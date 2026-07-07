# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_hide_out_of_stock_products = fields.Boolean(
        related='pos_config_id.hide_out_of_stock_products',
        readonly=False,
        string='Masquer les produits en rupture de stock',
    )
