# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MultiStoreReplenishmentWizard(models.TransientModel):
    """
    F8 — Wizard de réapprovisionnement multi-magasins.
    L'utilisateur sélectionne les magasins à approvisionner,
    charge leurs besoins (ruptures détectées) et valide en un seul clic.
    """
    _name = 'multi.store.replenishment.wizard'
    _description = 'Réapprovisionnement de plusieurs magasins'

    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Magasins à approvisionner',
        domain=[('is_pos_store', '=', True)],
        required=True,
    )
    scheduled_date = fields.Date(
        string='Date prévue',
        default=fields.Date.today,
        required=True,
    )
    line_ids = fields.One2many(
        'multi.store.replenishment.line',
        'wizard_id',
        string='Produits à envoyer',
    )
    total_stores = fields.Integer(
        string='Magasins concernés',
        compute='_compute_totals',
    )
    total_lines = fields.Integer(
        string='Lignes actives',
        compute='_compute_totals',
    )

    @api.depends('line_ids', 'line_ids.qty_to_send')
    def _compute_totals(self):
        for wizard in self:
            active = wizard.line_ids.filtered(lambda l: l.qty_to_send > 0)
            wizard.total_lines = len(active)
            wizard.total_stores = len(active.mapped('dest_warehouse_id'))

    def action_load_needs(self):
        """
        Charge les besoins pour les magasins sélectionnés.
        - Si des seuils min/max sont configurés : affiche les produits en rupture
          avec la quantité suggérée pré-remplie.
        - Sinon : affiche tous les produits disponibles au central
          pour que l'utilisateur saisisse les quantités manuellement.
        """
        self.ensure_one()
        if not self.warehouse_ids:
            raise UserError(_("Veuillez sélectionner au moins un magasin."))

        self.line_ids = [(5, 0, 0)]
        lines = []

        for warehouse in self.warehouse_ids:
            # Entrepôt central pour ce magasin
            central = warehouse.central_warehouse_id
            if not central:
                central = self.env['stock.warehouse'].search([
                    ('is_pos_store', '=', False),
                    ('company_id', '=', warehouse.company_id.id),
                ], limit=1)

            if not central:
                continue

            # Construire un index des orderpoints pour ce magasin
            orderpoints = self.env['stock.warehouse.orderpoint'].search([
                ('warehouse_id', '=', warehouse.id),
            ])
            op_by_product = {op.product_id.id: op for op in orderpoints}

            if orderpoints:
                # Mode ruptures : on liste les produits avec un seuil configuré
                products_to_show = orderpoints.mapped('product_id')
            else:
                # Mode manuel : on liste les produits disponibles au central
                src_quants = self.env['stock.quant'].search([
                    ('location_id', '=', central.lot_stock_id.id),
                    ('quantity', '>', 0),
                ])
                products_to_show = src_quants.mapped('product_id')

            for product in products_to_show:
                op = op_by_product.get(product.id)

                # Stock actuel du magasin
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', warehouse.lot_stock_id.id),
                ])
                qty_on_hand = sum(quants.mapped('quantity'))

                # Stock central disponible
                src_quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', central.lot_stock_id.id),
                ])
                src_qty = sum(src_quants.mapped('quantity'))

                qty_min = op.product_min_qty if op else 0.0
                qty_max = op.product_max_qty if op else 0.0
                is_below = qty_on_hand < qty_min if op else False

                # Quantité suggérée
                if op and is_below:
                    qty_suggested = max((qty_max or qty_min) - qty_on_hand, 0)
                else:
                    qty_suggested = 0.0

                lines.append((0, 0, {
                    'dest_warehouse_id': warehouse.id,
                    'src_warehouse_id': central.id,
                    'product_id': product.id,
                    'product_uom_id': product.uom_id.id,
                    'qty_on_hand': qty_on_hand,
                    'qty_min': qty_min,
                    'qty_max': qty_max,
                    'qty_available_src': src_qty,
                    'qty_to_send': qty_suggested,
                    'is_below_min': is_below,
                }))

        if not lines:
            raise UserError(_(
                "Aucun produit trouvé pour les magasins sélectionnés.\n"
                "Vérifiez que l'entrepôt central a du stock ou que des produits "
                "sont disponibles dans le système."
            ))

        self.line_ids = lines

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'views': [(False, 'form')],
        }

    def action_validate_all(self):
        """Valide tous les réapprovisionnements avec qty_to_send > 0."""
        self.ensure_one()
        lines_to_process = self.line_ids.filtered(lambda l: l.qty_to_send > 0)
        if not lines_to_process:
            raise UserError(_("Aucune quantité à envoyer. Ajustez les lignes."))

        warehouses = lines_to_process.mapped('dest_warehouse_id')

        for warehouse in warehouses:
            wh_lines = lines_to_process.filtered(lambda l: l.dest_warehouse_id == warehouse)
            src_warehouse = wh_lines[0].src_warehouse_id
            if not src_warehouse:
                continue

            route = self.env['stock.route'].search([
                ('supplied_wh_id', '=', warehouse.id),
                ('supplier_wh_id', '=', src_warehouse.id),
            ], limit=1)
            if not route:
                route = self.env['stock.route'].search([
                    ('supplied_wh_id', '=', warehouse.id),
                ], limit=1)
            if not route:
                continue

            origin = 'MultiAppro/%s/%s' % (
                warehouse.code,
                fields.Date.today().strftime('%d%m%y'),
            )

            procurements = []
            for line in wh_lines:
                values = {
                    'route_ids': route,
                    'date_planned': self.scheduled_date,
                    'warehouse_id': warehouse,
                    'company_id': self.env.company,
                }
                procurements.append(
                    self.env['stock.rule'].Procurement(
                        line.product_id,
                        line.qty_to_send,
                        line.product_uom_id,
                        warehouse.lot_stock_id,
                        line.product_id.display_name,
                        origin,
                        self.env.company,
                        values,
                    )
                )

            self.env['stock.rule'].run(procurements)
            self.env.flush_all()

            new_pickings = self.env['stock.picking'].search([
                ('origin', '=', origin),
                ('state', 'not in', ['done', 'cancel']),
            ], order='id asc')

            new_pickings.write({
                'is_store_replenishment': True,
                'dest_store_id': warehouse.id,
                'src_store_id': src_warehouse.id,
            })

            outgoing = new_pickings.filtered(
                lambda p: p.location_id.warehouse_id == src_warehouse
            )
            reception = new_pickings.filtered(
                lambda p: p.location_dest_id.id == warehouse.lot_stock_id.id
            )

            for picking in outgoing:
                for move in picking.move_ids:
                    move.quantity = move.product_uom_qty
                try:
                    picking.with_context(skip_backorder=True).button_validate()
                except Exception:
                    picking.action_assign()

            wizard_single = self.env['store.replenishment.wizard'].new({
                'dest_warehouse_id': warehouse.id,
                'source_warehouse_id': src_warehouse.id,
            })
            wizard_single._notify_store_reception_ready(reception)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Réapprovisionnement groupé validé'),
                'message': _(
                    '%(stores)s magasin(s) réapprovisionnés. '
                    'Les responsables ont été notifiés.'
                ) % {'stores': len(warehouses)},
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class MultiStoreReplenishmentLine(models.TransientModel):
    _name = 'multi.store.replenishment.line'
    _description = 'Ligne de réapprovisionnement multi-magasins'
    _order = 'dest_warehouse_id, product_id'

    wizard_id = fields.Many2one('multi.store.replenishment.wizard', required=True, ondelete='cascade')
    dest_warehouse_id = fields.Many2one('stock.warehouse', string='Magasin', readonly=True)
    src_warehouse_id = fields.Many2one('stock.warehouse', string='Depuis', readonly=True)
    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unité', readonly=True)
    qty_on_hand = fields.Float(string='Stock magasin', readonly=True, digits='Product Unit')
    qty_min = fields.Float(string='Seuil min', readonly=True, digits='Product Unit')
    qty_max = fields.Float(string='Seuil max', readonly=True, digits='Product Unit')
    qty_available_src = fields.Float(string='Stock central', readonly=True, digits='Product Unit')
    qty_to_send = fields.Float(string='À envoyer', digits='Product Unit')
    is_below_min = fields.Boolean(string='En rupture', readonly=True)
