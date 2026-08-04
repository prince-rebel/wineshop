# -*- coding: utf-8 -*-
from odoo import api, models

SEQUENCE_CODE = 'product.template.reference'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if not vals.get('default_code'):
                vals['default_code'] = sequence.next_by_code(SEQUENCE_CODE)
        return super().create(vals_list)
