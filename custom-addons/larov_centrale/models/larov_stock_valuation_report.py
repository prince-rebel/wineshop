# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class LarovStockValuationReport(models.Model):
    """Inventaire de stock en valeur : quantité × coût unitaire (CMUP) par
    produit et par établissement.

    Vue SQL en lecture seule, source du rapport « Inventaire en valeur »
    (dépôts en colonnes) et des synthèses par région / par établissement.
    Le coût est le coût de revient du produit (champ Coût, alimenté par le
    CMUP et les coûts logistiques une fois la valorisation activée).
    """
    _name = 'larov.stock.valuation.report'
    _description = 'Inventaire en valeur par établissement'
    _auto = False
    _rec_name = 'product_id'
    _order = 'value desc, product_code'

    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Modèle', readonly=True)
    product_code = fields.Char(string='Réf.', readonly=True)
    product_name = fields.Char(string='Désignation', readonly=True)
    categ_id = fields.Many2one('product.category', string='Catégorie', readonly=True)
    wine_region_id = fields.Many2one('larov.wine.region', string='Région', readonly=True)
    wine_color = fields.Selection([
        ('rouge', 'Rouge'), ('blanc', 'Blanc'), ('rose', 'Rosé'),
        ('effervescent', 'Effervescent'), ('autre', 'Autre / N.A.'),
    ], string='Couleur', readonly=True)
    vintage = fields.Integer(string='Millésime', readonly=True)
    supplier_id = fields.Many2one('res.partner', string='Fournisseur principal', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Établissement', readonly=True)
    establishment_type = fields.Selection([
        ('central', 'Dépôt central'), ('shop', 'Boutique (caisse)'),
        ('chr_deposit', 'Dépôt-vente chez un client (CHR)'), ('other', 'Autre établissement'),
    ], string="Type d'établissement", readonly=True)
    company_id = fields.Many2one('res.company', string='Société', readonly=True)
    quantity = fields.Float(string='Quantité', readonly=True, digits='Product Unit')
    unit_cost = fields.Float(string='P.U. CMUP', readonly=True, digits='Product Price')
    value = fields.Float(string='Valeur stock', readonly=True, digits='Product Price')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH wh_stock AS (
                    SELECT
                        sw.id          AS warehouse_id,
                        sw.company_id  AS company_id,
                        sq.product_id  AS product_id,
                        SUM(sq.quantity) AS quantity
                    FROM stock_warehouse sw
                    JOIN stock_location sl_root ON sl_root.id = sw.lot_stock_id
                    JOIN stock_location sl
                         ON sl.parent_path LIKE sl_root.parent_path || '%%'
                        AND sl.usage = 'internal' AND sl.active = TRUE
                    JOIN stock_quant sq ON sq.location_id = sl.id
                    WHERE sw.active = TRUE
                    GROUP BY sw.id, sw.company_id, sq.product_id
                    HAVING SUM(sq.quantity) <> 0
                ),
                main_supplier AS (
                    SELECT DISTINCT ON (si.product_tmpl_id)
                           si.product_tmpl_id, si.partner_id
                    FROM product_supplierinfo si
                    ORDER BY si.product_tmpl_id, si.sequence, si.id
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY ws.product_id, ws.warehouse_id) AS id,
                    ws.product_id,
                    pt.id                                   AS product_tmpl_id,
                    pp.default_code                         AS product_code,
                    COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS product_name,
                    pt.categ_id,
                    pt.wine_region_id,
                    pt.wine_color,
                    pt.vintage,
                    ms.partner_id                           AS supplier_id,
                    ws.warehouse_id,
                    sw.establishment_type,
                    ws.company_id,
                    ws.quantity,
                    COALESCE((pp.standard_price->>(ws.company_id::text))::float, 0.0) AS unit_cost,
                    ws.quantity * COALESCE((pp.standard_price->>(ws.company_id::text))::float, 0.0) AS value
                FROM wh_stock ws
                JOIN stock_warehouse sw ON sw.id = ws.warehouse_id
                JOIN product_product pp ON pp.id = ws.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN main_supplier ms ON ms.product_tmpl_id = pt.id
            )
        """ % self._table)

    @api.model
    def _larov_matrix(self, warehouse_ids=None, region_ids=None):
        """Matrice produit × établissement pour le PDF « Inventaire en valeur ».

        Retourne (warehouses, rows, totals, by_region, by_warehouse) où rows est
        une liste de dicts triés par valeur décroissante.
        """
        domain = []
        if warehouse_ids:
            domain.append(('warehouse_id', 'in', warehouse_ids))
        if region_ids:
            domain.append(('wine_region_id', 'in', region_ids))
        records = self.search(domain)
        warehouses = records.mapped('warehouse_id').sorted(
            key=lambda w: (w.establishment_type != 'central', w.name)
        )
        rows = {}
        for rec in records:
            row = rows.setdefault(rec.product_id.id, {
                'code': rec.product_code or '',
                'name': rec.product_name or '',
                'region': rec.wine_region_id.name or '',
                'color': rec.product_id.wine_color_display,
                'supplier': rec.supplier_id.name or '',
                'unit_cost': rec.unit_cost,
                'qty': 0.0,
                'value': 0.0,
                'by_wh': {},
            })
            row['qty'] += rec.quantity
            row['value'] += rec.value
            row['by_wh'][rec.warehouse_id.id] = row['by_wh'].get(rec.warehouse_id.id, 0.0) + rec.quantity
        total_value = sum(r['value'] for r in rows.values()) or 0.0
        total_qty = sum(r['qty'] for r in rows.values()) or 0.0
        for row in rows.values():
            row['pct'] = (row['value'] / total_value * 100.0) if total_value else 0.0
        by_region, by_wh = {}, {}
        for rec in records:
            key = rec.wine_region_id.name or 'Non renseigné'
            by_region[key] = by_region.get(key, 0.0) + rec.value
            by_wh[rec.warehouse_id.name] = by_wh.get(rec.warehouse_id.name, 0.0) + rec.value
        by_wh_qty = {}
        for rec in records:
            by_wh_qty[rec.warehouse_id.id] = by_wh_qty.get(rec.warehouse_id.id, 0.0) + rec.quantity
        return {
            'warehouses': warehouses,
            'rows': sorted(rows.values(), key=lambda r: -r['value']),
            'total_qty': total_qty,
            'total_value': total_value,
            'by_wh_qty': by_wh_qty,
            'by_region': sorted(by_region.items(), key=lambda kv: -kv[1]),
            'by_warehouse': sorted(by_wh.items(), key=lambda kv: -kv[1]),
        }
