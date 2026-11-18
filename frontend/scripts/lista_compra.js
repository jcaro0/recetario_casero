let shoppingItems = []; // lista actual (para saber qué ingrediente es cada casilla)

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("shoppingList")
        .addEventListener("change", onToggleItem);
    loadShoppingList();
});

// "1.5 uds", "200 g" o "" si el ingrediente no tiene cantidad
function shoppingQuantity(item) {
    return formatQtyUnit(item.qty, item.unit).replace(/^\s*-\s*/, "");
}

// ¿Hay alguna receta puesta en el menú?
function menuHasRecipes(menu) {
    return Object.values(menu).some(meals =>
        Object.values(meals).some(slot => slot && slot.name)
    );
}

async function loadShoppingList() {
    const container = document.getElementById("shoppingList");
    container.innerHTML = "<p>Cargando...</p>";
    try {
        const [menu, shopping] = await Promise.all([
            api("/menu"),
            api("/shopping-list")
        ]);

        if (!menuHasRecipes(menu)) {
            shoppingItems = [];
            container.innerHTML = emptyStateHtml("No hay menú semanal");
            return;
        }
        if (shopping.length === 0) {
            shoppingItems = [];
            container.innerHTML = "<p>No hay nada en la lista todavía.</p>";
            return;
        }

        shoppingItems = shopping;
        container.innerHTML = shopping.map((item, index) => `
            <label class="shopping-item${item.checked ? " checked" : ""}">
                <input type="checkbox" data-index="${index}"${item.checked ? " checked" : ""}>
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

// Marcar / desmarcar un ingrediente: se guarda en la base de datos
async function onToggleItem(e) {
    const box = e.target.closest('input[type="checkbox"]');
    if (!box) return;

    const item = shoppingItems[Number(box.dataset.index)];
    if (!item) return;

    const row = box.closest(".shopping-item");
    const checked = box.checked;
    row.classList.toggle("checked", checked);

    try {
        await api("/shopping-list/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: item.name, unit: item.unit, checked })
        });
        item.checked = checked;
    } catch (err) {
        // Si no se pudo guardar, la casilla vuelve a como estaba
        box.checked = !checked;
        row.classList.toggle("checked", !checked);
        alert("No se pudo guardar: " + err.message);
    }
}

// Exportar: los ingredientes ya comprados llevan ✅, el resto un punto
async function shareShopping(type) {
    try {
        const shopping = await api("/shopping-list");
        if (shopping.length === 0) {
            alert("No hay nada que compartir todavía.");
            return;
        }
        let text = "🛒 LISTA DE LA COMPRA\n\n";
        shopping.forEach(item => {
            const qty = shoppingQuantity(item);
            const mark = item.checked ? "✅" : "•";
            text += qty ? `${mark} ${item.name} (${qty})\n` : `${mark} ${item.name}\n`;
        });
        shareText(text, type, "Lista de la compra");
    } catch (e) {
        alert("No se pudo compartir la lista: " + e.message);
    }
}