document.addEventListener("DOMContentLoaded", () => {
    loadShoppingList();
});

async function loadShoppingList() {
    const container = document.getElementById("shoppingList");
    container.innerHTML = "<p>Cargando...</p>";
    try {
        const res = await fetch("/shopping-list");
        const shopping = await res.json();
        if (shopping.length === 0) {
            container.innerHTML = "<p>No hay nada en la lista todavía.</p>";
            return;
        }
        container.innerHTML = "";
        shopping.forEach(item => {
            container.innerHTML += `
                <label class="shopping-item">
                    <input type="checkbox">
                    <div class="shopping-info">
                        <strong>${item.name}</strong>
                        <span>${formatQtyUnit(item.qty, item.unit).replace(/^\s*-\s*/, "")}</span>
                    </div>
                </label>
            `;
        });
    } catch {
        container.innerHTML = "<p>Error al cargar.</p>";
    }
}

async function shareShopping(type) {
    const res = await fetch("/shopping-list");
    const shopping = await res.json();
    let text = "🛒 LISTA DE LA COMPRA\n\n";
    shopping.forEach(item => {
        text += `• ${item.name} (${item.qty} ${item.unit})\n`;
    });
    shareText(text, type);
}