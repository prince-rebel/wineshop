# -*- coding: utf-8 -*-
{
    'name': 'LAROV — Gestion de la Centrale (Route des vins)',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': "Achats & import, stock multi-établissements, coût de revient, "
               "pilotage commercial, encours clients et documents LAROV",
    'description': """
Extension Odoo pour la Centrale LAROV (avenant AV-2026-01).

Lot 1 — Achats, stock multi-établissements & seuils
Lot 2 — Coût de revient & valorisation du stock (CMUP, coûts logistiques)
Lot 3 — Pilotage commercial & reporting (encours, proforma, BL, CA)
Lot 4 — CRM & fidélisation

Documents imprimables au format LAROV :
 - Bon de commande fournisseur, Bon de réception d'arrivage
 - Bon de commande client, Proforma, Bon de livraison
 - Bon de mouvement de stock (A4 + ticket)
 - Relevé d'échéances client (balance âgée), Encours clients
 - Inventaire en valeur, Fiche commerciale, Rapport de réapprovisionnement
    """,
    'author': 'Djakaridja Traore',
    'website': 'https://www.larov-glb.com',
    'license': 'LGPL-3',
    'depends': [
        # existant
        'pos_store_replenishment',
        'product_reference_sequence',
        # Lot 1 — achats & stock multi-établissements
        'purchase',
        'purchase_stock',
        # Lot 2 — valorisation & coûts logistiques
        'stock_account',
        'stock_landed_costs',
        # Lot 3 — ventes, facturation, marges
        'sale_management',
        'sale_stock',
        'sale_margin',
        'account',
        # Lot 4 — CRM & fidélisation
        'crm',
        'sale_crm',
        'loyalty',
        'pos_loyalty',
        'sale_loyalty',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'data/ir_sequence_data.xml',
        'data/larov_wine_region_data.xml',
        'data/larov_commercial_zone_data.xml',
        'views/res_config_settings_views.xml',
        'views/larov_wine_region_views.xml',
        'views/larov_commercial_zone_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/stock_warehouse_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/sale_order_views.xml',
        'views/larov_stock_report_views.xml',
        'views/larov_customer_outstanding_views.xml',
        'views/menuitems.xml',
        'report/larov_report_common.xml',
        'report/purchase_order_report.xml',
        'report/stock_reception_report.xml',
        'report/sale_order_report.xml',
        'report/stock_delivery_report.xml',
        'report/stock_move_report.xml',
        'report/stock_reports_templates.xml',
        'report/customer_outstanding_report.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'larov_centrale/static/src/scss/larov_report.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
