# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


def _fmt_qty(value):
    """Affiche 40 plutôt que 40.0, mais garde 1 décimale si nécessaire."""
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def _build_store_sales_summary(history_rows):
    if not history_rows:
        return _(
            "Aucune vente ni aucun mouvement de stock enregistré pour ce "
            "produit dans les magasins."
        )
    total_sold = sum(history_rows.mapped('qty_sold_total'))
    total_stock = sum(history_rows.mapped('qty_on_hand'))
    lines = [
        _("VENDU AU TOTAL : %(sold)s   —   STOCK ACTUEL TOTAL : %(stock)s") % {
            'sold': _fmt_qty(total_sold),
            'stock': _fmt_qty(total_stock),
        },
        "",
    ]
    for row in history_rows.sorted(key=lambda r: r.warehouse_name or ''):
        lines.append(
            _("• %(store)s : %(sold)s vendu(s)  |  %(stock)s en stock") % {
                'store': row.warehouse_name,
                'sold': _fmt_qty(row.qty_sold_total),
                'stock': _fmt_qty(row.qty_on_hand),
            }
        )
    return "\n".join(lines)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    store_history_count = fields.Integer(
        string='Historique magasins',
        compute='_compute_store_history_count',
    )
    store_sales_summary = fields.Text(
        string='Ventes et stock par magasin',
        compute='_compute_store_sales_summary',
    )

    def _compute_store_history_count(self):
        History = self.env['product.store.history']
        for template in self:
            template.store_history_count = History.search_count([
                ('product_id', 'in', template.product_variant_ids.ids),
            ])

    def _compute_store_sales_summary(self):
        History = self.env['product.store.history']
        for template in self:
            rows = History.search([
                ('product_id', 'in', template.product_variant_ids.ids),
            ])
            template.store_sales_summary = _build_store_sales_summary(rows)

    def action_view_store_history(self):
        """
        Ouvre l'historique consolidé (F9) de ce produit magasin par magasin :
        stock actuel, ventes et transferts inter-magasins.
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pos_store_replenishment.action_product_store_history'
        )
        action['domain'] = [('product_id', 'in', self.product_variant_ids.ids)]
        action['context'] = {}
        action['name'] = _('Historique magasins — %s') % self.display_name
        return action

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Override : exclure les produits en rupture de stock dans l'entrepôt
        du magasin POS quand l'option hide_out_of_stock_products est activée.
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

    store_history_count = fields.Integer(
        string='Historique magasins',
        compute='_compute_store_history_count',
    )
    store_sales_summary = fields.Text(
        string='Ventes et stock par magasin',
        compute='_compute_store_sales_summary',
    )

    def _compute_store_history_count(self):
        History = self.env['product.store.history']
        for product in self:
            product.store_history_count = History.search_count([
                ('product_id', '=', product.id),
            ])

    def _compute_store_sales_summary(self):
        History = self.env['product.store.history']
        for product in self:
            rows = History.search([('product_id', '=', product.id)])
            product.store_sales_summary = _build_store_sales_summary(rows)

    def action_view_store_history(self):
        """
        Ouvre l'historique consolidé (F9) de ce produit magasin par magasin :
        stock actuel, ventes et transferts inter-magasins.

        Doublon volontaire de ProductTemplate.action_view_store_history :
        selon l'écran d'où l'on ouvre la fiche produit, Odoo affiche parfois
        directement un enregistrement product.product (variante) plutôt que
        product.template, et le bouton doit alors exister sur ce modèle.
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pos_store_replenishment.action_product_store_history'
        )
        action['domain'] = [('product_id', '=', self.id)]
        action['context'] = {}
        action['name'] = _('Historique magasins — %s') % self.display_name
        return action

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
