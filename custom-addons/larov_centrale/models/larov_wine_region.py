# -*- coding: utf-8 -*-
from odoo import fields, models


class LarovWineRegion(models.Model):
    """Région viticole d'un vin (Bourgogne, Bordeaux, Champagne, Loire…).

    Portée par le produit ; sert de colonne « Région » sur tous les documents
    LAROV et d'axe d'analyse pour l'inventaire en valeur et le CA.
    """
    _name = 'larov.wine.region'
    _description = 'Région viticole'
    _order = 'sequence, name'

    name = fields.Char(string='Région', required=True, translate=False)
    code = fields.Char(string='Code', size=8, help="Code court affiché sur les tickets (ex. BGN, BDX).")
    sequence = fields.Integer(default=10)
    country_id = fields.Many2one('res.country', string='Pays', default=lambda self: self.env.ref('base.fr', raise_if_not_found=False))
    active = fields.Boolean(default=True)
    product_count = fields.Integer(string='Nb produits', compute='_compute_product_count')

    _name_uniq = models.Constraint('unique(name)', "Cette région existe déjà.")

    def _compute_product_count(self):
        data = self.env['product.template']._read_group(
            [('wine_region_id', 'in', self.ids)], ['wine_region_id'], ['__count'],
        )
        counts = {region.id: count for region, count in data}
        for rec in self:
            rec.product_count = counts.get(rec.id, 0)
