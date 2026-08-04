# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StoreStockReport(models.Model):
    """
    F6 — Vue SQL en lecture seule pour le tableau de bord stock global.
    Affiche le stock, la valeur immobilisée et la marge par produit × magasin.
    Réservé aux managers (accès restreint dans le menu).
    """
    _name = 'store.stock.report'
    _description = 'Stock global par magasin'
    _auto = False
    _rec_name = 'product_name'
    _order = 'product_name, warehouse_name'

    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_name = fields.Char(string='Produit', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Catégorie', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Magasin / Entrepôt', readonly=True)
    warehouse_name = fields.Char(string='Magasin', readonly=True)
    is_pos_store = fields.Boolean(string='Magasin POS', readonly=True)
    qty_on_hand = fields.Float(string='Stock disponible', readonly=True, digits='Product Unit')
    qty_min = fields.Float(string='Seuil minimum', readonly=True, digits='Product Unit')
    qty_max = fields.Float(string='Seuil maximum', readonly=True, digits='Product Unit')
    is_below_min = fields.Boolean(string='Sous le seuil', readonly=True)

    # Colonnes coût — réservées aux managers
    cost_price = fields.Float(string='Coût unitaire', readonly=True, digits='Product Price')
    sale_price = fields.Float(string='Prix de vente', readonly=True, digits='Product Price')
    stock_value = fields.Float(string='Valeur du stock (coût total)', readonly=True, digits='Product Price')
    margin_value = fields.Float(string='Marge unitaire', readonly=True, digits='Product Price')
    margin_pct = fields.Float(string='Marge %', readonly=True, digits='[16,1]')
    sale_value = fields.Float(string='Vente potentielle (prix de vente)', readonly=True, digits='Product Price')
    margin_total = fields.Float(string='Marge totale attendue', readonly=True, digits='Product Price')

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS store_stock_report")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW store_stock_report AS
            WITH warehouse_stock AS (
                -- Stock par entrepôt, en incluant TOUTES les sous-locations internes
                -- (parent_path LIKE couvre lot_stock_id et ses enfants)
                SELECT
                    sw.id AS warehouse_id,
                    sq.product_id,
                    SUM(sq.quantity) AS qty_on_hand
                FROM stock_warehouse sw
                JOIN stock_location sl_root ON sl_root.id = sw.lot_stock_id
                JOIN stock_location sl
                    ON sl.parent_path LIKE sl_root.parent_path || '%%'
                    AND sl.usage = 'internal'
                    AND sl.active = TRUE
                JOIN stock_quant sq ON sq.location_id = sl.id
                WHERE sw.active = TRUE
                GROUP BY sw.id, sq.product_id
                HAVING SUM(sq.quantity) > 0
            )
            SELECT
                ROW_NUMBER() OVER () AS id,
                pp.id AS product_id,
                COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS product_name,
                pt.categ_id AS product_categ_id,
                sw.id AS warehouse_id,
                sw.name AS warehouse_name,
                sw.is_pos_store,
                ws.qty_on_hand,
                COALESCE(MAX(op.product_min_qty), 0) AS qty_min,
                COALESCE(MAX(op.product_max_qty), 0) AS qty_max,
                CASE
                    WHEN ws.qty_on_hand < COALESCE(MAX(op.product_min_qty), 0)
                    THEN TRUE ELSE FALSE
                END AS is_below_min,
                -- Coût de revient (standard_price est un JSONB company_id → valeur)
                COALESCE(
                    CAST((SELECT value FROM jsonb_each_text(pp.standard_price) LIMIT 1) AS FLOAT),
                    0
                ) AS cost_price,
                pt.list_price AS sale_price,
                -- Valeur du stock immobilisé
                ws.qty_on_hand * COALESCE(
                    CAST((SELECT value FROM jsonb_each_text(pp.standard_price) LIMIT 1) AS FLOAT),
                    0
                ) AS stock_value,
                -- Marge unitaire et %
                pt.list_price - COALESCE(
                    CAST((SELECT value FROM jsonb_each_text(pp.standard_price) LIMIT 1) AS FLOAT),
                    0
                ) AS margin_value,
                CASE
                    WHEN pt.list_price > 0 THEN ROUND(
                        ((pt.list_price - COALESCE(
                            CAST((SELECT value FROM jsonb_each_text(pp.standard_price) LIMIT 1) AS FLOAT),
                            0
                        )) / pt.list_price * 100)::numeric, 1
                    )
                    ELSE 0
                END AS margin_pct,
                -- Vente potentielle : ce que rapporterait tout le stock vendu au prix de vente
                ws.qty_on_hand * pt.list_price AS sale_value,
                -- Marge totale attendue sur tout le stock disponible (pas juste unitaire)
                ws.qty_on_hand * (pt.list_price - COALESCE(
                    CAST((SELECT value FROM jsonb_each_text(pp.standard_price) LIMIT 1) AS FLOAT),
                    0
                )) AS margin_total
            FROM warehouse_stock ws
            JOIN stock_warehouse sw ON sw.id = ws.warehouse_id
            JOIN product_product pp ON pp.id = ws.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id AND pt.active = TRUE
            LEFT JOIN stock_warehouse_orderpoint op
                ON op.warehouse_id = sw.id
                AND op.product_id = pp.id
            GROUP BY pp.id, pt.name, pt.categ_id, sw.id, sw.name, sw.is_pos_store,
                     ws.qty_on_hand, pp.standard_price, pt.list_price
        """)
