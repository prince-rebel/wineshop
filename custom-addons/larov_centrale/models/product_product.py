# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    monthly_sales_qty = fields.Float(
        string='Vente mensuelle', compute='_compute_monthly_sales_qty',
        digits='Product Unit',
    )
    incoming_po_qty = fields.Float(
        string='Arrivage en cours', compute='_compute_incoming_po_qty',
        digits='Product Unit',
    )
    coverage_months = fields.Float(
        string='Couverture (mois)', compute='_compute_coverage_months', digits=(16, 1),
    )
    alert_stock_qty = fields.Float(
        string="Stock d'alerte", compute='_compute_coverage_months',
        digits='Product Unit',
        help="Vente mensuelle × couverture visée.",
    )
    price_chr = fields.Float(
        string='Prix CHR', compute='_compute_larov_prices', digits='Product Price',
        help="Prix TTC selon la liste de prix CHR paramétrée.",
    )
    price_takeaway = fields.Float(
        string='Prix à emporter', compute='_compute_larov_prices', digits='Product Price',
        help="Prix TTC selon la liste de prix « à emporter » paramétrée.",
    )
    stockout_estimate_months = fields.Float(
        string='Estimation rupture (mois)', compute='_compute_coverage_months', digits=(16, 1),
        help="Stock disponible ÷ vente mensuelle : nombre de mois avant rupture.",
    )
    suggested_order_qty = fields.Float(
        string='Proposition de commande', compute='_compute_coverage_months',
        digits='Product Unit',
        help="Stock d'alerte − stock disponible − arrivage en cours (jamais négatif).",
    )

    # ------------------------------------------------------------------
    # Vente mensuelle : mouvements de stock « terminés » vers les clients
    # (caisse ET ventes B2B), nets des retours, sur N mois glissants.
    # ------------------------------------------------------------------
    @api.model
    def _larov_monthly_sales_map(self, product_ids, months=None, warehouse_id=None):
        """Retourne {product_id: qté vendue par mois} pour les produits donnés."""
        if not product_ids:
            return {}
        months = months or self.env['larov.settings'].sales_history_months()
        date_from = fields.Datetime.now() - relativedelta(months=months)
        domain_out = [
            ('product_id', 'in', product_ids),
            ('state', '=', 'done'),
            ('date', '>=', date_from),
            ('location_dest_id.usage', '=', 'customer'),
            ('location_id.usage', '=', 'internal'),
        ]
        domain_in = [
            ('product_id', 'in', product_ids),
            ('state', '=', 'done'),
            ('date', '>=', date_from),
            ('location_id.usage', '=', 'customer'),
            ('location_dest_id.usage', '=', 'internal'),
        ]
        if warehouse_id:
            wh_ids = warehouse_id if isinstance(warehouse_id, (list, tuple)) else [warehouse_id]
            domain_out.append(('location_id.warehouse_id', 'in', wh_ids))
            domain_in.append(('location_dest_id.warehouse_id', 'in', wh_ids))
        Move = self.env['stock.move']
        sold = {p.id: q for p, q in Move._read_group(domain_out, ['product_id'], ['quantity:sum'])}
        returned = {p.id: q for p, q in Move._read_group(domain_in, ['product_id'], ['quantity:sum'])}
        return {
            pid: max(0.0, (sold.get(pid, 0.0) - returned.get(pid, 0.0)) / months)
            for pid in product_ids
        }

    @api.depends_context('warehouse_id', 'larov_history_months')
    def _compute_monthly_sales_qty(self):
        sales = self._larov_monthly_sales_map(
            self.ids,
            months=self.env.context.get('larov_history_months'),
            warehouse_id=self.env.context.get('warehouse_id'),
        )
        for product in self:
            product.monthly_sales_qty = sales.get(product.id, 0.0)

    # ------------------------------------------------------------------
    # Arrivage en cours : lignes de commande fournisseur confirmées,
    # quantité commandée − quantité déjà reçue.
    # ------------------------------------------------------------------
    @api.model
    def _larov_incoming_po_map(self, product_ids):
        if not product_ids:
            return {}
        lines = self.env['purchase.order.line'].search([
            ('product_id', 'in', product_ids),
            ('state', 'in', ('purchase', 'done')),
        ])
        res = dict.fromkeys(product_ids, 0.0)
        for line in lines:
            res[line.product_id.id] += max(0.0, line.product_qty - line.qty_received)
        return res

    def _compute_incoming_po_qty(self):
        incoming = self._larov_incoming_po_map(self.ids)
        for product in self:
            product.incoming_po_qty = incoming.get(product.id, 0.0)

    @api.depends('monthly_sales_qty', 'incoming_po_qty', 'qty_available')
    @api.depends_context('larov_coverage_months')
    def _compute_coverage_months(self):
        coverage_target = self.env.context.get('larov_coverage_months') or self.env['larov.settings'].coverage_months()
        for product in self:
            monthly = product.monthly_sales_qty
            product.coverage_months = (product.qty_available / monthly) if monthly else 0.0
            product.stockout_estimate_months = product.coverage_months
            product.alert_stock_qty = monthly * coverage_target
            product.suggested_order_qty = max(
                0.0, product.alert_stock_qty - product.qty_available - product.incoming_po_qty,
            )

    # ------------------------------------------------------------------
    # Prix CHR / à emporter (fiche commerciale) selon les listes de prix
    # paramétrées dans Inventaire › Configuration › Paramètres.
    # ------------------------------------------------------------------
    def _compute_larov_prices(self):
        settings = self.env['larov.settings']
        pl_chr = settings.pricelist_chr()
        pl_take = settings.pricelist_takeaway()
        prices_chr = pl_chr._get_products_price(self, 1.0) if pl_chr else {}
        prices_take = pl_take._get_products_price(self, 1.0) if pl_take else {}
        for product in self:
            base_chr = prices_chr.get(product.id, product.list_price)
            base_take = prices_take.get(product.id, product.list_price)
            product.price_chr = product._larov_price_ttc(base_chr, pl_chr)
            product.price_takeaway = product._larov_price_ttc(base_take, pl_take)

    def _larov_price_ttc(self, price, pricelist=None):
        """Convertit un prix de liste en TTC (les documents LAROV sont TTC)."""
        self.ensure_one()
        taxes = self.taxes_id.filtered(lambda t: t.company_id == self.env.company) or self.taxes_id
        if not taxes:
            return price
        currency = (pricelist and pricelist.currency_id) or self.env.company.currency_id
        return taxes.compute_all(price, currency=currency, quantity=1.0, product=self)['total_included']
