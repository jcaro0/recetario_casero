const MEALS = [
    { key: "comida", label: "Comida", icon: "🍽️" },
    { key: "cena", label: "Cena", icon: "🌙" }
];

let currentEditSlot = null; // { day, meal }
let recipeOptions = null;
let weeklyMenu = {};
let menuDays = [];
let savingWeekPeople = false;
let weekPeople = 2;

document.addEventListener("DOMContentLoaded", () => {
    byId("shareMenuButton").onclick = event => shareMenu(event.currentTarget);
    loadWeeklyMenu();
    document.addEventListener("recetario:refreshed", loadWeeklyMenu);
    byId("generateButton").onclick = event => confirmRegenerate(event.currentTarget);
    byId("weekPeopleForm").onsubmit = async e => {
        e.preventDefault();
        const input = byId("weekPeople");
        if (!canWrite() || savingWeekPeople || !input.reportValidity()) return;
        savingWeekPeople = true;
        const button = e.currentTarget.querySelector("button");
        button.disabled = input.disabled = true;
        byId("weekPeopleStatus").textContent = "Aplicando comensales…";
        try {
            await api("/menu/people", "POST", { people: Number(input.value) });
            await loadWeeklyMenu();
            notify("Comensales actualizados", "success");
        } catch (err) {
            notify("No se pudieron guardar los comensales. " + err.message, "error");
        } finally {
            savingWeekPeople = false;
            byId("weekPeopleStatus").textContent = "";
            button.disabled = input.disabled = false;
            applyWriteAccess();
        }
    };
    setupChooseRecipeModal();
    setupWeekGridEvents();
});

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

function shareMenu(trigger) {
    const hasRecipes = menuDays.some(day => MEALS.some(meal => weeklyMenu[day]?.[meal.key]?.name));
    const text = hasRecipes ? "🍽️ MENÚ SEMANAL\n\n" + menuDays.map(day => [
        capitalize(day),
        ...MEALS.map(meal => `  ${meal.label}: ${weeklyMenu[day]?.[meal.key]?.name || "Sin receta"}`)
    ].join("\n")).join("\n\n") : "";
    shareContent("Menú semanal", text, trigger);
}

