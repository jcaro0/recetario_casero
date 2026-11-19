let catalogRecipes = [];
const searchKey = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
document.addEventListener("DOMContentLoaded", () => {
    loadRecipesView();
    document.addEventListener("recetario:refreshed", loadRecipesView);
    setupRecipeExpansion();
    byId("catalogSearch").addEventListener("input", renderRecipes);
});

async function loadRecipesView() {
    const list = byId("recipesContainer");
    list.innerHTML = "<p>Cargando recetas...</p>";
    try {
        catalogRecipes = await api("/recipes");
        if (catalogRecipes.length === 0) {
            list.innerHTML = emptyStateHtml("No hay recetas añadidas");
            return;
        }
        renderRecipes();
    } catch (error) {
        list.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    }
}

function renderRecipes() {
    const list = byId("recipesContainer");
    if (!catalogRecipes.length) return;
    const query = searchKey(byId("catalogSearch").value.trim());
    const recipes = catalogRecipes.filter(recipe => searchKey([recipe.name, ...recipe.ingredients.map(i => i.name)].join(" ")).includes(query));
    if (!recipes.length) { list.innerHTML = "<p>No hay recetas que coincidan.</p>"; return; }
    list.innerHTML = recipes.map(recipe => `
            <div class="recipe-card" data-id="${recipe.id}">
                <div class="recipe-card-header">
                    <div>
                        <h3>${escapeHtml(recipe.name)}</h3>
                        <small>${recipe.ingredients.length} ingredientes · ${recipe.servings || 2} raciones</small>
                        ${typeBadge(recipe.type)}
                    </div>
                </div>
                <a class="editRecipe" data-write href="agregar_recetas.html?id=${recipe.id}" aria-label="Editar ${escapeHtml(recipe.name)}">Editar</a>
                <button aria-label="Eliminar ${escapeHtml(recipe.name)}"
                    class="deleteRecipe" data-write
                    onclick="deleteRecipe(${recipe.id})">
                    <span class="material-symbols-rounded">delete</span>
                </button>
                <div class="ingredients-panel"><h4>Ingredientes</h4><ul>
                    ${recipe.ingredients.map(i => `
                        <li>${escapeHtml(i.name)}${escapeHtml(formatQtyUnit(i.qty, i.unit, " - "))}</li>
                    `).join("")}
                </ul>
                ${(recipe.preparation || []).length ? `<h4>Preparación</h4><ol>${recipe.preparation.map(step => `<li class="recipe-text">${escapeHtml(step)}</li>`).join("")}</ol>` : ""}
                ${recipe.notes ? `<h4>Notas</h4><p class="recipe-text">${escapeHtml(recipe.notes)}</p>` : ""}
                </div>
            </div>
        `).join("");
    applyWriteAccess();
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
    if (!canWrite() || !confirm("¿Eliminar receta?")) return;
    try {
        await api(`/recipes/${id}`, "DELETE");
    } catch (e) {
        alert("No se pudo eliminar: " + e.message);
    }
    loadRecipesView();
}
