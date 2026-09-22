const DAYS = [
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes"
];

let currentEditDay = null;
let allRecipesCache = [];

document.addEventListener("DOMContentLoaded", () => {
    loadWeeklyMenu();
    setupModal();
    setupChooseRecipeModal();
    setupWeekGridEvents();
});

// Compartir menú semanal
async function shareMenu(type) {
    const res = await fetch("/menu");
    const menu = await res.json();
    let text = "🍽️ MENÚ SEMANAL\n\n";
    DAYS.forEach(day => {
        const recipe = menu[day.toLowerCase()];
        text += `${day}: ${recipe?.name || "Sin receta"}\n`;
    });
    shareText(text, type);
}

// Carga del menú semanal
async function loadWeeklyMenu() {
    const grid = document.getElementById("weekGrid");
    if (!grid) return;
    grid.innerHTML = "<p>Cargando menú...</p>";
    try {
        const res = await fetch("/menu");
        const menu = await res.json();
        grid.innerHTML = "";
        DAYS.forEach(day => {
            const dayKey = day.toLowerCase();
            const recipe = menu[dayKey] || {};
            grid.innerHTML += `
                <div class="day-card" draggable="true" data-day="${dayKey}">
                    <div class="day-header">
                        <h3>${day}</h3>
                        <span>🍽️</span>
                    </div>
                    <div class="food">
                        ${recipe.name || "Sin receta"}
                        <small>
                            ${recipe.ingredients?.length || 0} ingredientes
                        </small>
                    </div>
                    <div class="day-hint">
                        <span class="material-symbols-rounded">swap_horiz</span>
                        Toca para cambiar • arrastra para mover
                    </div>
                </div>
            `;
        });
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
        await fetch("/menu/generate", {
            method: "POST"
        });
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

async function openChooseRecipeModal(day) {
    currentEditDay = day;
    const modal = document.getElementById("chooseRecipeModal");
    const dayLabel = document.getElementById("chooseRecipeDay");
    const searchInput = document.getElementById("recipeSearchInput");
    const list = document.getElementById("chooseRecipeList");

    dayLabel.textContent = capitalize(day);
    searchInput.value = "";
    modal.classList.remove("hidden");
    list.innerHTML = '<p class="choose-recipe-empty">Cargando recetas...</p>';

    try {
        const res = await fetch("/recipes");
        allRecipesCache = await res.json();
        renderChooseRecipeList("");
    } catch {
        list.innerHTML = '<p class="choose-recipe-empty">No se pudieron cargar las recetas.</p>';
    }

    searchInput.focus();
}

function closeChooseRecipeModal() {
    document.getElementById("chooseRecipeModal").classList.add("hidden");
    currentEditDay = null;
}

function renderChooseRecipeList(query) {
    const list = document.getElementById("chooseRecipeList");
    const q = query.trim().toLowerCase();
    const filtered = allRecipesCache.filter(r =>
        r.name.toLowerCase().includes(q)
    );

    if (allRecipesCache.length === 0) {
        list.innerHTML = `
            <p class="choose-recipe-empty">
                Todavía no tienes recetas guardadas.<br>Añade alguna primero.
            </p>
        `;
        return;
    }

    if (filtered.length === 0) {
        list.innerHTML = '<p class="choose-recipe-empty">No hay recetas que coincidan.</p>';
        return;
    }

    list.innerHTML = filtered.map(r => `
        <button class="choose-recipe-item" data-id="${r.id}">
            <span class="choose-recipe-name">${r.name}</span>
            <span class="choose-recipe-count">${r.ingredients.length} ingredientes</span>
        </button>
    `).join("");

    list.querySelectorAll(".choose-recipe-item").forEach(btn => {
        btn.onclick = () => selectRecipeForDay(Number(btn.dataset.id));
    });
}

async function selectRecipeForDay(recipeId) {
    if (!currentEditDay) return;
    await fetch(`/menu/${encodeURIComponent(currentEditDay)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipe_id: recipeId })
    });
    closeChooseRecipeModal();
    loadWeeklyMenu();
}

// Drag & drop en tarjetas de días
function setupWeekGridEvents() {
    const grid = document.getElementById("weekGrid");
    if (!grid) return;

    grid.addEventListener("click", (e) => {
        const card = e.target.closest(".day-card");
        if (!card) return;
        openChooseRecipeModal(card.dataset.day);
    });

    grid.addEventListener("dragstart", (e) => {
        const card = e.target.closest(".day-card");
        if (!card) return;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", card.dataset.day);
        card.classList.add("dragging");
    });

    grid.addEventListener("dragend", (e) => {
        const card = e.target.closest(".day-card");
        if (card) card.classList.remove("dragging");
        grid.querySelectorAll(".day-card.drag-over").forEach(c => {
            c.classList.remove("drag-over");
        });
    });

    grid.addEventListener("dragover", (e) => {
        const card = e.target.closest(".day-card");
        if (!card) return;
        e.preventDefault();
        card.classList.add("drag-over");
    });

    grid.addEventListener("dragleave", (e) => {
        const card = e.target.closest(".day-card");
        if (card) card.classList.remove("drag-over");
    });

    grid.addEventListener("drop", async (e) => {
        const card = e.target.closest(".day-card");
        if (!card) return;
        e.preventDefault();
        card.classList.remove("drag-over");
        const fromDay = e.dataTransfer.getData("text/plain");
        const toDay = card.dataset.day;

        if (fromDay && toDay && fromDay !== toDay) {
            await fetch("/menu/swap", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ day1: fromDay, day2: toDay })
            });
            loadWeeklyMenu();
        }
    });
}

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}