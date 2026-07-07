# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PosConfig(models.Model):
    _inherit = 'pos.config'

    hide_out_of_stock_products = fields.Boolean(
        string='Masquer les produits en rupture de stock',
        default=False,
        help=(
            "Si activé, les produits avec un stock nul ou négatif dans l'entrepôt "
            "lié à ce point de vente ne s'affichent pas en caisse. "
            "Le vendeur ne voit que ce qui est réellement disponible."
        ),
    )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Override : exclure les produits en rupture de stock dans l'entrepôt
        du magasin POS quand l'option hide_out_of_stock_products est activée.
        """
        domain = super()._load_pos_data_domain(data, config)

        if not config.hide_out_of_stock_products:
            return domain

        warehouse = config.picking_type_id.warehouse_id
        if not warehouse:
            return domain

        # Produits avec stock > 0 dans l'emplacement de stock du magasin
        quants = self.env['stock.quant'].sudo().search([
            ('location_id', '=', warehouse.lot_stock_id.id),
            ('quantity', '>', 0),
        ])
        available_tmpl_ids = quants.mapped('product_id.product_tmpl_id').ids

        if available_tmpl_ids:
            domain += [('id', 'in', available_tmpl_ids)]
        else:
            # Aucun stock : on retourne un domaine qui ne donne rien
            domain += [('id', 'in', [])]

        return domain
