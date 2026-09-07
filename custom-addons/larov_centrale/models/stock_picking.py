# -*- coding: utf-8 -*-
from odoo import api, fields, models

MOVE_NATURES = [
    ('transfer', 'Transfert entre dépôts'),
    ('exit', 'Sortie'),
    ('entry', 'Entrée (arrivage)'),
    ('return', 'Retour'),
    ('breakage', 'Casse / perte'),
]


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ── Réception d'arrivage fournisseur ────────────────────────────────────
    forwarder_id = fields.Many2one(
        'res.partner', string='Transitaire',
        compute='_compute_forwarder_id', store=True, readonly=False,
        domain=[('is_forwarder', '=', True)],
    )
    transport_mode = fields.Selection(
        related='purchase_id.transport_mode', string='Mode de transport', readonly=False,
    )
    transport_mode_label = fields.Char(related='purchase_id.transport_mode_label')
    container_ref = fields.Char(string='N° conteneur / B/L')
    supplier_invoice_ref = fields.Char(string='N° facture fournisseur')
    cargo_condition = fields.Char(
        string='État général du chargement',
        help="Ex. « Conforme — cartons secs, palettes intactes ».",
    )
    reception_remarks = fields.Text(string='Réserves et observations')
    total_damaged_qty = fields.Float(
        string='Casse / manquant (total)', compute='_compute_reception_totals', digits='Product Unit',
    )
    damage_rate = fields.Float(
        string='Taux de casse', compute='_compute_reception_totals', digits=(16, 4),
        help="Casse et manquants ÷ quantité commandée.",
    )
    total_gap_qty = fields.Float(
        string='Écart total', compute='_compute_reception_totals', digits='Product Unit',
    )
    received_value_supplier_currency = fields.Float(
        string='Valeur reçue (devise fournisseur)', compute='_compute_reception_totals',
        digits='Product Price',
    )

    # ── Bon de livraison client ─────────────────────────────────────────────
    driver_name = fields.Char(string='Livreur')
    site_contact = fields.Char(
        string='Contact sur place',
        help="Nom et téléphone de la personne qui réceptionne chez le client.",
    )

    # ── Bon de mouvement interne ────────────────────────────────────────────
    move_nature = fields.Selection(
        MOVE_NATURES, string='Nature du mouvement',
        compute='_compute_move_nature', store=True, readonly=False,
    )

    # ── Signatures imprimées ────────────────────────────────────────────────
    prepared_by_name = fields.Char(string='Établi / réceptionné par')
    checked_by_name = fields.Char(string='Contrôlé par')

    @api.depends('purchase_id.forwarder_id')
    def _compute_forwarder_id(self):
        for picking in self:
            if picking.purchase_id and picking.purchase_id.forwarder_id:
                picking.forwarder_id = picking.purchase_id.forwarder_id
            elif not picking.forwarder_id:
                picking.forwarder_id = False

    @api.depends('move_ids.qty_damaged', 'move_ids.product_uom_qty', 'move_ids.quantity',
                 'move_ids.purchase_line_id.price_unit')
    def _compute_reception_totals(self):
        for picking in self:
            moves = picking.move_ids
            ordered = sum(moves.mapped('product_uom_qty'))
            damaged = sum(moves.mapped('qty_damaged'))
            picking.total_damaged_qty = damaged
            picking.damage_rate = (damaged / ordered) if ordered else 0.0
            picking.total_gap_qty = sum(moves.mapped('qty_gap'))
            picking.received_value_supplier_currency = sum(
                m.quantity * (m.purchase_line_id.price_unit or 0.0) for m in moves
            )

    @api.depends('picking_type_code', 'location_id.usage', 'location_dest_id.usage',
                 'location_id.warehouse_id', 'location_dest_id.warehouse_id')
    def _compute_move_nature(self):
        for picking in self:
            code = picking.picking_type_code
            if code == 'incoming':
                nature = 'entry' if picking.location_id.usage == 'supplier' else 'return'
            elif code == 'outgoing':
                nature = 'exit'
            elif picking.location_dest_id.usage == 'inventory':
                nature = 'breakage'
            else:
                nature = 'transfer'
            # Valeur saisie manuellement conservée, sinon nature déduite
            picking.move_nature = picking.move_nature or nature

    def _larov_transfer_lines(self):
        """Lignes du bon de mouvement : chaque référence apparaît deux fois
        (sortie en négatif, entrée en positif), comme sur le modèle client."""
        self.ensure_one()
        lines = []
        for move in self.move_ids.filtered(lambda m: m.state != 'cancel'):
            qty = move.quantity or move.product_uom_qty
            lines.append({'move': move, 'qty': -qty, 'received': 0.0,
                          'label': 'sortie %s' % (self.location_id.warehouse_id.name or self.location_id.display_name)})
            lines.append({'move': move, 'qty': qty,
                          'received': move.quantity if move.state == 'done' else 0.0,
                          'label': 'entrée %s' % (self.location_dest_id.warehouse_id.name or self.location_dest_id.display_name)})
        return lines
