# -*- coding: utf-8 -*-
{
    'name': 'POS - Gestion simplifiée des stocks multi-magasins',
    'version': '1.0.0',
    'category': 'Point of Sale',
    'summary': 'Approvisionnement simplifié, alertes stock, disponibilité inter-magasins, dashboard transferts',
    'description': """
        Module de gestion simplifiée des stocks pour les réseaux de boutiques POS.

        Fonctionnalités :
        - F1 : Wizard d'approvisionnement simplifié (Central → Magasin)
        - F2 : Alertes automatiques quand le stock d'un magasin passe sous le seuil minimum
        - F3 : Disponibilité inter-magasins (rediriger un client vers un autre magasin)
        - F4 : Dashboard historique complet de tous les transferts inter-magasins
    """,
    'author': 'Djakaridja Traore (djakaridjatraore@outlook.com) +225 0759580627',
    'depends': ['stock', 'point_of_sale', 'mail', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template_data.xml',
        'wizard/store_replenishment_wizard_views.xml',
        'views/stock_warehouse_views.xml',
        'views/store_replenishment_dashboard_views.xml',
        'views/inter_store_availability_views.xml',
        'views/store_stock_report_views.xml',
        'views/store_stockout_forecast_views.xml',
        'views/pos_sale_margin_report_views.xml',
        'views/pos_order_margin_views.xml',
        'views/sale_order_views.xml',
        'views/pos_config_views.xml',
        'views/product_store_history_views.xml',
        'views/product_views.xml',
        'views/menuitems.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_store_replenishment/static/src/app/components/pos_compat_fix.js',
            'pos_store_replenishment/static/src/app/components/stock_availability/stock_availability_button.xml',
            'pos_store_replenishment/static/src/app/components/stock_availability/stock_availability_button.js',
            # stockout_alert désactivé : les produits à stock=0 ne sont plus
            # chargés dans le POS (filtre _load_pos_data_domain), l'alerte est inutile
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
