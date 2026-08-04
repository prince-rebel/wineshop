# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    can_edit_date_order_after_confirm = fields.Boolean(
        compute='_compute_can_edit_date_order_after_confirm',
        help="Réservé aux administrateurs : autorise la correction de la "
             "date de commande même après confirmation (les Sales Managers "
             "ne peuvent la modifier qu'avant confirmation).",
    )

    def _compute_can_edit_date_order_after_confirm(self):
        is_admin = self.env.user.has_group('base.group_system')
        for order in self:
            order.can_edit_date_order_after_confirm = is_admin

    def action_confirm(self):
        """
        Le cœur Odoo force systématiquement date_order = maintenant() à la
        confirmation (_prepare_confirmation_values), quelle que soit la date
        saisie manuellement avant (cf. vue view_order_form_editable_date qui
        ouvre ce champ aux Sales Managers pour la saisie rétroactive).

        On ne restaure la date manuelle QUE si elle diffère de create_date :
        tant que personne n'y a touché, date_order == create_date pendant
        tout le brouillon. Un écart entre les deux ne peut venir que d'une
        modification manuelle délibérée (nos Sales Managers) — dans ce cas
        on la préserve. Sinon, on laisse le comportement standard d'Odoo
        (date_order devient la date de confirmation), qui reste le bon
        réglage par défaut pour toutes les ventes normales.
        """
        manual_dates = {
            order.id: order.date_order
            for order in self
            if order.date_order and order.create_date and order.date_order != order.create_date
        }
        result = super().action_confirm()
        for order in self:
            manual_date = manual_dates.get(order.id)
            if manual_date:
                order.date_order = manual_date
        return result
