const MEALS = [
    { key: "comida", label: "Comida", icon: "🍽️" },
    { key: "cena", label: "Cena", icon: "🌙" }
];

let currentEditSlot = null; // { day, meal }
let recipeOptions = null;
let weeklyMenu = {};
let weekPeople = 2;

document.addEventListener("DOMContentLoaded", () => {
    setupShareDropdown(shareMenu);
    loadWeeklyMenu();
    document.addEventListener("recetario:refreshed", loadWeeklyMenu);
    document.addEventListener("recetario:locked", closeChooseRecipeModal);
    setupModal();
    byId("weekPeopleForm").onsubmit = async e => {
        e.preventDefault();
        const input = byId("weekPeople");
        if (!canWrite() || !input.reportValidity()) return;
        const button = e.currentTarget.querySelector("button");
        button.disabled = true;
        try {
            await api("/menu/people", "POST", { people: Number(input.value) });
            byId("weekPeopleStatus").textContent = "Comensales actualizados";
            await loadWeeklyMenu();
        } catch (err) { byId("weekPeopleStatus").textContent = err.message; }
        finally { button.disabled = false; applyWriteAccess(); }
    };
    setupChooseRecipeModal();
    setupWeekGridEvents();
});

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

// Compartir menú semanal
async function shareMenu(type) {
    try {
        const [days, menu] = await Promise.all([api("/days"), api("/menu")]);
        let text = "🍽️ MENÚ SEMANAL\n\n";
        days.forEach(day => {
            text += `${capitalize(day)}\n`;
            MEALS.forEach(meal => {
                const recipe = menu[day]?.[meal.key];
                text += `  ${meal.label}: ${recipe?.name || "Sin receta"}\n`;
            });
            text += "\n";
        });
        await shareText(text.trim(), type, "Menú semanal");
    } catch (e) {
        alert("No se pudo compartir el menú: " + e.message);
    }
}

// Carga del menú semanal
function slotHtml(dayKey, meal, recipe) {
    const name = recipe?.name || "Sin receta";
    const count = recipe?.ingredients?.length || 0;
    return `
        <div class="meal-slot" data-write-drag
             data-day="${dayKey}" data-meal="${meal.key}">
            <div class="meal-label">${meal.icon} ${meal.label}</div>
            <div class="food">
                ${escapeHtml(name)}
                <small>${count} ingredientes</small>
            </div>
            ${recipe?.id ? `<div class="slot-people">Comensales
                <input data-write type="number" min="1" max="2147483647" step="1" required value="${recipe.people || recipe.servings || 2}"
                    aria-label="Comensales de ${escapeHtml(dayKey)} ${meal.label.toLowerCase()}">
                <button type="button" class="reset-people" data-write title="Usar las raciones originales">Originales (${recipe.servings || 2})</button>
            </div>` : ""}
        </div>
    `;
}

async function loadWeeklyMenu() {
    const grid = byId("weekGrid");
    const generateButton = byId("generateButton");
    grid.innerHTML = "<p>Cargando menú...</p>";
    try {
        // Peticiones en paralelo: días, ¿hay recetas suficientes? y menú
        const [days, status, menu, settings] = await Promise.all([
            api("/days"),
            api("/menu/status"),
            api("/menu"), api("/menu/people")
        ]);
        weeklyMenu = menu;
        weekPeople = settings.people;
        byId("weekPeople").value = weekPeople;

        // Un menú ya planificado sigue accesible aunque después se borren recetas.
        if (!status.enough && !Object.values(menu).some(meals => Object.values(meals).some(r => r.id))) {
            generateButton.style.display = "none";
            grid.innerHTML = emptyStateHtml("No hay suficientes recetas");
            return;
        }
        generateButton.style.display = status.enough ? "" : "none";

        grid.innerHTML = days.map(day => {
            const meals = menu[day];
            return `
                <div class="day-card" data-day="${day}">
                    <div class="day-header">
                        <h3>${escapeHtml(capitalize(day))}</h3>
                        <span>🍽️</span>
                    </div>
                    ${MEALS.map(m => slotHtml(day, m, meals[m.key])).join("")}
                    <div class="day-hint">
                        <span class="material-symbols-rounded">swap_horiz</span>
                        Toca para cambiar • arrastra para mover
                    </div>
                </div>
            `;
        }).join("");
    } catch (e) {
        grid.innerHTML = `<p>${escapeHtml(e.message)}</p>`;
    } finally {
        applyWriteAccess();
    }
}

