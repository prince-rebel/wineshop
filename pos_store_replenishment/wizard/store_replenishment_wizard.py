# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date


class StoreReplenishmentWizard(models.TransientModel):
    """
    Wizard simplifié pour approvisionner un magasin POS depuis l'entrepôt central.
    L'utilisateur choisit uniquement le magasin et les quantités.
    Toute la logique technique (routes, pickings, transit) est transparente.
    """
    _name = 'store.replenishment.wizard'
    _description = 'Approvisionnement magasin POS'

    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Magasin à approvisionner',
        required=True,
        domain=[('is_pos_store', '=', True)],
    )
    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Entrepôt source',
        compute='_compute_source_warehouse',
        store=True,
        readonly=False,
        help="Pré-rempli depuis la configuration du magasin (entrepôt central), "
             "mais modifiable si vous voulez approvisionner depuis un autre entrepôt.",
    )
    source_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        compute='_compute_source_warehouse_ids',
        string='Entrepôts source disponibles',
        help="Entrepôts ayant une route de réapprovisionnement configurée vers "
             "le magasin choisi. Sert à restreindre les choix possibles.",
    )
    line_ids = fields.One2many(
        'store.replenishment.wizard.line',
        'wizard_id',
        string='Produits à envoyer',
    )
    note = fields.Text(string='Remarques')
    scheduled_date = fields.Date(
        string='Date prévue',
        default=fields.Date.today,
        required=True,
    )

    @api.depends('dest_warehouse_id')
    def _compute_source_warehouse(self):
        for wizard in self:
            if wizard.dest_warehouse_id and wizard.dest_warehouse_id.central_warehouse_id:
                wizard.source_warehouse_id = wizard.dest_warehouse_id.central_warehouse_id
            else:
                # Fallback : premier entrepôt non-magasin de la société
                wizard.source_warehouse_id = self.env['stock.warehouse'].search([
                    ('is_pos_store', '=', False),
                    ('company_id', '=', self.env.company.id),
                ], limit=1)

    @api.depends('dest_warehouse_id')
    def _compute_source_warehouse_ids(self):
        for wizard in self:
            if wizard.dest_warehouse_id:
                routes = self.env['stock.route'].search([
                    ('supplied_wh_id', '=', wizard.dest_warehouse_id.id),
                ])
                wizard.source_warehouse_ids = routes.mapped('supplier_wh_id')
            else:
                wizard.source_warehouse_ids = False

    @api.onchange('dest_warehouse_id')
    def _onchange_dest_warehouse(self):
        """Pré-charger les produits disponibles avec leur stock respectif."""
        self.line_ids = [(5, 0, 0)]
        if not self.dest_warehouse_id:
            return
        # Charger les produits qui ont du stock au central OU un seuil min configuré au magasin
        orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('warehouse_id', '=', self.dest_warehouse_id.id),
        ])
        lines = []
        for op in orderpoints:
            lines.append((0, 0, {
                'product_id': op.product_id.id,
                'product_uom_id': op.product_uom.id,
                'qty_min': op.product_min_qty,
                'qty_max': op.product_max_qty,
            }))
        self.line_ids = lines

    def _get_resupply_route(self):
        """
        Trouve la route de réapprovisionnement Source → Magasin.

        Pas de fallback sur "n'importe quelle route vers ce magasin" : un tel
        fallback ignorerait silencieusement l'entrepôt source choisi par
        l'utilisateur et expédierait depuis un autre entrepôt (typiquement le
        dépôt central) sans le prévenir. Si aucune route n'existe pour la
        paire choisie, action_validate() lève une erreur claire à la place.
        """
        self.ensure_one()
        return self.env['stock.route'].search([
            ('supplied_wh_id', '=', self.dest_warehouse_id.id),
            ('supplier_wh_id', '=', self.source_warehouse_id.id),
        ], limit=1)

    def action_validate(self):
        """
        Flux simplifié en 2 étapes :
        1. Le gestionnaire central valide le wizard → WH/OUT validé automatiquement
           pour la quantité réellement disponible (stock central déduit immédiatement,
           jamais au-delà de ce qui existe réellement : un manque de stock central crée
           un reliquat en attente au lieu d'expédier une quantité fictive).
        2. Le responsable du magasin reçoit une notification avec 1 bouton
           "Confirmer la réception" → stock magasin mis à jour — uniquement pour les
           envois dont l'expédition centrale est réellement terminée.
        """
        self.ensure_one()

        lines_to_process = self.line_ids.filtered(lambda l: l.qty_to_send > 0)
        if not lines_to_process:
            raise UserError(_("Veuillez saisir au moins une quantité à envoyer."))

        if not self.source_warehouse_id:
            raise UserError(_("Aucun entrepôt central trouvé. Veuillez configurer l'entrepôt central sur le magasin."))

        route = self._get_resupply_route()
        if not route:
            raise UserError(_(
                "Aucune route de réapprovisionnement trouvée entre '%s' et '%s'.\n"
                "Configurez la route dans Inventaire > Configuration > Entrepôts "
                "(onglet 'Se réapprovisionner depuis')."
            ) % (self.source_warehouse_id.name, self.dest_warehouse_id.name))

        # Référence unique pour retrouver les pickings créés
        origin = 'Appro/%s/%s' % (
            self.dest_warehouse_id.code,
            fields.Date.today().strftime('%d%m%y'),
        )

        # Créer les procurements via le moteur de règles Odoo
        procurements = []
        for line in lines_to_process:
            values = {
                'route_ids': route,
                'date_planned': self.scheduled_date,
                'warehouse_id': self.dest_warehouse_id,
                'company_id': self.env.company,
            }
            procurements.append(
                self.env['stock.rule'].Procurement(
                    line.product_id,
                    line.qty_to_send,
                    line.product_uom_id,
                    self.dest_warehouse_id.lot_stock_id,
                    line.product_id.display_name,
                    origin,
                    self.env.company,
                    values,
                )
            )

        self.env['stock.rule'].run(procurements)
        self.env.flush_all()

        # Récupérer les pickings créés par cet approvisionnement
        new_pickings = self.env['stock.picking'].search([
            ('origin', '=', origin),
            ('state', 'not in', ['done', 'cancel']),
        ], order='id asc')

        new_pickings.write({
            'is_store_replenishment': True,
            'dest_store_id': self.dest_warehouse_id.id,
            'src_store_id': self.source_warehouse_id.id,
            'note': self.note or '',
        })

        # Séparer picking sortie (central) et picking réception (magasin)
        outgoing_picking = new_pickings.filtered(
            lambda p: p.location_id.warehouse_id == self.source_warehouse_id
        )
        reception_picking = new_pickings.filtered(
            lambda p: p.location_dest_id.id == self.dest_warehouse_id.lot_stock_id.id
        )

        # ── ÉTAPE 1 : valider automatiquement l'expédition centrale ──────────
        # On ne force JAMAIS move.quantity au-delà de ce qu'Odoo a réellement
        # réservé (move.quantity reflète déjà le stock disponible). Si le stock
        # central est insuffisant, seule la quantité disponible est expédiée et
        # Odoo crée automatiquement un reliquat (backorder) pour le solde.
        if outgoing_picking:
            outgoing_picking.action_assign()
            outgoing_picking.with_context(skip_backorder=True).button_validate()

        self.env.flush_all()

        # ── ÉTAPE 2 : notifier le responsable du magasin ─────────────────────
        # La réception est maintenant "Prêt" — un seul clic suffit pour confirmer.
        # On ne notifie que les réceptions dont l'expédition centrale est
        # effectivement terminée : jamais de notification pour un envoi bloqué
        # ou partiel, pour ne jamais laisser confirmer une réception fantôme.
        ready_for_reception = reception_picking.filtered(
            lambda p: not p.move_ids.move_orig_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        )
        self._notify_store_reception_ready(ready_for_reception)

        blocked_reception = reception_picking - ready_for_reception
        if blocked_reception:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Approvisionnement incomplet'),
                    'message': _(
                        'Stock central insuffisant : l\'expédition vers %(store)s n\'a pu être '
                        'complétée. Le solde restera en attente jusqu\'au réapprovisionnement '
                        'du dépôt central.'
                    ) % {'store': self.dest_warehouse_id.name},
                    'type': 'warning',
                    'sticky': True,
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Approvisionnement expédié'),
                'message': _(
                    '%(qty)s article(s) expédiés vers %(store)s. '
                    'Le responsable du magasin a été notifié pour confirmer la réception.'
                ) % {
                    'qty': len(lines_to_process),
                    'store': self.dest_warehouse_id.name,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _notify_store_reception_ready(self, reception_pickings):
        """
        Envoie une notification mail.activity au responsable du magasin
        avec un lien direct vers le picking de réception.
        1 clic depuis la notification → confirme la réception.
        """
        store = self.dest_warehouse_id
        responsible = store.responsible_user_id
        if not responsible or not reception_pickings:
            return

        for picking in reception_pickings:
            # Lien direct vers le picking de réception
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            picking_url = '%s/odoo/inventory/picking-type-all/%s' % (base_url, picking.id)

            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get_id('stock.picking'),
                'res_id': picking.id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'user_id': responsible.id,
                'summary': _('Réception à confirmer — %s') % store.name,
                'note': _(
                    'Un approvisionnement de <b>%(count)s produit(s)</b> a été expédié '
                    'depuis <b>%(src)s</b> vers <b>%(dest)s</b>.<br/><br/>'
                    'Merci de confirmer la réception en cliquant sur '
                    '<a href="%(url)s"><b>Confirmer la réception</b></a>.'
                ) % {
                    'count': len(picking.move_ids),
                    'src': self.source_warehouse_id.name,
                    'dest': store.name,
                    'url': picking_url,
                },
            })


