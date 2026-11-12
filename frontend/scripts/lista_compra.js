document.addEventListener("DOMContentLoaded", () => {
    loadShoppingList();
});

// "1.5 uds", "200 g" o "" si el ingrediente no tiene cantidad
function shoppingQuantity(item) {
    return formatQtyUnit(item.qty, item.unit).replace(/^\s*-\s*/, "");
}

async function loadShoppingList() {
    const container = document.getElementById("shoppingList");
    container.innerHTML = "<p>Cargando...</p>";
    try {
        const shopping = await api("/shopping-list");
        if (shopping.length === 0) {
            container.innerHTML = "<p>No hay nada en la lista todavía.</p>";
            return;
        }
        container.innerHTML = shopping.map(item => `
            <label class="shopping-item">
                <input type="checkbox">
                <div class="shopping-info">
                    <strong>${escapeHtml(item.name)}</strong>
                    <span>${escapeHtml(shoppingQuantity(item))}</span>
                </div>
            </label>
        `).join("");
    } catch {
        container.innerHTML = "<p>Error al cargar.</p>";
    }
}

async function shareShopping(type) {
    try {
        const shopping = await api("/shopping-list");
        let text = "🛒 LISTA DE LA COMPRA\n\n";
        shopping.forEach(item => {
            const qty = shoppingQuantity(item);
            text += qty ? `• ${item.name} (${qty})\n` : `• ${item.name}\n`;
        });
        shareText(text, type, "Lista de la compra");
    } catch (e) {
        alert("No se pudo compartir la lista: " + e.message);
    }
}