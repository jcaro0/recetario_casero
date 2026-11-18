document.addEventListener("DOMContentLoaded", () => {
    loadRecipesView();
    setupRecipeExpansion();
});

async function loadRecipesView() {
    const list = document.getElementById("recipesContainer");
    if (!list) return;
    list.innerHTML = "<p>Cargando recetas...</p>";
    try {
        const recipes = await api("/recipes");
        if (recipes.length === 0) {
            list.innerHTML = emptyStateHtml("No hay recetas añadidas");
            return;
        }
        list.innerHTML = recipes.map(recipe => `
            <div class="recipe-card" data-id="${recipe.id}">
                <div class="recipe-card-header">
                    <div>
                        <h3>${escapeHtml(recipe.name)}</h3>
                        <small>${recipe.ingredients.length} ingredientes · ${recipe.servings || 2} raciones</small>
                        ${typeBadge(recipe.type)}
                    </div>
                </div>
                <a class="editRecipe" href="agregar_recetas.html?id=${recipe.id}" aria-label="Editar ${escapeHtml(recipe.name)}">Editar</a>
                <button aria-label="Eliminar ${escapeHtml(recipe.name)}"
                    class="deleteRecipe"
                    onclick="deleteRecipe(${recipe.id})">
                    <span class="material-symbols-rounded">delete</span>
                </button>
                <div class="ingredients-panel"><h4>Ingredientes</h4><ul>
                    ${recipe.ingredients.map(i => `
                        <li>${escapeHtml(i.name)}${escapeHtml(formatQtyUnit(i.qty, i.unit))}</li>
                    `).join("")}
                </ul>
                ${(recipe.preparation || []).length ? `<h4>Preparación</h4><ol>${recipe.preparation.map(step => `<li class="recipe-text">${escapeHtml(step)}</li>`).join("")}</ol>` : ""}
                ${recipe.notes ? `<h4>Notas</h4><p class="recipe-text">${escapeHtml(recipe.notes)}</p>` : ""}
                </div>
            </div>
        `).join("");
    } catch {
        list.innerHTML = "<p>Error.</p>";
    }
}

function setupRecipeExpansion() {
    document.addEventListener("click", (e) => {
        if (e.target.closest(".deleteRecipe, .editRecipe")) return;
        const card = e.target.closest(".recipe-card");
        document.querySelectorAll(".recipe-card.expanded").forEach(c => {
            if (c !== card) c.classList.remove("expanded");
        });
        if (card) card.classList.toggle("expanded");
    });
}

async function deleteRecipe(id) {
    if (!confirm("¿Eliminar receta?")) return;
    try {
        await api("/recipes/" + id, { method: "DELETE" });
    } catch (e) {
        alert("No se pudo eliminar: " + e.message);
    }
    loadRecipesView();
}