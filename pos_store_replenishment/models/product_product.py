# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Surcharge : n'envoie au POS que les produits qui ont du stock > 0
        dans l'entrepôt associé à la configuration POS.
        Réduit la charge du POS en éliminant les produits en rupture.
        Actif uniquement si l'option 'Masquer les produits en rupture' est activée.
        """
        domain = super()._load_pos_data_domain(data, config)

        if not config.hide_out_of_stock_products:
            return domain

        # Entrepôt de ce POS : picking_type_id.warehouse_id est plus fiable
        warehouse = config.picking_type_id.warehouse_id
        if not warehouse:
            warehouse = config.warehouse_id

        if warehouse and warehouse.lot_stock_id:
            self.env.cr.execute("""
                SELECT DISTINCT pp.product_tmpl_id
                FROM stock_quant sq
                JOIN stock_location sl ON sl.id = sq.location_id
                    AND sl.usage = 'internal' AND sl.active = TRUE
                JOIN stock_location sl_root ON sl.parent_path LIKE sl_root.parent_path || '%%'
                    AND sl_root.id = %s
                JOIN product_product pp ON pp.id = sq.product_id
                WHERE sq.quantity > 0
            """, [warehouse.lot_stock_id.id])
            tmpl_ids = [row[0] for row in self.env.cr.fetchall()]
            domain += [('id', 'in', tmpl_ids)]

        return domain

    def action_view_inter_store_availability_from_template(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Disponibilité dans les magasins — %s') % self.display_name,
            'res_model': 'inter.store.availability.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.product_variant_id.id,
            },
        }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def get_inter_store_availability(self, exclude_warehouse_id=None):
        """
        Retourne la disponibilité de ce produit dans tous les magasins POS,
        en excluant optionnellement un magasin (celui qui est en rupture).

        Retourne une liste de dicts :
        [{'store_id': 3, 'store_name': 'Boutique Cocody', 'qty': 12.0}, ...]

        Utilisé par F3 pour recommander un autre magasin au client.
        """
        self.ensure_one()
        domain = [('is_pos_store', '=', True)]
        if exclude_warehouse_id:
            domain.append(('id', '!=', exclude_warehouse_id))
        stores = self.env['stock.warehouse'].search(domain)

        result = []
        for store in stores:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', self.id),
                ('location_id', '=', store.lot_stock_id.id),
            ])
            qty = sum(quants.mapped('quantity'))
            if qty > 0:
                result.append({
                    'store_id': store.id,
                    'store_name': store.name,
                    'store_address': store.partner_id.contact_address if store.partner_id else '',
                    'qty': qty,
                    'uom': self.uom_id.name,
                })
        return sorted(result, key=lambda x: x['qty'], reverse=True)

    def action_view_inter_store_availability(self):
        """
        Ouvre la vue de disponibilité inter-magasins pour ce produit.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Disponibilité dans les autres magasins — %s') % self.display_name,
            'res_model': 'inter.store.availability.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
            },
        }
