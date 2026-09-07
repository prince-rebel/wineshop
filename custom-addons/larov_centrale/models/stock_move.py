# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    qty_damaged = fields.Float(
        string='Casse / manquant', digits='Product Unit', default=0.0,
        help="Bouteilles cassées ou manquantes constatées à l'ouverture. "
             "À signaler au transitaire sous 48 h. N'entre pas en stock.",
    )
    qty_gap = fields.Float(
        string='Écart', compute='_compute_qty_gap', digits='Product Unit',
        help="Quantité réalisée − quantité prévue (négatif = manquant).",
    )
    wine_region_id = fields.Many2one(related='product_id.wine_region_id', string='Région')
    wine_color = fields.Selection(related='product_id.wine_color', string='Couleur')
    vintage_display = fields.Char(related='product_id.vintage_display', string='Mill.')
    estate = fields.Char(related='product_id.estate', string='Domaine')
    sale_price_unit_ttc = fields.Monetary(
        related='sale_line_id.price_unit_ttc', string='P.U. TTC (vente)',
        currency_field='sale_currency_id',
    )
    sale_currency_id = fields.Many2one(related='sale_line_id.currency_id')

    @api.depends('quantity', 'product_uom_qty', 'state')
    def _compute_qty_gap(self):
        for move in self:
            move.qty_gap = (move.quantity - move.product_uom_qty) if move.state != 'cancel' else 0.0

    @api.onchange('qty_damaged')
    def _onchange_qty_damaged(self):
        """Sur une réception : la quantité entrée en stock = commandée − casse."""
        if self.picking_code == 'incoming' and self.qty_damaged and self.product_uom_qty:
            self.quantity = max(0.0, self.product_uom_qty - self.qty_damaged)
