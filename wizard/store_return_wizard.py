# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StoreReturnWizard(models.TransientModel):
    """
    F5 — Wizard de retour de stock magasin → central.
    Permet à un magasin POS de renvoyer du stock excédentaire ou invendu
    vers l'entrepôt central, en un minimum de clics.
    """
    _name = 'store.return.wizard'
    _description = 'Retour de stock magasin vers central'

    src_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Magasin source',
        required=True,
        domain=[('is_pos_store', '=', True)],
    )
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Entrepôt central destinataire',
        compute='_compute_dest_warehouse',
        store=True,
    )
    line_ids = fields.One2many(
        'store.return.wizard.line',
        'wizard_id',
        string='Produits à retourner',
    )
    note = fields.Text(string='Motif du retour')
    scheduled_date = fields.Date(
        string='Date prévue',
        default=fields.Date.today,
        required=True,
    )

    @api.depends('src_warehouse_id')
    def _compute_dest_warehouse(self):
        for wizard in self:
            if wizard.src_warehouse_id and wizard.src_warehouse_id.central_warehouse_id:
                wizard.dest_warehouse_id = wizard.src_warehouse_id.central_warehouse_id
            else:
                wizard.dest_warehouse_id = self.env['stock.warehouse'].search([
                    ('is_pos_store', '=', False),
                    ('company_id', '=', self.env.company.id),
                ], limit=1)

    @api.onchange('src_warehouse_id')
    def _onchange_src_warehouse(self):
        """Charger les produits disponibles dans ce magasin."""
        self.line_ids = [(5, 0, 0)]
        if not self.src_warehouse_id:
            return
        # child_of inclut lot_stock_id et toutes ses sous-locations
        quants = self.env['stock.quant'].search([
            ('location_id', 'child_of', self.src_warehouse_id.lot_stock_id.id),
            ('quantity', '>', 0),
        ])
        # Agréger par produit : un produit peut avoir plusieurs quants
        # (par lot, package, sous-emplacement ou historique d'ajustements)
        product_qtys = {}
        for quant in quants:
            pid = quant.product_id.id
            if pid not in product_qtys:
                product_qtys[pid] = {'product_id': quant.product_id, 'qty': 0.0}
            product_qtys[pid]['qty'] += quant.quantity
        lines = []
        for pid, data in product_qtys.items():
            lines.append((0, 0, {
                'product_id': pid,
                'product_uom_id': data['product_id'].uom_id.id,
                'qty_available': data['qty'],
                'qty_to_return': 0.0,
            }))
        self.line_ids = lines

    def action_validate(self):
        """
        Crée un transfert magasin → central et le valide immédiatement.
        Le stock du magasin est déduit instantanément.
        """
        self.ensure_one()

        lines_to_process = self.line_ids.filtered(lambda l: l.qty_to_return > 0)
        if not lines_to_process:
            raise UserError(_("Veuillez saisir au moins une quantité à retourner."))

        if not self.dest_warehouse_id:
            raise UserError(_("Aucun entrepôt central trouvé pour ce magasin."))

        for line in lines_to_process:
            # Re-interroger le stock réel au moment de la validation
            # child_of inclut lot_stock_id et toutes ses sous-locations
            fresh_quants = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id', 'child_of', self.src_warehouse_id.lot_stock_id.id),
            ])
            actual_qty = sum(fresh_quants.mapped('quantity'))
            if line.qty_to_return > actual_qty:
                raise UserError(_(
                    "La quantité à retourner pour '%s' (%s) dépasse le stock disponible (%s)."
                ) % (line.product_id.display_name, line.qty_to_return, actual_qty))

        origin = 'Retour/%s/%s' % (
            self.src_warehouse_id.code,
            fields.Date.today().strftime('%d%m%y'),
        )

        # Trouver le picking type de sortie du magasin
        out_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id', '=', self.src_warehouse_id.id),
        ], limit=1)

        if not out_type:
            raise UserError(_(
                "Aucun type d'opération de sortie trouvé pour le magasin '%s'."
            ) % self.src_warehouse_id.name)

        # Destination : stock de l'entrepôt central
        dest_location = self.dest_warehouse_id.lot_stock_id

        picking_vals = {
            'picking_type_id': out_type.id,
            'location_id': self.src_warehouse_id.lot_stock_id.id,
            'location_dest_id': dest_location.id,
            'origin': origin,
            'scheduled_date': self.scheduled_date,
            'note': self.note or '',
            'is_store_replenishment': True,
            'src_store_id': self.src_warehouse_id.id,
            'dest_store_id': False,
        }

        picking = self.env['stock.picking'].create(picking_vals)

        for line in lines_to_process:
            self.env['stock.move'].create({
                'description_picking': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_to_return,
                'quantity': line.qty_to_return,
                'product_uom': line.product_uom_id.id,
                'picking_id': picking.id,
                'location_id': self.src_warehouse_id.lot_stock_id.id,
                'location_dest_id': dest_location.id,
            })

        picking.action_confirm()
        # Re-setter la quantité faite après action_confirm() qui peut la réinitialiser
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.with_context(skip_backorder=True).button_validate()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Retour validé'),
                'message': _(
                    '%(qty)s article(s) retournés depuis %(store)s vers %(central)s.'
                ) % {
                    'qty': len(lines_to_process),
                    'store': self.src_warehouse_id.name,
                    'central': self.dest_warehouse_id.name,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class StoreReturnWizardLine(models.TransientModel):
    """Ligne du wizard retour : un produit avec son stock disponible."""
    _name = 'store.return.wizard.line'
    _description = 'Ligne de retour de stock magasin'

    wizard_id = fields.Many2one('store.return.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unité',
        related='product_id.uom_id',
    )
    qty_available = fields.Float(
        string='Stock magasin',
        readonly=True,
        digits='Product Unit',
    )
    qty_to_return = fields.Float(
        string='Quantité à retourner',
        digits='Product Unit',
        default=0.0,
    )
