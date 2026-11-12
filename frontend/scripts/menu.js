const DAYS = [
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo"
];

const MEALS = [
    { key: "comida", label: "Comida", icon: "🍽️" },
    { key: "cena", label: "Cena", icon: "🌙" }
];

let currentEditSlot = null; // { day, meal }
let allRecipesCache = [];

document.addEventListener("DOMContentLoaded", () => {
    loadWeeklyMenu();
    setupModal();
    setupChooseRecipeModal();
    setupWeekGridEvents();
});

function mealLabel(key) {
    const meal = MEALS.find(m => m.key === key);
    return meal ? meal.label : key;
}

// Compartir menú semanal
async function shareMenu(type) {
    try {
        const menu = await api("/menu");
        let text = "🍽️ MENÚ SEMANAL\n\n";
        DAYS.forEach(day => {
            text += `${day}\n`;
            MEALS.forEach(meal => {
                const recipe = menu[day.toLowerCase()]?.[meal.key];
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
        </div>
    `;
}

async function loadWeeklyMenu() {
    const grid = document.getElementById("weekGrid");
    if (!grid) return;
    grid.innerHTML = "<p>Cargando menú...</p>";
    try {
        const menu = await api("/menu");
        grid.innerHTML = DAYS.map(day => {
            const dayKey = day.toLowerCase();
            const meals = menu[dayKey] || {};
            return `
                <div class="day-card" data-day="${dayKey}">
                    <div class="day-header">
                        <h3>${day}</h3>
                        <span>🍽️</span>
                    </div>
                    ${MEALS.map(m => slotHtml(dayKey, m, meals[m.key])).join("")}
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

    open.onclick = () => modal.classList.remove("hidden");
    cancel.onclick = () => modal.classList.add("hidden");
    confirm.onclick = async () => {
        modal.classList.add("hidden");
        try {
            const result = await api("/menu/generate", { method: "POST" });
            if (result && result.message) alert(result.message);
        } catch (e) {
            alert("No se pudo regenerar el menú: " + e.message);
        }
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

// Una receta 'comida' no entra en una cena (y al revés); 'ambos' y 'extra' valen siempre
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
    try {
        await api(`/menu/${encodeURIComponent(day)}/${encodeURIComponent(meal)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ recipe_id: recipeId })
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

    grid.addEventListener("click", (e) => {
        const slot = e.target.closest(".meal-slot");
        if (!slot) return;
        openChooseRecipeModal(slot.dataset.day, slot.dataset.meal);
    });

    grid.addEventListener("dragstart", (e) => {
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

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}