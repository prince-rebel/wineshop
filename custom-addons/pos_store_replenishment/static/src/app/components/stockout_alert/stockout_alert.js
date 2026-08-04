/** @odoo-module **/
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

// ─────────────────────────────────────────────────────────────
//  Dialog : liste des ruptures critiques du magasin
// ─────────────────────────────────────────────────────────────
export class StockoutAlertDialog extends Component {
    static template = "pos_store_replenishment.StockoutAlertDialog";
    static components = { Dialog };
    static props = {
        alerts: Array,
        close: Function,
    };

    get criticalAlerts() {
        return this.props.alerts.filter((a) => a.urgency === "critical");
    }

    get warningAlerts() {
        return this.props.alerts.filter((a) => a.urgency === "warning");
    }
}

// ─────────────────────────────────────────────────────────────
//  Patch ProductScreen : badge + notification ruptures critiques
// ─────────────────────────────────────────────────────────────
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this._stockoutAlerts = [];
        this._loadStockoutAlerts();
    },

    async _loadStockoutAlerts() {
        try {
            const wh = this.pos.config.warehouse_id;
            const warehouseId = wh ? (typeof wh === "object" ? wh.id : wh) : null;
            if (!warehouseId) return;

            const alerts = await this.orm.call(
                "store.stockout.forecast",
                "get_pos_alerts",
                [warehouseId]
            );
            this._stockoutAlerts = alerts || [];

            if (this._stockoutAlerts.filter((a) => a.urgency === "critical").length > 0) {
                // Afficher automatiquement à l'ouverture si ruptures critiques
                this._showStockoutAlert();
            }
        } catch (e) {
            // Silencieux si le modèle n'est pas accessible
        }
    },

    _showStockoutAlert() {
        if (this._stockoutAlerts.length === 0) return;
        this.dialog.add(StockoutAlertDialog, {
            alerts: this._stockoutAlerts,
        });
    },

    get criticalStockoutCount() {
        return this._stockoutAlerts.filter((a) => a.urgency === "critical").length;
    },
});
