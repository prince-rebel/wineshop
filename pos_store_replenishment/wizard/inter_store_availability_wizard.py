# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class InterStoreAvailabilityWizard(models.TransientModel):
    """
    Wizard F3 — Disponibilité inter-magasins.
    Permet de voir dans quels autres magasins un produit est disponible,
    pour rediriger un client en cas de rupture locale.
    """
    _name = 'inter.store.availability.wizard'
    _description = 'Disponibilité du produit dans les autres magasins'

    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True,
    )
    current_store_id = fields.Many2one(
        'stock.warehouse',
        string='Magasin actuel (en rupture)',
        domain=[('is_pos_store', '=', True)],
    )
    availability_line_ids = fields.One2many(
        'inter.store.availability.line',
        'wizard_id',
        string='Disponibilité par magasin',
        compute='_compute_availability',
    )
    has_availability = fields.Boolean(
        string='Stock trouvé ailleurs',
        compute='_compute_availability',
    )

    @api.depends('product_id', 'current_store_id')
    def _compute_availability(self):
        for wizard in self:
            wizard.availability_line_ids = [(5, 0, 0)]
            wizard.has_availability = False

            if not wizard.product_id:
                continue

            # Tous les entrepôts sauf le magasin courant :
            # POS stores + entrepôt(s) central (is_pos_store = False)
            domain = [('id', '!=', wizard.current_store_id.id if wizard.current_store_id else False)]
            stores = self.env['stock.warehouse'].search(domain)

            lines = []
            for store in stores:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', wizard.product_id.id),
                    ('location_id', 'child_of', store.lot_stock_id.id),
                ])
                qty = sum(quants.mapped('quantity'))
                lines.append((0, 0, {
                    'store_id': store.id,
                    'qty_available': qty,
                    'has_stock': qty > 0,
                    'address': store.partner_id.contact_address if store.partner_id else '',
                    'phone': store.partner_id.phone or store.partner_id.mobile or '',
                }))

            wizard.availability_line_ids = lines
            wizard.has_availability = any(
                qty > 0 for qty in [l[2]['qty_available'] for l in lines]
            )

    @api.model
    def get_availability_for_pos(self, product_id, current_warehouse_id=False):
        """
        Méthode RPC appelée depuis la session POS (F3).
        Retourne la liste des magasins avec la disponibilité du produit.
        """
        # Tous les entrepôts sauf le magasin courant (POS stores + central)
        domain = []
        if current_warehouse_id:
            domain.append(('id', '!=', current_warehouse_id))

        stores = self.env['stock.warehouse'].search(domain)
        result = []
        for store in stores:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product_id),
                ('location_id', 'child_of', store.lot_stock_id.id),
            ])
            qty = sum(quants.mapped('quantity'))
            result.append({
                'store_name': store.name,
                'qty_available': qty,
                'address': store.partner_id.contact_address if store.partner_id else '',
                'phone': store.partner_id.phone or store.partner_id.mobile or '',
            })

        result.sort(key=lambda x: x['qty_available'], reverse=True)
        return result


class InterStoreAvailabilityLine(models.TransientModel):
    """Ligne de disponibilité : un magasin avec son stock disponible."""
    _name = 'inter.store.availability.line'
    _description = 'Ligne de disponibilité inter-magasins'
    _order = 'qty_available desc'

    wizard_id = fields.Many2one('inter.store.availability.wizard', ondelete='cascade')
    store_id = fields.Many2one('stock.warehouse', string='Magasin', readonly=True)
    qty_available = fields.Float(string='Quantité disponible', readonly=True, digits='Product Unit')
    has_stock = fields.Boolean(string='En stock', readonly=True)
    address = fields.Char(string='Adresse', readonly=True)
    phone = fields.Char(string='Téléphone', readonly=True)
