let catalogRecipes = [];
let expandedRecipe = null;

const searchKey = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

document.addEventListener("DOMContentLoaded", () => {
    loadRecipesView();
    document.addEventListener("recetario:refreshed", loadRecipesView);
    byId("recipesContainer").addEventListener("click", onRecipeAction);
    byId("catalogSearch").addEventListener("input", renderRecipes);
});

async function loadRecipesView() {
    const list = byId("recipesContainer");
    if (!list.hasChildNodes()) list.innerHTML = '<p class="loading-state">Cargando recetas…</p>';
    try {
        catalogRecipes = await api("/recipes");
        renderRecipes();
    } catch (error) {
        list.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    }
}

function renderRecipes() {
    const list = byId("recipesContainer");
    const query = searchKey(byId("catalogSearch").value.trim());
    const recipes = catalogRecipes.filter(recipe =>
        searchKey([recipe.name, ...recipe.ingredients.map(ingredient => ingredient.name)].join(" ")).includes(query));
    if (!recipes.length) {
        list.innerHTML = catalogRecipes.length
            ? "<p>No hay recetas que coincidan.</p>" : emptyStateHtml("No hay recetas añadidas");
        return;
    }
    list.innerHTML = recipes.map(recipe => `
        <article class="recipe-card" data-id="${recipe.id}">
            <h2 class="recipe-card-title">
                <button type="button" class="recipe-card-header" aria-expanded="${expandedRecipe === recipe.id}" aria-controls="recipe-${recipe.id}">
                    <span class="recipe-name">${escapeHtml(recipe.name)}</span>
                    <span class="recipe-meta">
                        <span>${recipe.ingredients.length} ${recipe.ingredients.length === 1 ? "ingrediente" : "ingredientes"} · ${recipe.servings || 2} raciones</span>
                        ${typeBadge(recipe.type)}
                    </span>
                </button>
            </h2>
            <div class="recipe-actions">
                <a class="secondary editRecipe" data-write href="agregar_recetas.html?id=${recipe.id}"
                    aria-label="Editar ${escapeHtml(recipe.name)}">Editar</a>
                <button type="button" aria-label="Eliminar ${escapeHtml(recipe.name)}" aria-haspopup="dialog" class="icon-button deleteRecipe" data-write>
                    <span class="material-symbols-rounded" aria-hidden="true">delete</span>
                </button>
            </div>
            <div id="recipe-${recipe.id}" class="ingredients-panel"${expandedRecipe === recipe.id ? "" : " hidden"}>
                <button type="button" class="secondary shareRecipe" aria-label="Compartir ${escapeHtml(recipe.name)}" aria-haspopup="dialog">
                    <span class="material-symbols-rounded" aria-hidden="true">share</span> Compartir receta
                </button>
                <h3>Ingredientes</h3>
                <ul>${recipe.ingredients.map(ingredient => `<li>${escapeHtml(ingredientLine(ingredient))}</li>`).join("")}</ul>
                ${recipe.preparation?.length ? `<h3>Preparación</h3><ol>${recipe.preparation.map(step =>
                    `<li class="recipe-text">${escapeHtml(step)}</li>`).join("")}</ol>` : ""}
                ${recipe.notes ? `<h3>Notas</h3><p class="recipe-text">${escapeHtml(recipe.notes)}</p>` : ""}
            </div>
        </article>
    `).join("");
    applyWriteAccess();
}

function ingredientLine(ingredient) {
    const amount = formatQtyUnit(ingredient.qty, ingredient.unit) || ingredient.unit;
    return amount ? `${ingredient.name} — ${amount}` : ingredient.name;
}

function onRecipeAction(event) {
    const button = event.target.closest("button");
    const card = button?.closest(".recipe-card");
    if (!card) return;
    const recipe = catalogRecipes.find(recipe => recipe.id === Number(card.dataset.id));
    if (!recipe) return;
    if (button.matches(".recipe-card-header")) {
        expandedRecipe = expandedRecipe === recipe.id ? null : recipe.id;
        byId("recipesContainer").querySelectorAll(".recipe-card-header").forEach(trigger => {
            const expanded = Number(trigger.closest(".recipe-card").dataset.id) === expandedRecipe;
            trigger.setAttribute("aria-expanded", expanded);
            byId(trigger.getAttribute("aria-controls")).hidden = !expanded;
        });
    } else if (button.matches(".deleteRecipe")) {
        deleteRecipe(recipe, button);
    } else if (button.matches(".shareRecipe")) {
        const sections = [recipe.name, `${recipe.servings || 2} raciones`, "Ingredientes\n" +
            recipe.ingredients.map(ingredient => "• " + ingredientLine(ingredient)).join("\n")];
        if (recipe.preparation?.length) sections.push("Preparación\n" +
            recipe.preparation.map((step, index) => `${index + 1}. ${step}`).join("\n"));
        if (recipe.notes) sections.push("Notas\n" + recipe.notes);
        shareContent(recipe.name, sections.join("\n\n"), button);
    }
}

function deleteRecipe(recipe, trigger) {
    confirmAction({
        title: "¿Eliminar la receta?",
        message: `Se eliminará «${recipe.name}» del recetario. Esta acción no se puede deshacer.`,
        label: "Eliminar receta",
        trigger,
        destructive: true,
        progress: "Eliminando receta…",
        errorPrefix: "No se pudo eliminar la receta. ",
        action: () => api(`/recipes/${recipe.id}`, "DELETE"),
        onSuccess: async () => {
            if (expandedRecipe === recipe.id) expandedRecipe = null;
            await loadRecipesView();
            byId("catalogSearch").focus({ preventScroll: true });
            notify("Receta eliminada", "success");
        }
    });
}
