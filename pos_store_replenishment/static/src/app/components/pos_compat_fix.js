/** @odoo-module **/
/**
 * Correctif de compatibilité pour pos_product_stock (Cybrosys).
 *
 * Ce module lit this.pos.res_setting['stock_from'] dans PaymentScreen.validateOrder
 * mais res_setting = this.data.models['res.config.settings'].getFirst() peut être
 * undefined quand aucun enregistrement res.config.settings n'existe en DB
 * (TransientModel vidé automatiquement).
 *
 * On s'assure que res_setting a toujours au minimum un objet vide après
 * le chargement des données POS.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData(...arguments);
        // Garantit que res_setting est toujours un objet (même vide)
        // pour éviter le crash "Cannot read properties of undefined (reading 'stock_from')"
        if (!this.res_setting) {
            this.res_setting = {
                display_stock: false,
                stock_type: false,
                stock_from: false,
                stock_location_id: false,
            };
        }
    },
});
