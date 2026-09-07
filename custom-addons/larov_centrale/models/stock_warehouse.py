# -*- coding: utf-8 -*-
from odoo import api, fields, models

ESTABLISHMENT_TYPES = [
    ('central', 'Dépôt central'),
    ('shop', 'Boutique (caisse)'),
    ('chr_deposit', 'Dépôt-vente chez un client (CHR)'),
    ('other', 'Autre établissement'),
]


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    establishment_type = fields.Selection(
        ESTABLISHMENT_TYPES, string="Type d'établissement",
        default='other', required=True, index=True,
        help="Dépôt central : reçoit les arrivages et approvisionne les autres. "
             "Boutique : point de vente avec caisse. "
             "Dépôt-vente : stock LAROV entreposé chez un client CHR.",
    )
    consignee_partner_id = fields.Many2one(
        'res.partner', string='Client dépositaire',
        help="Pour un dépôt-vente : le client CHR chez qui le stock est entreposé.",
    )
    deposit_pickings_count = fields.Integer(
        string='Mouvements', compute='_compute_deposit_pickings_count',
    )

    @api.onchange('establishment_type')
    def _onchange_establishment_type(self):
        # Compatibilité avec le module existant : une boutique = magasin POS.
        self.is_pos_store = self.establishment_type == 'shop'
        if self.establishment_type != 'chr_deposit':
            self.consignee_partner_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('establishment_type') == 'shop':
                vals.setdefault('is_pos_store', True)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('establishment_type') == 'shop':
            vals.setdefault('is_pos_store', True)
        res = super().write(vals)
        # Lier automatiquement le client dépositaire à son entrepôt
        for wh in self.filtered(lambda w: w.establishment_type == 'chr_deposit' and w.consignee_partner_id):
            partner = wh.consignee_partner_id
            if not partner.is_consignment_deposit or partner.deposit_warehouse_id != wh:
                partner.write({'is_consignment_deposit': True, 'deposit_warehouse_id': wh.id})
        return res

    def _compute_deposit_pickings_count(self):
        Picking = self.env['stock.picking']
        for wh in self:
            wh.deposit_pickings_count = Picking.search_count([
                '|',
                ('location_id.warehouse_id', '=', wh.id),
                ('location_dest_id.warehouse_id', '=', wh.id),
                ('state', '=', 'done'),
            ])
