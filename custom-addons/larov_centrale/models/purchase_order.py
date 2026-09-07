# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # ── Import (Lot 1 / Lot 2) ──────────────────────────────────────────────
    forwarder_id = fields.Many2one(
        'res.partner', string='Transitaire retenu',
        domain=[('is_forwarder', '=', True)], tracking=True,
        help="Transitaire qui prend en charge l'acheminement de cette commande. "
             "Sert à ventiler le coût de revient par transitaire.",
    )
    transport_mode = fields.Selection([
        ('sea', 'Conteneur maritime'),
        ('air', 'Fret aérien'),
        ('road', 'Routier'),
        ('groupage', 'Groupage'),
    ], string='Mode de transport', default='sea')
    transport_mode_label = fields.Char(compute='_compute_transport_mode_label')
    delivery_terms = fields.Char(
        string='Incoterm / livraison',
        help="Ex. « Départ cave — enlèvement groupé ». L'incoterm normalisé "
             "reste dans le champ standard Incoterm.",
    )
    expected_arrival_date = fields.Date(string='Arrivée prévue (Abidjan)')
    target_coverage_months = fields.Float(
        string='Couverture visée (mois)',
        default=lambda self: self.env['larov.settings'].coverage_months(),
        digits=(16, 1),
    )
    bottles_per_case = fields.Integer(
        string='Bouteilles par carton',
        default=lambda self: self.env['larov.settings'].bottles_per_case(),
    )
    exchange_rate_xof = fields.Float(
        string='Taux de change (1 devise = X FCFA)', compute='_compute_exchange_rate_xof',
        digits=(16, 3),
    )
    amount_total_xof = fields.Monetary(
        string='Contre-valeur FCFA', compute='_compute_exchange_rate_xof',
        currency_field='company_currency_id',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Devise société', readonly=True,
    )
    total_bottles = fields.Float(string='Total bouteilles', compute='_compute_totals_larov', digits='Product Unit')
    total_cases = fields.Integer(string='Total cartons', compute='_compute_totals_larov')
    has_coverage_warning = fields.Boolean(
        string='Couverture à justifier', compute='_compute_totals_larov',
        help="Au moins une ligne dépasse la couverture maximale paramétrée.",
    )

    # ── Suivi de la commande (jalons imprimés sur le bon) ───────────────────
    date_deposit_paid = fields.Date(string='Paiement acompte', tracking=True)
    date_pickup = fields.Date(string='Enlèvement / départ', tracking=True)
    date_shipped = fields.Date(string='Embarquement', tracking=True)
    date_arrived_port = fields.Date(string='Arrivée Abidjan', tracking=True)
    date_received_warehouse = fields.Date(
        string='Réception en dépôt', compute='_compute_date_received_warehouse',
        help="Date de la dernière réception validée.",
    )
    import_status = fields.Selection([
        ('ordered', 'Commandée'),
        ('deposit_paid', 'Acompte payé'),
        ('picked_up', 'Enlevée'),
        ('shipped', 'Embarquée'),
        ('arrived', 'Arrivée Abidjan'),
        ('received', 'Réceptionnée'),
    ], string="Étape d'import", compute='_compute_import_status', store=True)

    @api.depends('transport_mode')
    def _compute_transport_mode_label(self):
        labels = dict(self._fields['transport_mode'].selection)
        for order in self:
            order.transport_mode_label = labels.get(order.transport_mode, '')

    @api.depends('currency_id', 'company_id.currency_id', 'date_order', 'amount_total')
    def _compute_exchange_rate_xof(self):
        for order in self:
            company_cur = order.company_id.currency_id
            if order.currency_id and company_cur and order.currency_id != company_cur:
                rate = order.currency_id._get_conversion_rate(
                    order.currency_id, company_cur, order.company_id,
                    order.date_order or fields.Date.today(),
                )
            else:
                rate = 1.0
            order.exchange_rate_xof = rate
            order.amount_total_xof = order.amount_total * rate

    @api.depends('order_line.product_qty', 'order_line.cases_qty', 'order_line.coverage_after_receipt')
    def _compute_totals_larov(self):
        max_cov = self.env['larov.settings'].max_coverage_months()
        for order in self:
            lines = order.order_line.filtered(lambda l: not l.display_type)
            order.total_bottles = sum(lines.mapped('product_qty'))
            order.total_cases = sum(lines.mapped('cases_qty'))
            order.has_coverage_warning = any(
                l.coverage_after_receipt > max_cov for l in lines if l.monthly_sales_qty
            )

    @api.depends('picking_ids.state', 'picking_ids.date_done')
    def _compute_date_received_warehouse(self):
        for order in self:
            done = order.picking_ids.filtered(lambda p: p.state == 'done' and p.date_done)
            order.date_received_warehouse = max(done.mapped('date_done')).date() if done else False

    @api.depends('state', 'date_deposit_paid', 'date_pickup', 'date_shipped',
                 'date_arrived_port', 'date_received_warehouse')
    def _compute_import_status(self):
        for order in self:
            if order.state not in ('purchase', 'done'):
                order.import_status = False
            elif order.date_received_warehouse:
                order.import_status = 'received'
            elif order.date_arrived_port:
                order.import_status = 'arrived'
            elif order.date_shipped:
                order.import_status = 'shipped'
            elif order.date_pickup:
                order.import_status = 'picked_up'
            elif order.date_deposit_paid:
                order.import_status = 'deposit_paid'
            else:
                order.import_status = 'ordered'


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    cases_qty = fields.Integer(
        string='Cartons', compute='_compute_cases_qty',
        help="Quantité ÷ bouteilles par carton, arrondi au carton supérieur.",
    )
    qty_stock_current = fields.Float(
        string='Stock actuel', compute='_compute_larov_coverage', digits='Product Unit',
        help="Stock disponible toutes localisations LAROV au moment de la commande.",
    )
    monthly_sales_qty = fields.Float(
        string='Vente mensuelle', compute='_compute_larov_coverage', digits='Product Unit',
    )
    coverage_after_receipt = fields.Float(
        string='Couverture (mois)', compute='_compute_larov_coverage', digits=(16, 1),
        help="(Stock actuel + arrivage en cours + quantité commandée) ÷ vente mensuelle.",
    )
    coverage_warning = fields.Boolean(compute='_compute_larov_coverage')
    wine_region_id = fields.Many2one(related='product_id.wine_region_id', string='Région')
    wine_color = fields.Selection(related='product_id.wine_color', string='Couleur')
    vintage_display = fields.Char(related='product_id.vintage_display', string='Mill.')
    estate = fields.Char(related='product_id.estate', string='Domaine')

    @api.depends('product_qty', 'order_id.bottles_per_case', 'product_id.bottles_per_case')
    def _compute_cases_qty(self):
        for line in self:
            per_case = line.product_id.bottles_per_case or line.order_id.bottles_per_case or 0
            if per_case and line.product_qty:
                line.cases_qty = -(-int(line.product_qty) // per_case)  # arrondi supérieur
            else:
                line.cases_qty = 0

    @api.depends('product_id', 'product_qty')
    def _compute_larov_coverage(self):
        max_cov = self.env['larov.settings'].max_coverage_months()
        products = self.mapped('product_id')
        sales = self.env['product.product']._larov_monthly_sales_map(products.ids)
        incoming = self.env['product.product']._larov_incoming_po_map(products.ids)
        for line in self:
            product = line.product_id
            if not product:
                line.qty_stock_current = line.monthly_sales_qty = line.coverage_after_receipt = 0.0
                line.coverage_warning = False
                continue
            monthly = sales.get(product.id, 0.0)
            # L'arrivage en cours inclut déjà cette ligne si la commande est confirmée
            other_incoming = incoming.get(product.id, 0.0)
            if line.state in ('purchase', 'done'):
                other_incoming = max(0.0, other_incoming - max(0.0, line.product_qty - line.qty_received))
            line.qty_stock_current = product.qty_available
            line.monthly_sales_qty = monthly
            projected = product.qty_available + other_incoming + line.product_qty
            line.coverage_after_receipt = (projected / monthly) if monthly else 0.0
            line.coverage_warning = bool(monthly) and line.coverage_after_receipt > max_cov
