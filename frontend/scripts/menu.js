// Los días activos los decide el servidor (variable MENU_DAYS) y se piden a /days
let DAYS = []; // [{ key: "lunes", label: "Lunes" }, ...]

const MEALS = [
    { key: "comida", label: "Comida", icon: "🍽️" },
    { key: "cena", label: "Cena", icon: "🌙" }
];

let currentEditSlot = null; // { day, meal }
let allRecipesCache = [];
let weeklyMenu = {};
let weekPeople = 2;

document.addEventListener("DOMContentLoaded", () => {
    loadWeeklyMenu();
    setupModal();
    document.getElementById("weekPeopleForm").onsubmit = async e => {
        e.preventDefault();
        const input = document.getElementById("weekPeople");
        if (!input.reportValidity()) return;
        const button = e.currentTarget.querySelector("button");
        button.disabled = true;
        try {
            const result = await api("/menu/people", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({people:Number(input.value)})});
            weekPeople = result.people;
            document.getElementById("weekPeopleStatus").textContent = "Comensales actualizados";
            await loadWeeklyMenu();
        } catch (err) { document.getElementById("weekPeopleStatus").textContent = err.message; }
        finally { button.disabled = false; }
    };
    setupChooseRecipeModal();
    setupWeekGridEvents();
});

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

function setDays(keys) {
    DAYS = keys.map(key => ({ key, label: capitalize(key) }));
}

function mealLabel(key) {
    const meal = MEALS.find(m => m.key === key);
    return meal ? meal.label : key;
}

// Compartir menú semanal
async function shareMenu(type) {
    try {
        const [days, menu] = await Promise.all([api("/days"), api("/menu")]);
        setDays(days);
        let text = "🍽️ MENÚ SEMANAL\n\n";
        DAYS.forEach(day => {
            text += `${day.label}\n`;
            MEALS.forEach(meal => {
                const recipe = menu[day.key]?.[meal.key];
                text += `  ${meal.label}: ${recipe?.name || "Sin receta"}\n`;
            });
            text += "\n";
        });
        shareText(text.trim(), type, "Menú semanal");
    } catch (e) {
        alert("No se pudo compartir el menú: " + e.message);
    }
}

// Carga del menú semanal
function slotHtml(dayKey, meal, recipe) {
    const name = recipe?.name || "Sin receta";
    const count = recipe?.ingredients?.length || 0;
    return `
        <div class="meal-slot" draggable="true"
             data-day="${dayKey}" data-meal="${meal.key}">
            <div class="meal-label">${meal.icon} ${meal.label}</div>
            <div class="food">
                ${escapeHtml(name)}
                <small>${count} ingredientes</small>
            </div>
            ${recipe?.id ? `<div class="slot-people">Comensales
                <input type="number" min="1" max="2147483647" step="1" required value="${recipe.people || recipe.servings || 2}"
                    aria-label="Comensales de ${escapeHtml(dayKey)} ${meal.label.toLowerCase()}">
                <button type="button" class="reset-people" title="Usar las raciones originales">Originales (${recipe.servings || 2})</button>
            </div>` : ""}
        </div>
    `;
}

async function loadWeeklyMenu() {
    const grid = document.getElementById("weekGrid");
    const generateButton = document.getElementById("generateButton");
    if (!grid) return;
    grid.innerHTML = "<p>Cargando menú...</p>";
    try {
        // Peticiones en paralelo: días, ¿hay recetas suficientes? y menú
        const [days, status, menu, settings] = await Promise.all([
            api("/days"),
            api("/menu/status"),
            api("/menu"), api("/menu/people")
        ]);
        setDays(days);
        weeklyMenu = menu;
        weekPeople = settings.people;
        document.getElementById("weekPeople").value = weekPeople;

        // Un menú ya planificado sigue accesible aunque después se borren recetas.
        if (!status.enough && !Object.values(menu).some(meals => Object.values(meals).some(r => r?.id))) {
            if (generateButton) generateButton.style.display = "none";
            grid.innerHTML = emptyStateHtml("No hay suficientes recetas");
            return;
        }
        if (generateButton) generateButton.style.display = status.enough ? "" : "none";

        grid.innerHTML = DAYS.map(day => {
            const meals = menu[day.key] || {};
            return `
                <div class="day-card" data-day="${day.key}">
                    <div class="day-header">
                        <h3>${escapeHtml(day.label)}</h3>
                        <span>🍽️</span>
                    </div>
                    ${MEALS.map(m => slotHtml(day.key, m, meals[m.key])).join("")}
                    <div class="day-hint">
                        <span class="material-symbols-rounded">swap_horiz</span>
                        Toca para cambiar • arrastra para mover
                    </div>
                </div>
            `;
        }).join("");
    } catch (e) {
        grid.innerHTML = "<p>No se pudo cargar el menú.</p>";
    }
}

