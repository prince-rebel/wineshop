# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockWarehouseOrderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    def _notify_store_low_stock(self):
        """
        Envoie une alerte (mail.activity + email) quand le stock d'un magasin POS
        passe sous le seuil minimum.
        Appelé par le scheduler après chaque fermeture de session POS.
        """
        for orderpoint in self.filtered(
            lambda op: op.warehouse_id.is_pos_store
            and op.qty_on_hand < op.product_min_qty
        ):
            store = orderpoint.warehouse_id
            product = orderpoint.product_id

            # --- Activité sur le responsable du magasin ---
            if store.responsible_user_id:
                self.env['mail.activity'].create({
                    'res_model_id': self.env['ir.model']._get_id('stock.warehouse.orderpoint'),
                    'res_id': orderpoint.id,
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'user_id': store.responsible_user_id.id,
                    'summary': _('Rupture de stock — %s') % store.name,
                    'note': _(
                        'Le stock de <b>%(product)s</b> dans <b>%(store)s</b> est passé sous '
                        'le seuil minimum.<br/>'
                        'Stock actuel : <b>%(qty)s %(uom)s</b> '
                        '(minimum : %(min_qty)s %(uom)s)'
                    ) % {
                        'product': product.display_name,
                        'store': store.name,
                        'qty': orderpoint.qty_on_hand,
                        'min_qty': orderpoint.product_min_qty,
                        'uom': orderpoint.product_uom.name,
                    },
                })

            # --- Email au gestionnaire de l'entrepôt central ---
            central = store.central_warehouse_id
            if central and central.partner_id and central.partner_id.email:
                template = self.env.ref(
                    'pos_store_replenishment.mail_template_low_stock_alert',
                    raise_if_not_found=False
                )
                if template:
                    template.send_mail(orderpoint.id, force_send=True)

    @api.model
    def _procure_orderpoint_confirm(self, use_new_cursor=False, company_id=False, raise_user_error=True):
        """
        Override pour déclencher les alertes stock bas sur les magasins POS
        après l'exécution normale du scheduler.
        """
        result = super()._procure_orderpoint_confirm(
            use_new_cursor=use_new_cursor,
            company_id=company_id,
            raise_user_error=raise_user_error,
        )
        # Alertes uniquement sur les magasins POS
        store_orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('warehouse_id.is_pos_store', '=', True),
        ])
        store_orderpoints._notify_store_low_stock()
        return result
