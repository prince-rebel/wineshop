# -*- coding: utf-8 -*-
from odoo import api, fields, models

WINE_COLORS = [
    ('rouge', 'Rouge'),
    ('blanc', 'Blanc'),
    ('rose', 'Rosé'),
    ('effervescent', 'Effervescent'),
    ('autre', 'Autre / N.A.'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ── Fiche vin (décision cadrage : un article par millésime) ─────────────
    is_wine = fields.Boolean(
        string='Vin / spiritueux',
        default=True,
        help="Décoché pour les accessoires, PLV et emballages : les colonnes "
             "Région / Couleur / Millésime restent vides sur les documents.",
    )
    wine_region_id = fields.Many2one(
        'larov.wine.region', string='Région', index=True, ondelete='restrict',
    )
    wine_color = fields.Selection(WINE_COLORS, string='Couleur')
    vintage = fields.Integer(
        string='Millésime',
        help="Année du millésime. Vide pour les champagnes non millésimés.",
    )
    vintage_display = fields.Char(string='Mill.', compute='_compute_vintage_display')
    wine_color_display = fields.Char(string='Couleur (libellé)', compute='_compute_wine_color_display')
    estate = fields.Char(string='Domaine / Producteur')
    appellation = fields.Char(
        string='Appellation',
        help="Libellé court de l'appellation tel qu'imprimé sur les bons "
             "(ex. « Bourgogne Aligoté »). Par défaut : le nom du produit.",
    )
    bottle_size = fields.Selection([
        ('37.5', '37,5 cl'),
        ('75', '75 cl'),
        ('150', 'Magnum 1,5 L'),
        ('300', 'Jéroboam 3 L'),
        ('other', 'Autre'),
    ], string='Format', default='75')
    bottles_per_case = fields.Integer(
        string='Bouteilles par carton',
        default=lambda self: self.env['larov.settings'].bottles_per_case(),
    )

    # ── Indicateurs achats / réappro (agrégés depuis les variantes) ─────────
    monthly_sales_qty = fields.Float(
        string='Vente mensuelle', compute='_compute_larov_indicators',
        digits='Product Unit',
        help="Quantité vendue en moyenne par mois (caisse + ventes) sur "
             "l'historique paramétré.",
    )
    incoming_po_qty = fields.Float(
        string='Arrivage en cours', compute='_compute_larov_indicators',
        digits='Product Unit',
        help="Quantité commandée aux fournisseurs et non encore reçue.",
    )
    coverage_months = fields.Float(
        string='Couverture (mois)', compute='_compute_larov_indicators', digits=(16, 1),
        help="Stock disponible ÷ vente mensuelle.",
    )

    @api.depends('vintage')
    def _compute_vintage_display(self):
        for tmpl in self:
            tmpl.vintage_display = str(tmpl.vintage) if tmpl.vintage else ''

    @api.depends('wine_color', 'is_wine')
    def _compute_wine_color_display(self):
        labels = dict(self._fields['wine_color'].selection)
        for tmpl in self:
            tmpl.wine_color_display = labels.get(tmpl.wine_color, '') if tmpl.is_wine else ''

    @api.depends('product_variant_ids')
    def _compute_larov_indicators(self):
        for tmpl in self:
            variants = tmpl.product_variant_ids
            tmpl.monthly_sales_qty = sum(variants.mapped('monthly_sales_qty'))
            tmpl.incoming_po_qty = sum(variants.mapped('incoming_po_qty'))
            monthly = tmpl.monthly_sales_qty
            tmpl.coverage_months = (tmpl.qty_available / monthly) if monthly else 0.0

    def _get_larov_appellation(self):
        self.ensure_one()
        return self.appellation or self.name