class StoreReplenishmentWizardLine(models.TransientModel):
    """Ligne du wizard : un produit avec ses quantités."""
    _name = 'store.replenishment.wizard.line'
    _description = 'Ligne d\'approvisionnement magasin'

    wizard_id = fields.Many2one('store.replenishment.wizard', required=True, ondelete='cascade')

    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True,
        domain=[('type', '=', 'consu')],
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unité',
        related='product_id.uom_id',
    )
    qty_available_src = fields.Float(
        string='Stock central',
        compute='_compute_qty',
        digits='Product Unit',
    )
    qty_available_dst = fields.Float(
        string='Stock magasin',
        compute='_compute_qty',
        digits='Product Unit',
    )
    qty_min = fields.Float(string='Seuil min', digits='Product Unit')
    qty_max = fields.Float(string='Seuil max', digits='Product Unit')
    qty_to_send = fields.Float(
        string='Quantité à envoyer',
        digits='Product Unit',
        default=0.0,
    )
    alert = fields.Boolean(
        string='En rupture',
        compute='_compute_qty',
        help="Vrai si le stock du magasin est sous le seuil minimum.",
    )

    @api.depends('product_id', 'wizard_id.dest_warehouse_id', 'wizard_id.source_warehouse_id')
    def _compute_qty(self):
        for line in self:
            line.qty_available_src = 0.0
            line.qty_available_dst = 0.0
            line.alert = False

            if not line.product_id:
                continue

            wizard = line.wizard_id

            # Stock entrepôt central
            if wizard.source_warehouse_id:
                src_quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', wizard.source_warehouse_id.lot_stock_id.id),
                ])
                line.qty_available_src = sum(src_quants.mapped('quantity'))

            # Stock magasin destinataire
            if wizard.dest_warehouse_id:
                dst_quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', wizard.dest_warehouse_id.lot_stock_id.id),
                ])
                line.qty_available_dst = sum(dst_quants.mapped('quantity'))
                line.alert = line.qty_available_dst < line.qty_min

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Pré-remplir la quantité à envoyer = max - stock actuel magasin."""
        if self.product_id and self.wizard_id.dest_warehouse_id:
            self._compute_qty()
            if self.qty_max > 0 and self.qty_available_dst < self.qty_max:
                self.qty_to_send = self.qty_max - self.qty_available_dst
