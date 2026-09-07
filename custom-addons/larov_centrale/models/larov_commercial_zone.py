# -*- coding: utf-8 -*-
from odoo import fields, models


class LarovCommercialZone(models.Model):
    """Région / secteur commercial d'un client (Cocody, Marcory, Assinie…).

    Distinct de la région viticole du produit. Sert à la segmentation des
    clients (Lot 3) et au chiffre d'affaires « par région ».
    """
    _name = 'larov.commercial.zone'
    _description = 'Secteur commercial'
    _order = 'sequence, name'

    name = fields.Char(string='Secteur', required=True)
    sequence = fields.Integer(default=10)
    salesperson_id = fields.Many2one('res.users', string='Commercial référent')
    active = fields.Boolean(default=True)
    partner_count = fields.Integer(string='Nb clients', compute='_compute_partner_count')

    _name_uniq = models.Constraint('unique(name)', "Ce secteur existe déjà.")

    def _compute_partner_count(self):
        data = self.env['res.partner']._read_group(
            [('commercial_zone_id', 'in', self.ids)], ['commercial_zone_id'], ['__count'],
        )
        counts = {zone.id: count for zone, count in data}
        for rec in self:
            rec.partner_count = counts.get(rec.id, 0)
