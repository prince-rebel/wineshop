# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ReportStockValuationLarov(models.AbstractModel):
    _name = 'report.larov_centrale.report_stock_valuation_larov'
    _description = "Inventaire en valeur (LAROV)"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['larov.stock.report.wizard'].browse(docids)
        Valuation = self.env['larov.stock.valuation.report']
        docs = []
        for wiz in wizards:
            matrix = Valuation._larov_matrix(
                warehouse_ids=wiz.warehouse_ids.ids or None,
                region_ids=wiz.region_ids.ids or None,
            )
            docs.append({'wizard': wiz, **matrix})
        return {
            'doc_ids': docids,
            'doc_model': 'larov.stock.report.wizard',
            'docs': docs,
            'company': self.env.company,
            'today': fields.Date.context_today(self),
        }


class ReportCommercialSheetLarov(models.AbstractModel):
    _name = 'report.larov_centrale.report_commercial_sheet_larov'
    _description = "Fiche commerciale (LAROV)"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['larov.stock.report.wizard'].browse(docids)
        docs = [{'wizard': wiz, 'products': wiz._get_products()} for wiz in wizards]
        return {
            'doc_ids': docids,
            'doc_model': 'larov.stock.report.wizard',
            'docs': docs,
            'company': self.env.company,
            'today': fields.Date.context_today(self),
            'settings': self.env['larov.settings'],
        }


class ReportReplenishmentLarov(models.AbstractModel):
    _name = 'report.larov_centrale.report_replenishment_larov'
    _description = "Rapport de réapprovisionnement (LAROV)"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['larov.stock.report.wizard'].browse(docids)
        docs = []
        for wiz in wizards:
            products = wiz._get_products()
            # Les produits à commander en premier, puis par couverture croissante
            products = products.sorted(key=lambda p: (p.suggested_order_qty <= 0, p.coverage_months))
            docs.append({'wizard': wiz, 'products': products})
        return {
            'doc_ids': docids,
            'doc_model': 'larov.stock.report.wizard',
            'docs': docs,
            'company': self.env.company,
            'today': fields.Date.context_today(self),
        }
