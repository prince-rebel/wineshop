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
    store_transfer_count = fields.Integer(
        string='Nombre de transferts',
        compute='_compute_store_transfer_count',
    )

    def _compute_store_transfer_count(self):
        Picking = self.env['stock.picking']
        for warehouse in self:
            warehouse.store_transfer_count = Picking.search_count([
                ('is_store_replenishment', '=', True),
                '|',
                ('dest_store_id', '=', warehouse.id),
                ('src_store_id', '=', warehouse.id),
            ])

    def action_view_store_transfer_history(self):
        """
        Ouvre le dashboard F4 (Historique des approvisionnements) filtré sur
        ce magasin, qu'il soit destinataire (réceptions) ou source (retours).
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pos_store_replenishment.action_store_replenishment_dashboard'
        )
        action['domain'] = [
            ('is_store_replenishment', '=', True),
            '|',
            ('dest_store_id', '=', self.id),
            ('src_store_id', '=', self.id),
        ]
        action['context'] = {'focus_warehouse_id': self.id, 'group_by': ['validation_group']}
        action['name'] = _('Transferts — %s') % self.name
        return action

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
