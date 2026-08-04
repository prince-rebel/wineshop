# -*- coding: utf-8 -*-
from odoo import fields, models


class PosSaleMarginReport(models.Model):
    """
    Vue SQL en lecture seule : rentabilité réelle des ventes POS
    (CA, coût, marge) par produit / magasin / période.
    Réservé aux managers (données financières sensibles).
    """
    _name = 'pos.sale.margin.report'
    _description = 'Rentabilité des ventes POS'
    _auto = False
    _rec_name = 'product_name'
    _order = 'date_order desc'

    order_id = fields.Many2one('pos.order', string='Commande', readonly=True)
    date_order = fields.Datetime(string='Date de vente', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Magasin', readonly=True)
    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_name = fields.Char(string='Produit', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Catégorie', readonly=True)
    qty = fields.Float(string='Quantité vendue', readonly=True, digits='Product Unit')
    revenue = fields.Float(string='CA (HT)', readonly=True, digits='Product Price')
    cost = fields.Float(string='Coût', readonly=True, digits='Product Price')
    margin = fields.Float(string='Marge', readonly=True, digits='Product Price')
    margin_pct = fields.Float(string='Marge %', readonly=True, digits=(16, 1))

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS pos_sale_margin_report")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW pos_sale_margin_report AS
            SELECT
                pol.id AS id,
                po.id AS order_id,
                po.date_order AS date_order,
                pc.warehouse_id AS warehouse_id,
                pol.product_id AS product_id,
                COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS product_name,
                pt.categ_id AS product_categ_id,
                pol.qty AS qty,
                pol.price_subtotal AS revenue,
                COALESCE(pol.total_cost, 0) AS cost,
                pol.price_subtotal - COALESCE(pol.total_cost, 0) AS margin,
                CASE
                    WHEN pol.price_subtotal > 0 THEN ROUND(
                        ((pol.price_subtotal - COALESCE(pol.total_cost, 0))
                         / pol.price_subtotal * 100)::numeric, 1
                    )
                    ELSE 0
                END AS margin_pct
            FROM pos_order_line pol
            JOIN pos_order po ON po.id = pol.order_id
            JOIN pos_config pc ON pc.id = po.config_id
            JOIN product_product pp ON pp.id = pol.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE po.state NOT IN ('cancel', 'draft')
        """)
