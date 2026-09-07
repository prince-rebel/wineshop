# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class LarovStockReportWizard(models.TransientModel):
    """Point d'entrée unique des états de stock LAROV.

    - Inventaire en valeur   : quantité × CMUP, dépôts en colonnes, synthèses
    - Fiche commerciale      : stock dispo, prix CHR / à emporter, arrivage en cours
    - Réapprovisionnement    : vente mensuelle, stock d'alerte, estimation rupture,
                               arrivage en cours, proposition de commande
    Chaque état s'ouvre à l'écran (liste / pivot) ou s'imprime en PDF.
    """
    _name = 'larov.stock.report.wizard'
    _description = 'États de stock LAROV'

    report_type = fields.Selection([
        ('valuation', 'Inventaire en valeur'),
        ('commercial', 'Fiche commerciale'),
        ('replenishment', 'Rapport de réapprovisionnement'),
    ], string='État', required=True, default='valuation')
    warehouse_ids = fields.Many2many(
        'stock.warehouse', string='Établissements',
        help="Vide = tous les établissements.",
    )
    region_ids = fields.Many2many('larov.wine.region', string='Régions')
    categ_ids = fields.Many2many('product.category', string='Catégories')
    only_wines = fields.Boolean(string='Vins uniquement', default=True)
    history_months = fields.Integer(
        string='Historique de vente (mois)',
        default=lambda self: self.env['larov.settings'].sales_history_months(),
    )
    coverage_months = fields.Float(
        string='Couverture visée (mois)',
        default=lambda self: self.env['larov.settings'].coverage_months(), digits=(16, 1),
    )
    include_zero_stock = fields.Boolean(
        string='Inclure les produits sans stock', default=False,
        help="Fiche commerciale / réappro : afficher aussi les références en rupture.",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _product_domain(self):
        self.ensure_one()
        domain = [('sale_ok', '=', True), ('type', '=', 'consu')]
        if self.only_wines:
            domain.append(('is_wine', '=', True))
        if self.region_ids:
            domain.append(('wine_region_id', 'in', self.region_ids.ids))
        if self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))
        if not self.include_zero_stock:
            domain.append(('qty_available', '>', 0))
        return domain

    def _product_context(self):
        self.ensure_one()
        ctx = dict(self.env.context,
                   larov_history_months=self.history_months or None,
                   larov_coverage_months=self.coverage_months or None)
        if len(self.warehouse_ids) == 1:
            ctx['warehouse_id'] = self.warehouse_ids.id
        elif self.warehouse_ids:
            ctx['warehouse_id'] = self.warehouse_ids.ids
        return ctx

    def _get_products(self):
        self.ensure_one()
        products = self.env['product.product'].with_context(self._product_context()).search(
            self._product_domain(), order='default_code, name',
        )
        return products

    # ------------------------------------------------------------------
    # Actions écran
    # ------------------------------------------------------------------
    def action_open(self):
        self.ensure_one()
        if self.report_type == 'valuation':
            action = self.env['ir.actions.act_window']._for_xml_id('larov_centrale.action_larov_stock_valuation_report')
            domain = []
            if self.warehouse_ids:
                domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
            if self.region_ids:
                domain.append(('wine_region_id', 'in', self.region_ids.ids))
            if self.categ_ids:
                domain.append(('categ_id', 'child_of', self.categ_ids.ids))
            action['domain'] = domain
            return action
        xmlid = ('larov_centrale.action_larov_commercial_sheet' if self.report_type == 'commercial'
                 else 'larov_centrale.action_larov_replenishment_report')
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['domain'] = self._product_domain()
        action['context'] = self._product_context()
        return action

    # ------------------------------------------------------------------
    # Impression PDF
    # ------------------------------------------------------------------
    def action_print(self):
        self.ensure_one()
        report_xmlid = {
            'valuation': 'larov_centrale.action_report_stock_valuation_larov',
            'commercial': 'larov_centrale.action_report_commercial_sheet_larov',
            'replenishment': 'larov_centrale.action_report_replenishment_larov',
        }[self.report_type]
        return self.env.ref(report_xmlid).report_action(self)
