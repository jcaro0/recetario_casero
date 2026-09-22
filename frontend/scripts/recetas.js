document.addEventListener("DOMContentLoaded", () => {
    loadRecipesView();
    setupRecipeExpansion();
});

async function loadRecipesView() {
    const list = document.getElementById("recipesContainer");
    if (!list) return;
    list.innerHTML = "<p>Cargando recetas...</p>";
    try {
        const res = await fetch("/recipes");
        const recipes = await res.json();
        if (recipes.length === 0) {
            list.innerHTML = "<p>Todavía no has guardado ninguna receta.</p>";
            return;
        }
        list.innerHTML = recipes.map(recipe => `
            <div class="recipe-card" data-id="${recipe.id}">
                <div class="recipe-card-header">
                    <span class="recipe-icon">🍲</span>
                    <div>
                        <h3>${recipe.name}</h3>
                        <small>${recipe.ingredients.length} ingredientes</small>
                    </div>
                </div>
                <button
                    class="deleteRecipe"
                    onclick="deleteRecipe(${recipe.id})">
                    <span class="material-symbols-rounded">delete</span>
                </button>
                <ul class="ingredients-panel">
                    ${recipe.ingredients.map(i => `
                        <li>${i.name}${formatQtyUnit(i.qty, i.unit)}</li>
                    `).join("")}
                </ul>
            </div>
        `).join("");
    } catch {
        list.innerHTML = "<p>Error.</p>";
    }
}

function setupRecipeExpansion() {
    document.addEventListener("click", (e) => {
        if (e.target.closest(".deleteRecipe")) return;
        const card = e.target.closest(".recipe-card");
        document.querySelectorAll(".recipe-card.expanded").forEach(c => {
            if (c !== card) c.classList.remove("expanded");
        });
        if (card) card.classList.toggle("expanded");
    });
}

async function deleteRecipe(id) {
    if (!confirm("¿Eliminar receta?")) return;
    await fetch("/recipes/" + id, {
        method: "DELETE"
    });
    loadRecipesView();
}