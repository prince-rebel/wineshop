# -*- coding: utf-8 -*-
from odoo import api, fields, models

PARAM_COVERAGE = 'larov_centrale.coverage_months'
PARAM_MAX_COVERAGE = 'larov_centrale.max_coverage_months'
PARAM_HISTORY = 'larov_centrale.sales_history_months'
PARAM_BOTTLES_PER_CASE = 'larov_centrale.bottles_per_case'
PARAM_PRICELIST_CHR = 'larov_centrale.pricelist_chr_id'
PARAM_PRICELIST_TAKEAWAY = 'larov_centrale.pricelist_takeaway_id'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    larov_coverage_months = fields.Float(
        string="Couverture visée (mois)",
        help="Nombre de mois de vente que doit couvrir le stock après réception "
             "d'une commande fournisseur. Sert au stock d'alerte "
             "(vente mensuelle × couverture) et à la proposition de commande.",
    )
    larov_max_coverage_months = fields.Float(
        string="Couverture maximale à justifier (mois)",
        help="Au-delà de cette couverture après réception, la ligne de commande "
             "fournisseur est signalée et doit être justifiée.",
    )
    larov_sales_history_months = fields.Integer(
        string="Historique de vente (mois)",
        help="Nombre de mois glissants utilisés pour calculer la vente mensuelle "
             "moyenne d'un produit (caisse + ventes B2B).",
    )
    larov_bottles_per_case = fields.Integer(
        string="Bouteilles par carton (défaut)",
        help="Conditionnement par défaut proposé sur les commandes fournisseur.",
    )

    larov_pricelist_chr_id = fields.Many2one(
        'product.pricelist', string='Liste de prix CHR',
        help="Tarif appliqué aux restaurants, hôtels et bars (colonne « Prix CHR » de la fiche commerciale).",
    )
    larov_pricelist_takeaway_id = fields.Many2one(
        'product.pricelist', string='Liste de prix à emporter',
        help="Tarif boutique / particuliers (colonne « Prix à emporter »).",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        res.update(
            larov_pricelist_chr_id=int(icp.get_param(PARAM_PRICELIST_CHR, 0)) or False,
            larov_pricelist_takeaway_id=int(icp.get_param(PARAM_PRICELIST_TAKEAWAY, 0)) or False,
        )
        res.update(
            larov_coverage_months=float(icp.get_param(PARAM_COVERAGE, 4.0)),
            larov_max_coverage_months=float(icp.get_param(PARAM_MAX_COVERAGE, 6.0)),
            larov_sales_history_months=int(icp.get_param(PARAM_HISTORY, 3)),
            larov_bottles_per_case=int(icp.get_param(PARAM_BOTTLES_PER_CASE, 6)),
        )
        return res

    def set_values(self):
        super().set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(PARAM_COVERAGE, self.larov_coverage_months or 4.0)
        icp.set_param(PARAM_MAX_COVERAGE, self.larov_max_coverage_months or 6.0)
        icp.set_param(PARAM_HISTORY, self.larov_sales_history_months or 3)
        icp.set_param(PARAM_BOTTLES_PER_CASE, self.larov_bottles_per_case or 6)
        icp.set_param(PARAM_PRICELIST_CHR, self.larov_pricelist_chr_id.id or 0)
        icp.set_param(PARAM_PRICELIST_TAKEAWAY, self.larov_pricelist_takeaway_id.id or 0)


class LarovSettingsHelper(models.AbstractModel):
    """Accès centralisé aux paramètres LAROV depuis les autres modèles."""
    _name = 'larov.settings'
    _description = 'Paramètres LAROV (helper)'

    @api.model
    def coverage_months(self):
        return float(self.env['ir.config_parameter'].sudo().get_param(PARAM_COVERAGE, 4.0))

    @api.model
    def max_coverage_months(self):
        return float(self.env['ir.config_parameter'].sudo().get_param(PARAM_MAX_COVERAGE, 6.0))

    @api.model
    def sales_history_months(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(PARAM_HISTORY, 3))

    @api.model
    def bottles_per_case(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(PARAM_BOTTLES_PER_CASE, 6))

    @api.model
    def _pricelist(self, param):
        pl_id = int(self.env['ir.config_parameter'].sudo().get_param(param, 0) or 0)
        pricelist = self.env['product.pricelist'].browse(pl_id).exists() if pl_id else self.env['product.pricelist']
        return pricelist.filtered('active')

    @api.model
    def pricelist_chr(self):
        return self._pricelist(PARAM_PRICELIST_CHR)

    @api.model
    def pricelist_takeaway(self):
        return self._pricelist(PARAM_PRICELIST_TAKEAWAY)