// Modal para regenerar menú
function setupModal() {
    const modal = byId("modal");
    const open = byId("generateButton");
    const cancel = byId("cancelModal");
    const confirm = byId("confirmModal");

    const people = byId("generatePeople");
    open.onclick = () => {
        people.value = weekPeople;
        modal.classList.remove("hidden");
        people.focus();
    };
    cancel.onclick = () => modal.classList.add("hidden");
    dismissModalOnBackdropOrEscape("modal", cancel.onclick);
    confirm.onclick = async () => {
        if (!canWrite() || !people.reportValidity()) return;
        confirm.disabled = true;
        try {
            await api("/menu/generate", "POST", { people: Number(people.value) });
            modal.classList.add("hidden");
        } catch (e) {
            alert("No se pudo regenerar el menú: " + e.message);
        }
        confirm.disabled = false;
        loadWeeklyMenu();
    };
}

// Modal selector de receta
function setupChooseRecipeModal() {
    byId("closeChooseModal").onclick = closeChooseRecipeModal;
    dismissModalOnBackdropOrEscape("chooseRecipeModal", closeChooseRecipeModal);
    byId("recipeSearchInput").oninput = () => renderChooseRecipeList();
    byId("chooseRecipeList").onclick = event => {
        const button = event.target.closest(".choose-recipe-item");
        if (button) selectRecipeForSlot(Number(button.dataset.id));
    };
}

async function openChooseRecipeModal(day, meal) {
    const slot = { day, meal };
    currentEditSlot = slot;
    recipeOptions = null;
    const modal = byId("chooseRecipeModal");
    const dayLabel = byId("chooseRecipeDay");
    const searchInput = byId("recipeSearchInput");
    const list = byId("chooseRecipeList");
    const people = byId("slotPeople");
    people.value = weeklyMenu[day]?.[meal]?.people || weekPeople;
    people.setCustomValidity("");

    dayLabel.textContent = `${capitalize(day)} (${meal})`;
    searchInput.value = "";
    modal.classList.remove("hidden");
    list.innerHTML = '<p class="choose-recipe-empty">Cargando recetas...</p>';

    try {
        const result = await api(`/recipes?meal=${meal}`);
        if (currentEditSlot !== slot) return;
        recipeOptions = result;
        renderChooseRecipeList();
    } catch {
        if (currentEditSlot === slot) list.innerHTML = '<p class="choose-recipe-empty">No se pudieron cargar las recetas.</p>';
    }

    searchInput.focus();
}

function closeChooseRecipeModal() {
    byId("chooseRecipeModal").classList.add("hidden");
    currentEditSlot = null;
}

function renderChooseRecipeList() {
    if (!recipeOptions) return;
    const list = byId("chooseRecipeList");
    const query = byId("recipeSearchInput").value.trim().toLowerCase();
    const { recipes, has_recipes } = recipeOptions;
    const filtered = recipes.filter(recipe => recipe.name.toLowerCase().includes(query));
    if (!filtered.length) {
        const message = !has_recipes
            ? "Todavía no tienes recetas guardadas.<br>Añade alguna primero."
            : recipes.length
                ? "No hay recetas que coincidan."
                : `No tienes recetas válidas para la ${currentEditSlot.meal}.`;
        list.innerHTML = `<p class="choose-recipe-empty">${message}</p>`;
        return;
    }

    list.innerHTML = filtered.map(r => `
        <button class="choose-recipe-item" data-id="${r.id}">
            <span class="choose-recipe-name">${escapeHtml(r.name)} ${typeBadge(r.type)}</span>
            <span class="choose-recipe-count">${r.ingredients.length} ingredientes</span>
        </button>
    `).join("");

}