// Modal para regenerar menú
function setupModal() {
    const modal = document.getElementById("modal");
    const open = document.getElementById("generateButton");
    const cancel = document.getElementById("cancelModal");
    const confirm = document.getElementById("confirmModal");

    const people = document.getElementById("generatePeople");
    open.onclick = () => {
        people.value = weekPeople;
        modal.classList.remove("hidden");
        people.focus();
    };
    modal.addEventListener("click", e => { if (e.target === modal) cancel.click(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") { cancel.click(); closeChooseRecipeModal(); } });
    cancel.onclick = () => modal.classList.add("hidden");
    confirm.onclick = async () => {
        if (!people.reportValidity()) return;
        confirm.disabled = true;
        try {
            await api("/menu/generate", { method: "POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({people:Number(people.value)}) });
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
    const modal = document.getElementById("chooseRecipeModal");
    const closeBtn = document.getElementById("closeChooseModal");
    const searchInput = document.getElementById("recipeSearchInput");

    closeBtn.onclick = () => closeChooseRecipeModal();

    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeChooseRecipeModal();
    });

    searchInput.addEventListener("input", () => {
        renderChooseRecipeList(searchInput.value);
    });
}

async function openChooseRecipeModal(day, meal) {
    currentEditSlot = { day, meal };
    const modal = document.getElementById("chooseRecipeModal");
    const dayLabel = document.getElementById("chooseRecipeDay");
    const searchInput = document.getElementById("recipeSearchInput");
    const list = document.getElementById("chooseRecipeList");
    const people = document.getElementById("slotPeople");
    people.value = weeklyMenu[day]?.[meal]?.people || weekPeople;
    people.setCustomValidity("");

    dayLabel.textContent = `${capitalize(day)} (${mealLabel(meal).toLowerCase()})`;
    searchInput.value = "";
    modal.classList.remove("hidden");
    list.innerHTML = '<p class="choose-recipe-empty">Cargando recetas...</p>';

    try {
        allRecipesCache = await api("/recipes");
        renderChooseRecipeList("");
    } catch {
        list.innerHTML = '<p class="choose-recipe-empty">No se pudieron cargar las recetas.</p>';
    }

    searchInput.focus();
}

function closeChooseRecipeModal() {
    document.getElementById("chooseRecipeModal").classList.add("hidden");
    currentEditSlot = null;
}

// Una receta 'comida' no entra en una cena (y al revés); 'ambos' y 'extra' valen siempre.
// Al cambiar a mano se puede repetir receta libremente.
function fitsMeal(recipeType, meal) {
    return ["ambos", "extra", meal].includes(recipeType);
}

function renderChooseRecipeList(query) {
    const list = document.getElementById("chooseRecipeList");
    const q = query.trim().toLowerCase();
    const meal = currentEditSlot?.meal;

    if (allRecipesCache.length === 0) {
        list.innerHTML = `
            <p class="choose-recipe-empty">
                Todavía no tienes recetas guardadas.<br>Añade alguna primero.
            </p>
        `;
        return;
    }

    const compatible = allRecipesCache.filter(r => fitsMeal(r.type, meal));

    if (compatible.length === 0) {
        list.innerHTML = `
            <p class="choose-recipe-empty">
                No tienes recetas válidas para la ${escapeHtml(mealLabel(meal).toLowerCase())}.
            </p>
        `;
        return;
    }

    const filtered = compatible.filter(r => r.name.toLowerCase().includes(q));

    if (filtered.length === 0) {
        list.innerHTML = '<p class="choose-recipe-empty">No hay recetas que coincidan.</p>';
        return;
    }

    list.innerHTML = filtered.map(r => `
        <button class="choose-recipe-item" data-id="${r.id}">
            <span class="choose-recipe-name">${escapeHtml(r.name)} ${typeBadge(r.type)}</span>
            <span class="choose-recipe-count">${r.ingredients.length} ingredientes</span>
        </button>
    `).join("");

    list.querySelectorAll(".choose-recipe-item").forEach(btn => {
        btn.onclick = () => selectRecipeForSlot(Number(btn.dataset.id));
    });
}

async function selectRecipeForSlot(recipeId) {
    if (!currentEditSlot) return;
    const { day, meal } = currentEditSlot;
    const input = document.getElementById("slotPeople");
    if (!input.reportValidity()) return;
    try {
        await api(`/menu/${encodeURIComponent(day)}/${encodeURIComponent(meal)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ recipe_id: recipeId, people: input.value ? Number(input.value) : null })
        });
    } catch (e) {
        alert(e.message);
    }
    closeChooseRecipeModal();
    loadWeeklyMenu();
}

// Click y drag & drop sobre cada hueco (comida / cena)
function setupWeekGridEvents() {
    const grid = document.getElementById("weekGrid");
    if (!grid) return;

    grid.addEventListener("click", async (e) => {
        if (e.target.closest(".slot-people")) {
            if (e.target.closest(".reset-people")) await updateSlotPeople(e.target.closest(".meal-slot"), null);
            return;
        }
        const slot = e.target.closest(".meal-slot");
        if (!slot) return;
        openChooseRecipeModal(slot.dataset.day, slot.dataset.meal);
    });

    grid.addEventListener("change", async (e) => {
        if (!e.target.matches(".slot-people input") || !e.target.reportValidity()) return;
        await updateSlotPeople(e.target.closest(".meal-slot"), Number(e.target.value));
    });
    grid.addEventListener("keydown", e => {
        if (e.key === "Enter" && e.target.matches(".slot-people input")) e.target.blur();
    });
    grid.addEventListener("dragstart", (e) => {
        if (e.target.closest(".slot-people")) { e.preventDefault(); return; }
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
            await api("/menu/swap", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    day1: fromDay, meal1: fromMeal,
                    day2: toDay, meal2: toMeal
                })
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
        await api(`/menu/${encodeURIComponent(day)}/${meal}`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ recipe_id: weeklyMenu[day][meal].id, people })
        });
    } catch (err) { alert("No se pudieron guardar los comensales: " + err.message); }
    await loadWeeklyMenu();
}