// Carga del menú semanal
function slotHtml(dayKey, meal, recipe) {
    const name = recipe?.name || "Sin receta";
    const count = recipe?.ingredients?.length || 0;
    return `
        <div class="meal-slot" data-write-drag
             data-day="${dayKey}" data-meal="${meal.key}">
            <div class="meal-label">${meal.icon} ${meal.label}</div>
            <button type="button" class="food" data-write aria-haspopup="dialog"
                aria-label="Cambiar ${meal.label.toLowerCase()} de ${escapeHtml(dayKey)}: ${escapeHtml(name)}">
                ${escapeHtml(name)}
                ${recipe?.id ? `<small>${count} ${count === 1 ? "ingrediente" : "ingredientes"}</small>` : ""}
            </button>
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
    if (!grid.querySelector(".day-card")) grid.innerHTML = '<p class="loading-state">Cargando menú…</p>';
    try {
        // Peticiones en paralelo: días, ¿hay recetas suficientes? y menú
        const [days, status, menu, settings] = await Promise.all([
            api("/days"),
            api("/menu/status"),
            api("/menu"), api("/menu/people")
        ]);
        weeklyMenu = menu;
        menuDays = days;
        weekPeople = settings.people;
        byId("weekPeople").value = weekPeople;

        // Un menú ya planificado sigue accesible aunque después se borren recetas.
        if (!status.enough && !Object.values(menu).some(meals => Object.values(meals).some(r => r.id))) {
            generateButton.hidden = true;
            document.querySelector("[data-write-hint]").hidden = true;
            grid.innerHTML = emptyStateHtml("No hay suficientes recetas");
            return;
        }
        generateButton.hidden = !status.enough;
        document.querySelector("[data-write-hint]").hidden = false;

        grid.innerHTML = days.map(day => {
            const meals = menu[day];
            return `
                <div class="day-card" data-day="${day}">
                    <h3 class="day-heading">${escapeHtml(capitalize(day))}</h3>
                    ${MEALS.map(m => slotHtml(day, m, meals[m.key])).join("")}
                </div>
            `;
        }).join("");
    } catch (e) {
        grid.innerHTML = `<p>${escapeHtml(e.message)}</p>`;
    } finally {
        applyWriteAccess();
    }
}

function confirmRegenerate(trigger) {
    confirmAction({
        title: "¿Regenerar el menú?",
        message: "Se sustituirán las comidas y cenas de la semana.",
        label: "Regenerar menú",
        trigger,
        destructive: true,
        number: { label: "Comensales de la semana", value: weekPeople },
        action: people => api("/menu/generate", "POST", { people }),
        onSuccess: async () => {
            await loadWeeklyMenu();
            notify("Menú semanal regenerado", "success");
        },
        progress: "Regenerando menú…",
        errorPrefix: "No se pudo regenerar el menú. "
    });
}

// Modal selector de receta
function setupChooseRecipeModal() {
    byId("chooseRecipeModal").addEventListener("close", () => {
        if (!byId("chooseRecipeModal").open) currentEditSlot = null;
    });
    byId("recipeSearchInput").oninput = () => renderChooseRecipeList();
    byId("chooseRecipeList").onclick = event => {
        const button = event.target.closest(".choose-recipe-item");
        if (button) selectRecipeForSlot(button);
    };
}

async function openChooseRecipeModal(day, meal, trigger) {
    if (byId("chooseRecipeModal").open) return;
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
    list.innerHTML = '<p class="loading-state">Cargando recetas…</p>';
    if (!openDialog(modal, trigger)) return;

    try {
        const result = await api(`/recipes?meal=${meal}`);
        if (currentEditSlot !== slot || !modal.open) return;
        recipeOptions = result;
        renderChooseRecipeList();
    } catch {
        if (currentEditSlot === slot && modal.open) {
            list.innerHTML = '<p class="choose-recipe-empty">No se pudieron cargar las recetas.</p>';
        }
    }
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

async function selectRecipeForSlot(button) {
    if (!currentEditSlot) return;
    const { day, meal } = currentEditSlot;
    const input = byId("slotPeople");
    if (!input.reportValidity()) return;
    const people = input.value ? Number(input.value) : null;
    const saved = await runDialogAction(byId("chooseRecipeModal"),
        () => saveMenuSlot(day, meal, Number(button.dataset.id), people),
        button, "Guardando comida o cena…", "No se pudo cambiar la receta. ");
    if (!saved) return;
    await loadWeeklyMenu();
    const slot = [...document.querySelectorAll(".meal-slot")].find(slot =>
        slot.dataset.day === day && slot.dataset.meal === meal);
    slot?.querySelector(".food").focus({ preventScroll: true });
    notify("Menú actualizado", "success");
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
        openChooseRecipeModal(slot.dataset.day, slot.dataset.meal, slot.querySelector(".food"));
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
            notify("No se pudieron intercambiar las recetas. " + err.message, "error");
        }
        loadWeeklyMenu();
    });
}

async function updateSlotPeople(slot, people) {
    const { day, meal } = slot.dataset;
    const input = slot.querySelector("input");
    if (input.disabled) return;
    input.disabled = true;
    slot.querySelector(".reset-people").disabled = true;
    try {
        await saveMenuSlot(day, meal, weeklyMenu[day][meal].id, people);
    } catch (err) { notify("No se pudieron guardar los comensales. " + err.message, "error"); }
    await loadWeeklyMenu();
}

function saveMenuSlot(day, meal, recipeId, people) {
    return api(`/menu/${encodeURIComponent(day)}/${meal}`, "POST", { recipe_id: recipeId, people });
}
