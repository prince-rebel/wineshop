# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_store_replenishment = fields.Boolean(
        string='Approvisionnement magasin',
        default=False,
        copy=False,
        help="Indique que ce transfert est un approvisionnement entre l'entrepôt central et un magasin POS."
    )
    store_replenishment_status = fields.Char(
        string='Statut',
        compute='_compute_store_replenishment_status',
        store=False,
    )
    dest_store_id = fields.Many2one(
        'stock.warehouse',
        string='Magasin destinataire',
        domain=[('is_pos_store', '=', True)],
        copy=False,
    )
    src_store_id = fields.Many2one(
        'stock.warehouse',
        string='Magasin source',
        copy=False,
    )
    is_pending_store_validation = fields.Boolean(
        string='En attente de confirmation',
        compute='_compute_is_pending_store_validation',
        store=True,
        help="Vrai si ce transfert est prêt et attend la confirmation de réception du magasin.",
    )
    store_direction_label = fields.Selection(
        [('in', 'Reçu'), ('out', 'Envoyé')],
        string='Sens',
        compute='_compute_store_direction_label',
        help="Calculé par rapport au magasin consulté (menu Historique — "
             "par magasin). Vide dans la vue 'Tous les magasins' où il n'y a "
             "pas un seul magasin de référence.",
    )

    validation_group = fields.Selection(
        [('to_validate', 'À valider'), ('validated', 'Déjà validé')],
        string='État',
        compute='_compute_validation_group',
        store=True,
        help="Sert uniquement à regrouper la liste : les opérations encore "
             "en attente de confirmation apparaissent avant celles déjà "
             "traitées.",
    )

    @api.depends('is_pending_store_validation')
    def _compute_validation_group(self):
        for picking in self:
            picking.validation_group = (
                'to_validate' if picking.is_pending_store_validation else 'validated'
            )

    @api.depends_context('focus_warehouse_id')
    def _compute_store_direction_label(self):
        focus_id = self.env.context.get('focus_warehouse_id')
        for picking in self:
            if not focus_id:
                picking.store_direction_label = False
            elif picking.dest_store_id.id == focus_id:
                picking.store_direction_label = 'in'
            elif picking.src_store_id.id == focus_id:
                picking.store_direction_label = 'out'
            else:
                picking.store_direction_label = False

    @api.depends('state')
    def _compute_is_pending_store_validation(self):
        for picking in self:
            picking.is_pending_store_validation = picking.state == 'assigned'

    @api.depends('state')
    def _compute_store_replenishment_status(self):
        state_map = {
            'draft':     _('Brouillon'),
            'waiting':   _('En attente d\'expédition'),
            'confirmed': _('En préparation'),
            'assigned':  _('Prêt à confirmer'),
            'done':      _('Reçu ✓'),
            'cancel':    _('Annulé'),
        }
        for picking in self:
            picking.store_replenishment_status = state_map.get(picking.state, picking.state)

    def button_validate(self):
        """
        Verrou central : quel que soit le point d'entrée utilisé pour valider
        un transfert (bouton natif Odoo "Valider" dans Inventaire, ou notre
        bouton "Confirmer la réception"), on empêche de réceptionner un
        approvisionnement magasin tant que l'expédition depuis le dépôt
        central n'est pas réellement terminée. Sans ce verrou au niveau du
        cœur Odoo, un utilisateur validant depuis l'écran standard des
        transferts contournait notre garde-fou et créait du stock fantôme
        (stock négatif en transit).
        """
        for picking in self:
            picking._check_store_reception_upstream_done()
        return super().button_validate()

    def _check_store_reception_upstream_done(self):
        self.ensure_one()
        if not (self.is_store_replenishment and self.dest_store_id):
            return
        pending_origin = self.move_ids.move_orig_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
        )
        if pending_origin:
            raise UserError(_(
                "Impossible de valider cette réception : l'expédition depuis le dépôt "
                "central n'est pas encore terminée (stock central insuffisant ou "
                "expédition non validée). Contactez le gestionnaire du dépôt central "
                "avant de confirmer cette réception."
            ))

    def action_confirm_store_reception(self):
        """
        Action simplifiée : le responsable du magasin confirme la réception
        en un seul clic depuis le dashboard ou la notification.

        Ne valide que la quantité réellement disponible (déjà calculée par la
        réservation Odoo sur `move.quantity`) : on ne force jamais la quantité
        à la demande initiale, pour ne jamais créer de stock qui n'a pas
        réellement transité par le dépôt central (stock négatif en transit).
        Le verrou anti-réception-prématurée est appliqué par button_validate()
        ci-dessus, quel que soit le chemin emprunté pour y arriver.
        """
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_("Cette réception a déjà été confirmée."))
        if self.state == 'cancel':
            raise UserError(_("Ce transfert a été annulé."))

        self.action_assign()
        self.with_context(skip_backorder=True).button_validate()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Réception confirmée'),
                'message': _('Le stock de %s a été mis à jour.') % self.dest_store_id.name,
                'type': 'success',
                'sticky': False,
            },
        }
