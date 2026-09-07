# -*- coding: utf-8 -*-
from odoo import api, fields, models

CUSTOMER_SEGMENTS = [
    ('chr', 'CHR externe'),
    ('group', 'Groupe'),
    ('individual', 'Particulier'),
    ('company', 'Entreprise (cadeaux)'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ── Segmentation client (Lot 3) ─────────────────────────────────────────
    customer_segment = fields.Selection(
        CUSTOMER_SEGMENTS, string='Type de client', index=True,
        help="CHR externe (restaurants, hôtels, bars), Groupe (établissements "
             "du groupe : MUST, IVV, WEST…), Particulier (vente à emporter), "
             "Entreprise (cadeaux d'affaires).",
    )
    commercial_zone_id = fields.Many2one(
        'larov.commercial.zone', string='Secteur commercial', index=True,
        ondelete='set null',
    )
    # ── Rôles logistiques ───────────────────────────────────────────────────
    is_forwarder = fields.Boolean(
        string='Transitaire',
        help="Coché pour les transitaires (JEFF…). Permet de les sélectionner "
             "sur les commandes fournisseur et de ventiler les coûts logistiques.",
    )
    # ── Dépôt-vente (décision cadrage « mixte ») ────────────────────────────
    is_consignment_deposit = fields.Boolean(
        string='Dépôt-vente',
        help="Le vin livré chez ce client reste propriété de LAROV jusqu'à sa "
             "vente : le stock est suivi dans l'entrepôt indiqué ci-dessous.",
    )
    deposit_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Entrepôt de dépôt-vente',
        domain="[('establishment_type', '=', 'chr_deposit')]",
        help="Entrepôt Odoo représentant le stock LAROV chez ce client.",
    )
    # Libellé fiscal ivoirien (N° compte contribuable = champ TVA standard)
    taxpayer_number = fields.Char(
        string='N° compte contribuable', related='vat', readonly=False,
    )

    @api.onchange('is_consignment_deposit')
    def _onchange_is_consignment_deposit(self):
        if not self.is_consignment_deposit:
            self.deposit_warehouse_id = False

    @api.onchange('customer_segment')
    def _onchange_customer_segment(self):
        # Les clients CHR et groupe sont des sociétés ; les particuliers non.
        if self.customer_segment in ('chr', 'group', 'company'):
            self.is_company = True
        elif self.customer_segment == 'individual':
            self.is_company = False
