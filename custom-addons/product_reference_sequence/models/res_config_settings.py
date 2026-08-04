# -*- coding: utf-8 -*-
from odoo import api, fields, models

SEQUENCE_CODE = 'product.template.reference'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    product_reference_prefix = fields.Char(string="Préfixe de référence produit")
    product_reference_padding = fields.Integer(string="Nombre de chiffres")
    product_reference_next_number = fields.Integer(string="Prochain numéro")

    @api.model
    def get_values(self):
        res = super().get_values()
        sequence = self.env['ir.sequence'].search([('code', '=', SEQUENCE_CODE)], limit=1)
        res.update({
            'product_reference_prefix': sequence.prefix or '',
            'product_reference_padding': sequence.padding or 4,
            'product_reference_next_number': sequence.number_next_actual or 1,
        })
        return res

    def set_values(self):
        super().set_values()
        sequence = self.env['ir.sequence'].search([('code', '=', SEQUENCE_CODE)], limit=1)
        if sequence:
            sequence.write({
                'prefix': self.product_reference_prefix or '',
                'padding': self.product_reference_padding or 4,
            })
            # number_next_actual (pas number_next) : pour une séquence
            # 'standard', le compteur réel vit dans une séquence PostgreSQL
            # native, pas dans la colonne number_next de la table ir_sequence.
            # Passer par ce champ calculé déclenche bien l'ALTER SEQUENCE.
            if self.product_reference_next_number:
                sequence.number_next_actual = self.product_reference_next_number
