# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import AccessError

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

    def action_generate_missing_reference(self):
        """Attribue une référence interne aux produits sélectionnés qui n'en ont pas,
        dans l'ordre de création. Les produits ayant déjà une référence sont ignorés."""
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_("Seul un administrateur Inventaire peut générer les références."))

        sequence = self.env['ir.sequence']
        templates = self.filtered(lambda t: not t.default_code).sorted(
            key=lambda t: (t.create_date, t.id))

        done = 0
        for template in templates:
            variants = template.with_context(active_test=False).product_variant_ids
            if len(variants) <= 1:
                template.default_code = sequence.next_by_code(SEQUENCE_CODE)
                done += 1
            else:
                for variant in variants.filtered(lambda v: not v.default_code):
                    variant.default_code = sequence.next_by_code(SEQUENCE_CODE)
                    done += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Références générées"),
                'message': _("%(done)s référence(s) attribuée(s), %(skipped)s produit(s) déjà référencé(s).",
                             done=done, skipped=len(self) - len(templates)),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
