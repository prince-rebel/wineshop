# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # Odoo core fournit déjà 'margin' et 'margin_percent' (compute='_compute_margin').
    # On n'ajoute ici que le coût total, absent du cœur au niveau commande
    # (il n'existe que sur pos.order.line). Nom de méthode dédié pour ne
    # jamais entrer en collision avec le _compute_margin natif.
    total_cost = fields.Monetary(
        string='Coût',
        compute='_compute_pos_replenishment_total_cost',
        store=True,
        groups='point_of_sale.group_pos_manager',
    )

    @api.depends('lines.total_cost')
    def _compute_pos_replenishment_total_cost(self):
        for order in self:
            order.total_cost = sum(order.lines.mapped('total_cost'))
