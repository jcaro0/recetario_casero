let shoppingSaving = false;
let shoppingItems = []; // lista actual (para saber qué ingrediente es cada casilla)
let editingProduct = null;

document.addEventListener("DOMContentLoaded", () => {
    byId("shoppingList").addEventListener("change", onToggleItem);
    byId("shoppingList").addEventListener("click", onProductAction);
    byId("manualForm").addEventListener("submit", saveManualProduct);
    byId("manualCancel").onclick = resetManualForm;
    setupShareDropdown(shareShopping);
    loadShoppingList();
    document.addEventListener("recetario:refreshed", loadShoppingList);
    document.addEventListener("recetario:locked", resetManualForm);
});

async function loadShoppingList(showLoading = true) {
    const container = byId("shoppingList");
    if (showLoading) container.innerHTML = "<p>Cargando...</p>";
    try {
        const [menu, shopping] = await Promise.all([
            api("/menu"),
            api("/shopping-list")
        ]);

        if (shopping.length === 0) {
            shoppingItems = [];
            const hasMenu = Object.values(menu).some(meals => Object.values(meals).some(slot => slot.name));
            container.innerHTML = hasMenu ? "<p>No hay nada en la lista todavía.</p>" :
                emptyStateHtml("No hay menú semanal");
            return;
        }

        shoppingItems = shopping;
        renderShoppingList();
    } catch (error) {
        container.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    }
}

function shoppingAmount(item) {
    return formatQtyUnit(item.qty, item.unit) || (item.manual_id ? item.unit || "" : "");
}

function renderShoppingList() {
    const container = byId("shoppingList");
    const row = (item, index) => `
        <div class="shopping-item${item.checked ? " checked" : ""}" data-index="${index}">
            <label class="shopping-details">
                <input type="checkbox" data-write${item.checked ? " checked" : ""}>
                <span class="shopping-info"><strong>${escapeHtml(item.name)}</strong>
                <span>${escapeHtml(shoppingAmount(item))}</span></span>
            </label>
            ${item.manual_id ? `<div class="manual-actions">
                <button type="button" data-write data-action="edit" aria-label="Editar ${escapeHtml(item.name)}">Editar</button>
                <button type="button" data-write data-action="delete" aria-label="Eliminar ${escapeHtml(item.name)}">Eliminar</button>
            </div>` : ""}
        </div>`;
    const group = checked => shoppingItems.map((item, index) => item.checked === checked ? row(item, index) : "").join("");
    container.innerHTML = group(false) + (shoppingItems.some(i => i.checked) ?
        '<h2 class="purchased-divider">Ya comprados</h2>' + group(true) : "");
    applyWriteAccess();
}

function resetManualForm() {
    editingProduct = null;
    byId("manualForm").reset();
    byId("manualSubmit").textContent = "Añadir producto";
    byId("manualCancel").classList.add("hidden");
    byId("manualStatus").textContent = "";
}

async function saveManualProduct(event) {
    event.preventDefault();
    if (!canWrite()) return;
    const button = byId("manualSubmit");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    button.disabled = true;
    try {
        const url = "/shopping-list/manual";
        if (editingProduct === null) await api(url, "POST", data);
        else await api(`${url}/${editingProduct}`, "PUT", data);
        resetManualForm();
        await loadShoppingList();
    } catch (error) {
        byId("manualStatus").textContent = error.message;
    } finally {
        button.disabled = false;
    }
}

async function onProductAction(event) {
    const button = event.target.closest("[data-action]");
    if (!button || !canWrite()) return;
    const item = shoppingItems[Number(button.closest(".shopping-item").dataset.index)];
    if (button.dataset.action === "edit") {
        editingProduct = item.manual_id;
        const fields = byId("manualForm").elements;
        fields.namedItem("name").value = item.name;
        fields.qty.value = item.qty ?? "";
        fields.unit.value = item.unit ?? "";
        byId("manualSubmit").textContent = "Guardar producto";
        byId("manualCancel").classList.remove("hidden");
        fields.namedItem("name").focus();
    } else if (confirm(`¿Eliminar «${item.name}»?`)) {
        try {
            await api(`/shopping-list/manual/${item.manual_id}`, "DELETE");
            if (editingProduct === item.manual_id) resetManualForm();
            await loadShoppingList();
        } catch (error) {
            byId("manualStatus").textContent = error.message;
        }
    }
}

// Marcar / desmarcar un ingrediente: se guarda en la base de datos
async function onToggleItem(e) {
    const box = e.target.closest('input[type="checkbox"]');
    if (!box || shoppingSaving) return;

    const row = box.closest(".shopping-item");
    const item = shoppingItems[Number(row.dataset.index)];
    if (!item) return;

    if (!canWrite()) {
        box.checked = item.checked;
        return;
    }
    const checked = box.checked;
    // Deja la última marca del servidor visible hasta confirmar la operación.
    box.checked = item.checked;
    shoppingSaving = true;
    document.querySelectorAll(".shopping-item input").forEach(input => input.disabled = true);
    try {
        if (item.manual_id) {
            await api(`/shopping-list/manual/${item.manual_id}`, "PATCH", { checked });
        } else {
            await api("/shopping-list/check", "POST", { name: item.name, unit: item.unit, checked });
        }
        await loadShoppingList(false);
    } catch (err) {
        box.checked = item.checked;
        alert("No se pudo guardar: " + err.message);
    } finally {
        shoppingSaving = false;
        document.querySelectorAll(".shopping-item input").forEach(input => input.disabled = false);
        applyWriteAccess();
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
            const qty = shoppingAmount(item);
            const mark = item.checked ? "✅" : "•";
            text += qty ? `${mark} ${item.name} (${qty})\n` : `${mark} ${item.name}\n`;
        });
        await shareText(text, type, "Lista de la compra");
    } catch (e) {
        alert("No se pudo compartir la lista: " + e.message);
    }
}
