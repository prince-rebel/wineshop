# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ProductStoreHistory(models.Model):
    """
    F9 — Historique complet d'un produit, magasin par magasin.
    Vue SQL en lecture seule consolidant, pour chaque produit x magasin :
    - le stock actuel et les seuils min/max
    - les ventes POS (quantité, nombre de ventes, dernière vente)
    - les transferts inter-magasins (reçu / expédié, nombre, dernier mouvement)
    Alimente le smart button "Historique magasins" sur la fiche produit.
    """
    _name = 'product.store.history'
    _description = 'Historique produit par magasin'
    _auto = False
    _rec_name = 'warehouse_name'
    _order = 'warehouse_name'

    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_name = fields.Char(string='Produit', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Magasin', readonly=True)
    warehouse_name = fields.Char(string='Magasin', readonly=True)
    is_pos_store = fields.Boolean(string='Magasin POS', readonly=True)

    qty_on_hand = fields.Float(string='Stock actuel', readonly=True, digits='Product Unit')
    qty_min = fields.Float(string='Seuil min', readonly=True, digits='Product Unit')
    qty_max = fields.Float(string='Seuil max', readonly=True, digits='Product Unit')
    is_below_min = fields.Boolean(string='Sous le seuil', readonly=True)

    qty_sold_total = fields.Float(string='Vendu (total)', readonly=True, digits='Product Unit')
    nb_sales = fields.Integer(string='Nb ventes', readonly=True)
    last_sale_date = fields.Datetime(string='Dernière vente', readonly=True)

    qty_transferred_in = fields.Float(string='Reçu (transferts)', readonly=True, digits='Product Unit')
    qty_transferred_out = fields.Float(string='Expédié/retourné (transferts)', readonly=True, digits='Product Unit')
    nb_transfers = fields.Integer(string='Nb transferts', readonly=True)
    last_transfer_date = fields.Datetime(string='Dernier transfert', readonly=True)

    def action_view_transfers(self):
        """Ouvre le dashboard F4 filtré sur ce produit et ce magasin."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pos_store_replenishment.action_store_replenishment_dashboard'
        )
        action['domain'] = [
            ('is_store_replenishment', '=', True),
            ('move_ids.product_id', '=', self.product_id.id),
            '|',
            ('dest_store_id', '=', self.warehouse_id.id),
            ('src_store_id', '=', self.warehouse_id.id),
        ]
        action['context'] = {'focus_warehouse_id': self.warehouse_id.id, 'group_by': ['validation_group']}
        action['name'] = _('Transferts — %(product)s @ %(store)s') % {
            'product': self.product_name,
            'store': self.warehouse_name,
        }
        return action

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS product_store_history")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW product_store_history AS
            WITH warehouses AS (
                SELECT id, name, lot_stock_id, is_pos_store
                FROM stock_warehouse
                WHERE active = TRUE
            ),
            stock_now AS (
                SELECT sq.product_id, sl.warehouse_id, SUM(sq.quantity) AS qty_on_hand
                FROM stock_quant sq
                JOIN stock_location sl
                    ON sl.id = sq.location_id
                    AND sl.usage = 'internal'
                    AND sl.active = TRUE
                WHERE sl.warehouse_id IS NOT NULL
                GROUP BY sq.product_id, sl.warehouse_id
            ),
            thresholds AS (
                SELECT product_id, warehouse_id,
                       product_min_qty AS qty_min,
                       product_max_qty AS qty_max
                FROM stock_warehouse_orderpoint
            ),
            sales AS (
                SELECT
                    pol.product_id,
                    COALESCE(spt.warehouse_id, pc.warehouse_id) AS warehouse_id,
                    SUM(pol.qty) AS qty_sold_total,
                    COUNT(DISTINCT po.id) AS nb_sales,
                    MAX(po.date_order) AS last_sale_date
                FROM pos_order_line pol
                JOIN pos_order po ON po.id = pol.order_id
                JOIN pos_session ps ON ps.id = po.session_id
                JOIN pos_config pc ON pc.id = ps.config_id
                LEFT JOIN stock_picking_type spt ON spt.id = pc.picking_type_id
                WHERE po.state NOT IN ('cancel', 'draft')
                GROUP BY pol.product_id, COALESCE(spt.warehouse_id, pc.warehouse_id)
            ),
            transfers AS (
                SELECT
                    sm.product_id,
                    w.id AS warehouse_id,
                    SUM(CASE WHEN sm.location_dest_id = w.lot_stock_id THEN sm.quantity ELSE 0 END) AS qty_transferred_in,
                    SUM(CASE WHEN sm.location_id = w.lot_stock_id THEN sm.quantity ELSE 0 END) AS qty_transferred_out,
                    COUNT(DISTINCT sp.id) AS nb_transfers,
                    MAX(sp.date_done) AS last_transfer_date
                FROM stock_move sm
                JOIN stock_picking sp
                    ON sp.id = sm.picking_id
                    AND sp.is_store_replenishment = TRUE
                    AND sp.state = 'done'
                JOIN warehouses w
                    ON w.lot_stock_id = sm.location_dest_id
                    OR w.lot_stock_id = sm.location_id
                GROUP BY sm.product_id, w.id
            )
            SELECT
                -- Id stable et déterministe (produit x magasin), volontairement PAS
                -- ROW_NUMBER() OVER () : cette vue est réévaluée à chaque requête SQL,
                -- et un window function sans ORDER BY peut réassigner un id différent
                -- à une autre ligne (produit) selon le plan d'exécution choisi par
                -- Postgres. Comme Odoo fait souvent search() puis read() en deux
                -- requêtes séparées, un id instable ferait remonter les données d'un
                -- AUTRE produit/magasin que celui demandé. Avec des ids d'entrepôt
                -- toujours < 1000 (largement suffisant ici), pp.id * 1000 + w.id est
                -- unique et stable quelle que soit la requête.
                (pp.id * 1000 + w.id) AS id,
                pp.id AS product_id,
                COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS product_name,
                w.id AS warehouse_id,
                w.name AS warehouse_name,
                w.is_pos_store,
                COALESCE(sn.qty_on_hand, 0) AS qty_on_hand,
                COALESCE(th.qty_min, 0) AS qty_min,
                COALESCE(th.qty_max, 0) AS qty_max,
                CASE
                    WHEN th.qty_min IS NOT NULL AND COALESCE(sn.qty_on_hand, 0) < th.qty_min
                    THEN TRUE ELSE FALSE
                END AS is_below_min,
                COALESCE(s.qty_sold_total, 0) AS qty_sold_total,
                COALESCE(s.nb_sales, 0) AS nb_sales,
                s.last_sale_date,
                COALESCE(t.qty_transferred_in, 0) AS qty_transferred_in,
                COALESCE(t.qty_transferred_out, 0) AS qty_transferred_out,
                COALESCE(t.nb_transfers, 0) AS nb_transfers,
                t.last_transfer_date
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id AND pt.active = TRUE
            CROSS JOIN warehouses w
            LEFT JOIN stock_now sn ON sn.product_id = pp.id AND sn.warehouse_id = w.id
            LEFT JOIN thresholds th ON th.product_id = pp.id AND th.warehouse_id = w.id
            LEFT JOIN sales s ON s.product_id = pp.id AND s.warehouse_id = w.id
            LEFT JOIN transfers t ON t.product_id = pp.id AND t.warehouse_id = w.id
            WHERE
                COALESCE(sn.qty_on_hand, 0) != 0
                OR COALESCE(s.qty_sold_total, 0) != 0
                OR COALESCE(t.nb_transfers, 0) != 0
                OR th.qty_min IS NOT NULL
        """)