async function selectRecipeForSlot(recipeId) {
    if (!currentEditSlot) return;
    const { day, meal } = currentEditSlot;
    const input = byId("slotPeople");
    if (!canWrite() || !input.reportValidity()) return;
    try {
        await saveMenuSlot(day, meal, recipeId, input.value ? Number(input.value) : null);
    } catch (e) {
        alert(e.message);
    }
    closeChooseRecipeModal();
    loadWeeklyMenu();
}

// Click y drag & drop sobre cada hueco (comida / cena)
function setupWeekGridEvents() {
    const grid = byId("weekGrid");

    grid.addEventListener("click", async (e) => {
        if (!canWrite()) return;
        if (e.target.closest(".slot-people")) {
            if (e.target.closest(".reset-people")) await updateSlotPeople(e.target.closest(".meal-slot"), null);
            return;
        }
        const slot = e.target.closest(".meal-slot");
        if (!slot) return;
        openChooseRecipeModal(slot.dataset.day, slot.dataset.meal);
    });

    grid.addEventListener("change", async (e) => {
        if (!canWrite() || !e.target.matches(".slot-people input") || !e.target.reportValidity()) return;
        await updateSlotPeople(e.target.closest(".meal-slot"), Number(e.target.value));
    });
    grid.addEventListener("keydown", e => {
        if (e.key === "Enter" && e.target.matches(".slot-people input")) e.target.blur();
    });
    grid.addEventListener("dragstart", (e) => {
        if (!canWrite() || e.target.closest(".slot-people")) { e.preventDefault(); return; }
        const slot = e.target.closest(".meal-slot");
        if (!slot) return;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", `${slot.dataset.day}|${slot.dataset.meal}`);
        slot.classList.add("dragging");
    });

    grid.addEventListener("dragend", (e) => {
        const slot = e.target.closest(".meal-slot");
        if (slot) slot.classList.remove("dragging");
        grid.querySelectorAll(".meal-slot.drag-over").forEach(s => {
            s.classList.remove("drag-over");
        });
    });

    grid.addEventListener("dragover", (e) => {
        const slot = e.target.closest(".meal-slot");
        if (!slot) return;
        e.preventDefault();
        slot.classList.add("drag-over");
    });

    grid.addEventListener("dragleave", (e) => {
        const slot = e.target.closest(".meal-slot");
        if (slot) slot.classList.remove("drag-over");
    });

    grid.addEventListener("drop", async (e) => {
        if (!canWrite()) return;
        const slot = e.target.closest(".meal-slot");
        if (!slot) return;
        e.preventDefault();
        slot.classList.remove("drag-over");

        const [fromDay, fromMeal] = (e.dataTransfer.getData("text/plain") || "").split("|");
        const toDay = slot.dataset.day;
        const toMeal = slot.dataset.meal;

        if (!fromDay || !fromMeal) return;
        if (fromDay === toDay && fromMeal === toMeal) return;

        try {
            await api("/menu/swap", "POST", {
                day1: fromDay, meal1: fromMeal,
                day2: toDay, meal2: toMeal
            });
        } catch (err) {
            alert(err.message);
        }
        loadWeeklyMenu();
    });
}

async function updateSlotPeople(slot, people) {
    const { day, meal } = slot.dataset;
    const input = slot.querySelector("input");
    input.disabled = true;
    try {
        await saveMenuSlot(day, meal, weeklyMenu[day][meal].id, people);
    } catch (err) { alert("No se pudieron guardar los comensales: " + err.message); }
    await loadWeeklyMenu();
}

function saveMenuSlot(day, meal, recipeId, people) {
    return api(`/menu/${encodeURIComponent(day)}/${meal}`, "POST", { recipe_id: recipeId, people });
}
