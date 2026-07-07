# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    is_pos_store = fields.Boolean(
        string='Est un magasin POS',
        default=False,
        help="Cochez si cet entrepôt correspond à une boutique physique POS. "
             "Les entrepôts marqués ainsi apparaîtront dans le wizard d'approvisionnement."
    )
    responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsable du magasin',
        help="Utilisateur qui recevra les alertes de rupture de stock pour ce magasin."
    )
    central_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Entrepôt central',
        domain=[('is_pos_store', '=', False)],
        help="Entrepôt central qui approvisionne ce magasin. "
             "Doit correspondre à la configuration resupply_wh_ids."
    )

    def get_store_stock_summary(self):
        """
        Retourne un résumé du stock pour tous les magasins POS.
        Utilisé par le dashboard.
        """
        self.ensure_one()
        quants = self.env['stock.quant'].search([
            ('location_id', '=', self.lot_stock_id.id),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        return quants
