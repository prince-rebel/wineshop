# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import date, timedelta


class StoreStockoutForecast(models.Model):
    """
    F7 — Prévision de rupture par magasin basée sur la vitesse de vente POS.
    Vue SQL calculant pour chaque produit × magasin :
    - La vitesse de vente moyenne sur les 30 derniers jours
    - Le nombre de jours avant rupture estimé
    """
    _name = 'store.stockout.forecast'
    _description = 'Prévision de rupture de stock'
    _auto = False
    _rec_name = 'product_name'
    _order = 'days_until_stockout asc nulls last'

    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_name = fields.Char(string='Produit', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Magasin', readonly=True)
    warehouse_name = fields.Char(string='Magasin', readonly=True)
    qty_on_hand = fields.Float(string='Stock actuel', readonly=True, digits='Product Unit')
    qty_sold_30d = fields.Float(string='Vendu (30j)', readonly=True, digits='Product Unit')
    daily_sales_rate = fields.Float(string='Ventes/jour', readonly=True, digits='[16,3]')
    days_until_stockout = fields.Integer(string='Jours avant rupture', readonly=True)
    estimated_stockout_date = fields.Date(string='Date rupture estimée', readonly=True)
    urgency = fields.Selection([
        ('critical', 'Critique (< 3 jours)'),
        ('warning', 'Attention (3-7 jours)'),
        ('ok', 'OK (> 7 jours)'),
        ('no_sales', 'Aucune vente récente'),
    ], string='Urgence', readonly=True)

    @api.model
    def get_pos_alerts(self, warehouse_id):
        """
        Méthode RPC appelée depuis la session POS.
        Retourne les alertes critiques et warnings pour le magasin donné.
        """
        records = self.search([
            ('warehouse_id', '=', warehouse_id),
            ('urgency', 'in', ['critical', 'warning']),
        ], order='days_until_stockout asc nulls last', limit=50)

        return [{
            'product_name': r.product_name,
            'qty_on_hand': r.qty_on_hand,
            'days_until_stockout': r.days_until_stockout,
            'urgency': r.urgency,
        } for r in records]

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS store_stockout_forecast")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW store_stockout_forecast AS
            WITH sales_30d AS (
                -- Ventes POS par produit et par magasin sur 30 jours
                -- Utilise picking_type_id.warehouse_id (plus fiable que warehouse_id direct)
                SELECT
                    pol.product_id,
                    COALESCE(spt.warehouse_id, pc.warehouse_id) AS warehouse_id,
                    SUM(pol.qty) AS qty_sold_30d,
                    SUM(pol.qty) / 30.0 AS daily_sales_rate
                FROM pos_order_line pol
                JOIN pos_order po ON po.id = pol.order_id
                JOIN pos_session ps ON ps.id = po.session_id
                JOIN pos_config pc ON pc.id = ps.config_id
                LEFT JOIN stock_picking_type spt ON spt.id = pc.picking_type_id
                WHERE po.state IN ('done', 'invoiced', 'paid')
                  AND po.date_order >= NOW() - INTERVAL '30 days'
                GROUP BY pol.product_id, COALESCE(spt.warehouse_id, pc.warehouse_id)
            ),
            stock_now AS (
                -- Stock actuel par produit et entrepôt POS uniquement
                SELECT
                    sq.product_id,
                    sl.warehouse_id,
                    SUM(sq.quantity) AS qty_on_hand
                FROM stock_quant sq
                JOIN stock_location sl ON sl.id = sq.location_id
                JOIN stock_warehouse sw ON sw.id = sl.warehouse_id AND sw.is_pos_store = TRUE
                WHERE sl.usage = 'internal'
                  AND sl.warehouse_id IS NOT NULL
                GROUP BY sq.product_id, sl.warehouse_id
            ),
            pos_store_products AS (
                -- Tous les produits POS actifs × tous les entrepôts POS
                -- Base produit-centrique : inclut même les ruptures sans ventes récentes
                -- Utilise picking_type_id.warehouse_id comme source de vérité
                SELECT DISTINCT
                    pp.id AS product_id,
                    COALESCE(spt.warehouse_id, pc.warehouse_id) AS warehouse_id
                FROM pos_config pc
                LEFT JOIN stock_picking_type spt ON spt.id = pc.picking_type_id
                JOIN stock_warehouse sw
                    ON sw.id = COALESCE(spt.warehouse_id, pc.warehouse_id)
                    AND sw.is_pos_store = TRUE
                    AND sw.active = TRUE
                CROSS JOIN product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    AND pt.active = TRUE
                    AND pt.available_in_pos = TRUE
            )
            SELECT
                ROW_NUMBER() OVER () AS id,
                pp.id AS product_id,
                COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS product_name,
                sw.id AS warehouse_id,
                sw.name AS warehouse_name,
                COALESCE(sn.qty_on_hand, 0) AS qty_on_hand,
                COALESCE(s.qty_sold_30d, 0) AS qty_sold_30d,
                COALESCE(s.daily_sales_rate, 0) AS daily_sales_rate,
                CASE
                    WHEN COALESCE(sn.qty_on_hand, 0) <= 0 THEN 0
                    WHEN COALESCE(s.daily_sales_rate, 0) <= 0 THEN NULL
                    ELSE GREATEST(0, FLOOR(sn.qty_on_hand / s.daily_sales_rate))::integer
                END AS days_until_stockout,
                CASE
                    WHEN COALESCE(sn.qty_on_hand, 0) <= 0 THEN CURRENT_DATE
                    WHEN COALESCE(s.daily_sales_rate, 0) <= 0 THEN NULL
                    ELSE (CURRENT_DATE + (GREATEST(0, FLOOR(sn.qty_on_hand / s.daily_sales_rate)) || ' days')::interval)::date
                END AS estimated_stockout_date,
                CASE
                    WHEN COALESCE(sn.qty_on_hand, 0) <= 0 THEN 'critical'
                    WHEN COALESCE(s.daily_sales_rate, 0) <= 0 THEN 'no_sales'
                    WHEN FLOOR(sn.qty_on_hand / s.daily_sales_rate) < 3 THEN 'critical'
                    WHEN FLOOR(sn.qty_on_hand / s.daily_sales_rate) < 7 THEN 'warning'
                    ELSE 'ok'
                END AS urgency
            FROM pos_store_products psp
            JOIN stock_warehouse sw ON sw.id = psp.warehouse_id
            JOIN product_product pp ON pp.id = psp.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN sales_30d s ON s.product_id = psp.product_id AND s.warehouse_id = psp.warehouse_id
            LEFT JOIN stock_now sn ON sn.product_id = psp.product_id AND sn.warehouse_id = psp.warehouse_id
            ORDER BY days_until_stockout ASC NULLS LAST
        """)
