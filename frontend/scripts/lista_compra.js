let shoppingSaving = false;
let shoppingItems = []; // lista actual (para saber qué ingrediente es cada casilla)
let editingProduct = null;
let manualUnit;
let savingManualProduct = false;

document.addEventListener("DOMContentLoaded", () => {
    byId("shoppingList").addEventListener("change", onToggleItem);
    byId("shoppingList").addEventListener("click", onProductAction);
    byId("manualForm").addEventListener("submit", saveManualProduct);
    byId("manualCancel").onclick = resetManualForm;
    manualUnit = createUnitSelector("manualUnit");
    byId("manualUnitField").replaceWith(manualUnit.element);
    setupShareDropdown(shareShopping);
    loadShoppingList();
    document.addEventListener("recetario:refreshed", loadShoppingList);
    document.addEventListener("recetario:locked", resetManualForm);
});

async function loadShoppingList() {
    const container = byId("shoppingList");
    if (!container.hasChildNodes()) container.innerHTML = '<p class="loading-state">Cargando compra…</p>';
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
        shoppingItems = [];
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
                <button type="button" class="icon-button" data-write data-action="delete" aria-label="Eliminar ${escapeHtml(item.name)}" aria-haspopup="dialog"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>
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
    manualUnit.setValue();
    byId("manualSubmit").textContent = "Añadir producto";
    byId("manualCancel").hidden = true;
    byId("manualStatus").textContent = "";
}

async function saveManualProduct(event) {
    event.preventDefault();
    if (!canWrite() || savingManualProduct) return;
    const form = event.currentTarget;
    const data = { ...Object.fromEntries(new FormData(form)), unit: manualUnit.value };
    const id = editingProduct;
    const fields = byId("manualFields");
    dismissToast();
    savingManualProduct = true;
    fields.disabled = true;
    byId("manualStatus").textContent = "Guardando producto…";
    try {
        const url = "/shopping-list/manual";
        if (id === null) await api(url, "POST", data);
        else await api(`${url}/${id}`, "PUT", data);
        resetManualForm();
        await loadShoppingList();
        notify(id === null ? "Producto añadido a la compra" : "Producto actualizado", "success");
    } catch (error) {
        notify("No se pudo guardar el producto. " + error.message, "error");
    } finally {
        savingManualProduct = false;
        fields.disabled = false;
        byId("manualStatus").textContent = "";
        applyWriteAccess();
    }
}

function onProductAction(event) {
    const button = event.target.closest("[data-action]");
    if (!button || !canWrite() || savingManualProduct) return;
    const item = shoppingItems[Number(button.closest(".shopping-item").dataset.index)];
    if (button.dataset.action === "edit") {
        editingProduct = item.manual_id;
        const fields = byId("manualForm").elements;
        fields.namedItem("name").value = item.name;
        fields.qty.value = item.qty ?? "";
        manualUnit.setValue(item.unit);
        byId("manualSubmit").textContent = "Guardar producto";
        byId("manualCancel").hidden = false;
        fields.namedItem("name").focus();
        return;
    }
    confirmAction({
        title: "¿Eliminar el producto?",
        message: `«${item.name}» se eliminará de la lista de la compra.`,
        label: "Eliminar producto",
        trigger: button,
        destructive: true,
        progress: "Eliminando producto…",
        errorPrefix: "No se pudo eliminar el producto. ",
        action: () => api(`/shopping-list/manual/${item.manual_id}`, "DELETE"),
        onSuccess: async () => {
            if (editingProduct === item.manual_id) resetManualForm();
            await loadShoppingList();
            byId("manualForm").elements.namedItem("name").focus({ preventScroll: true });
            notify("Producto eliminado de la compra", "success");
        }
    });
}

// Marcar / desmarcar un ingrediente: se guarda en la base de datos
async function onToggleItem(e) {
    const box = e.target.closest('input[type="checkbox"]');
    if (!box) return;

    const row = box.closest(".shopping-item");
    const item = shoppingItems[Number(row.dataset.index)];
    if (!item) return;

    if (!canWrite() || shoppingSaving) {
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
        await loadShoppingList();
    } catch (err) {
        box.checked = item.checked;
        notify("No se pudo actualizar la compra. " + err.message, "error");
    } finally {
        shoppingSaving = false;
        document.querySelectorAll(".shopping-item input").forEach(input => input.disabled = false);
        applyWriteAccess();
    }
}

// Exportar: los ingredientes ya comprados llevan ✅, el resto un punto
// Exportar: los ingredientes ya comprados llevan ✅, el resto un punto
async function shareShopping(type) {
    try {
        const shopping = await api("/shopping-list");
        if (shopping.length === 0) {
            notify("Todavía no hay contenido para compartir.");
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
        notify("No se pudo compartir la lista. " + e.message, "error");
    }
}
