# -*- coding: utf-8 -*-
{
    'name': 'Référence produit automatique',
    'version': '1.0.0',
    'category': 'Inventory',
    'summary': "Génère automatiquement la référence interne des nouveaux produits",
    'description': """
        Remplit automatiquement le champ Référence interne (default_code) des
        nouveaux produits, si l'utilisateur ne l'a pas renseigné lui-même.
        Le préfixe et le nombre de chiffres sont configurables directement
        depuis Réglages > Inventaire.
    """,
    'author': 'Djakaridja Traore',
    'depends': ['stock'],
    'data': [
        'data/ir_sequence_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
