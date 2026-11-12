document.addEventListener("DOMContentLoaded", () => {
    loadShoppingList();
});

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
            <label class="shopping-item ${item.checked ? 'checked' : ''}">
                <input type="checkbox" ${item.checked ? 'checked' : ''}
                       data-name="${escapeHtml(item.name)}" 
                       data-unit="${escapeHtml(item.unit || '')}">
                <div class="shopping-info">
                    <strong>${escapeHtml(item.name)}</strong>
                    <span>${escapeHtml(shoppingQuantity(item))}</span>
                </div>
            </label>
        `).join("");

        // Activa o desactiva la opacidad y notifica a Base de Datos
        container.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
            checkbox.addEventListener('change', async (e) => {
                const label = e.target.closest('.shopping-item');
                if (e.target.checked) {
                    label.classList.add('checked');
                } else {
                    label.classList.remove('checked');
                }
                try {
                    await api("/shopping-list/tick", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            name: e.target.dataset.name,
                            unit: e.target.dataset.unit || null,
                            checked: e.target.checked
                        })
                    });
                } catch (err) {
                    console.error("Error guardando progreso en lista: ", err);
                }
            });
        });

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
            // Incluimos el tick para compartir visualmente
            const mark = item.checked ? "[x]" : "[ ]";
            text += qty ? `${mark} ${item.name} (${qty})\n` : `${mark} ${item.name}\n`;
        });
        shareText(text, type, "Lista de la compra");
    } catch (e) {
        alert("No se pudo compartir la lista: " + e.message);
    }
}