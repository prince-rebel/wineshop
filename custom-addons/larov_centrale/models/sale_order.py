# -*- coding: utf-8 -*-
from odoo import api, fields, models

RECEPTION_CHANNELS = [
    ('whatsapp', 'WhatsApp'),
    ('phone', 'Téléphone'),
    ('email', 'E-mail'),
    ('visit', 'Visite / comptoir'),
    ('salesperson', 'Commercial'),
    ('website', 'Site web'),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    reception_channel = fields.Selection(
        RECEPTION_CHANNELS, string='Canal de réception', default='whatsapp',
        help="Comment la commande a été reçue (ex. WhatsApp — groupe Info Générale).",
    )
    reception_channel_label = fields.Char(compute='_compute_reception_channel_label')
    customer_segment = fields.Selection(
        related='partner_id.customer_segment', string='Type de client', store=True,
    )
    commercial_zone_id = fields.Many2one(
        related='partner_id.commercial_zone_id', string='Secteur commercial', store=True,
    )
    total_bottles = fields.Float(string='Nombre de bouteilles', compute='_compute_larov_totals', digits='Product Unit')
    total_discount_amount = fields.Monetary(string='Remise accordée', compute='_compute_larov_totals')
    all_lines_available = fields.Boolean(
        string='Livrable en totalité', compute='_compute_larov_totals',
        help="Toutes les lignes sont disponibles dans l'entrepôt de la commande.",
    )
    proforma_validity_days = fields.Integer(string='Validité proforma (jours)', default=30)

    @api.depends('reception_channel')
    def _compute_reception_channel_label(self):
        labels = dict(self._fields['reception_channel'].selection)
        for order in self:
            order.reception_channel_label = labels.get(order.reception_channel, '')

    @api.depends('order_line.product_uom_qty', 'order_line.price_unit_ttc', 'order_line.discount',
                 'order_line.is_available', 'order_line.product_id')
    def _compute_larov_totals(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: not l.display_type)
            product_lines = lines.filtered(lambda l: l.product_id.type == 'consu')
            order.total_bottles = sum(product_lines.filtered(lambda l: l.product_id.is_wine).mapped('product_uom_qty'))
            order.total_discount_amount = sum(
                l.price_unit_ttc * l.product_uom_qty * (l.discount or 0.0) / 100.0 for l in lines
            )
            stock_lines = product_lines.filtered(lambda l: l.product_id.is_storable)
            order.all_lines_available = all(stock_lines.mapped('is_available')) if stock_lines else True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    qty_available_wh = fields.Float(
        string='Stock dispo', compute='_compute_availability', digits='Product Unit',
        help="Quantité disponible (non réservée) dans l'entrepôt de la commande.",
    )
    is_available = fields.Boolean(string='Dispo ?', compute='_compute_availability')
    availability_label = fields.Char(string='Disponibilité', compute='_compute_availability')
    wine_region_id = fields.Many2one(related='product_id.wine_region_id', string='Région')
    wine_color = fields.Selection(related='product_id.wine_color', string='Couleur')
    vintage_display = fields.Char(related='product_id.vintage_display', string='Mill.')
    price_unit_ttc = fields.Monetary(
        string='P.U. TTC', compute='_compute_price_unit_ttc',
        help="Prix unitaire toutes taxes comprises, avant remise — tel qu'imprimé sur les documents LAROV.",
    )

    @api.depends('price_unit', 'tax_ids', 'product_id', 'order_id.partner_id', 'order_id.currency_id')
    def _compute_price_unit_ttc(self):
        for line in self:
            if not line.product_id or not line.tax_ids:
                line.price_unit_ttc = line.price_unit
                continue
            taxes = line.tax_ids.compute_all(
                line.price_unit, currency=line.currency_id, quantity=1.0,
                product=line.product_id, partner=line.order_id.partner_shipping_id,
            )
            line.price_unit_ttc = taxes['total_included']

    @api.depends('product_id', 'product_uom_qty', 'order_id.warehouse_id')
    def _compute_availability(self):
        for line in self:
            product = line.product_id
            if not product or not product.is_storable:
                line.qty_available_wh = 0.0
                line.is_available = True
                line.availability_label = ''
                continue
            wh = line.order_id.warehouse_id
            qty = product.with_context(warehouse_id=wh.id).free_qty if wh else product.free_qty
            # Une ligne déjà confirmée a réservé son stock : on le réintègre.
            if line.state == 'sale':
                qty += line.product_uom_qty - line.qty_delivered
            line.qty_available_wh = qty
            line.is_available = qty >= line.product_uom_qty
            line.availability_label = 'OUI' if line.is_available else 'MANQUE %s' % int(line.product_uom_qty - qty)
