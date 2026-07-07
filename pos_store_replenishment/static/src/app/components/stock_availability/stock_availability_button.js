/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

// ─────────────────────────────────────────────────────────────
//  Composant Dialog : Disponibilité inter-magasins
// ─────────────────────────────────────────────────────────────
export class StockAvailabilityDialog extends Component {
    static template = "pos_store_replenishment.StockAvailabilityDialog";
    static components = { Dialog };
    static props = {
        pos: Object,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            productId: null,
            productName: "",
            searchQuery: "",
            lines: [],
            loading: false,
            searched: false,
        });
        this.products = this.props.pos.models["product.product"].getAll();

        // Pré-remplir avec le produit sélectionné en caisse si disponible
        const order = this.props.pos.getOrder();
        const selectedLine = order && order.getSelectedOrderline();
        if (selectedLine && selectedLine.product_id) {
            this._loadProduct(
                selectedLine.product_id.id,
                selectedLine.product_id.display_name
            );
        }
    }

    get currentStoreWarehouseId() {
        const wh = this.props.pos.config.warehouse_id;
        if (!wh) return false;
        // warehouse_id peut être un objet {id, display_name} ou un entier
        return typeof wh === "object" ? wh.id : wh;
    }

    async _loadProduct(productId, productName) {
        this.state.productId = productId;
        this.state.productName = productName;
        this.state.loading = true;
        this.state.searched = false;
        this.state.lines = [];

        try {
            const result = await this.orm.call(
                "inter.store.availability.wizard",
                "get_availability_for_pos",
                [productId, this.currentStoreWarehouseId]
            );
            this.state.lines = result;
            this.state.searched = true;
        } catch (e) {
            this.state.lines = [];
            this.state.searched = true;
        } finally {
            this.state.loading = false;
        }
    }

    selectProduct(product) {
        this._loadProduct(product.id, product.display_name);
    }

    get sortedProducts() {
        return [...this.products].sort((a, b) =>
            (a.display_name || "").localeCompare(b.display_name || "")
        );
    }

    get filteredProducts() {
        const query = (this.state.searchQuery || "").trim().toLowerCase();
        const products = this.sortedProducts;
        if (!query) {
            return products;
        }
        return products.filter((product) => {
            const name = (product.display_name || "").toLowerCase();
            const code = (product.default_code || "").toLowerCase();
            const barcode = (product.barcode || "").toLowerCase();
            return name.includes(query) || code.includes(query) || barcode.includes(query);
        });
    }
}

// ─────────────────────────────────────────────────────────────
//  Patch ControlButtons : ajout du bouton Dispo. inter-magasins
//  Pas besoin d'override setup() — dialog est déjà disponible
//  dans ControlButtons via son propre setup()
// ─────────────────────────────────────────────────────────────
patch(ControlButtons.prototype, {
    openStockAvailability() {
        this.dialog.add(StockAvailabilityDialog, { pos: this.pos });
    },
});
