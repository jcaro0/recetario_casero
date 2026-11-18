let pendingRecipe = null; // receta a la espera de que se confirme el duplicado

document.addEventListener("DOMContentLoaded", () => {
    setupRecipeForm();
    setupDuplicateModal();
});

function setupRecipeForm() {
    const ingredientList = document.getElementById("ingredientList");
    ingredientList.appendChild(createIngredientRow());
    document.getElementById("recipeForm")
        .addEventListener("submit", saveRecipe);
}

function createIngredientRow() {
    const div = document.createElement("div");
    div.className = "ingredient-row ghost";
    div.innerHTML = `
        <input placeholder="Nuevo ingrediente" class="ingredient-name">
        <input placeholder="Cantidad"
               class="ingredient-qty"
               type="number"
               min="0"
               step="any">
        <select class="ingredient-unit">
            <option value="">Default</option>
            <option value="g">g — gramos</option>
            <option value="ml">ml — mililitros</option>
            <option value="uds">uds — unidades</option>
            <option value="cda">cda — cucharada</option>
            <option value="taza">taza — tazas</option>
        </select>
        <button type="button" class="deleteIngredient">✕</button>
    `;

    const nameInput = div.querySelector(".ingredient-name");
    const qtyInput = div.querySelector(".ingredient-qty");
    const unitSelect = div.querySelector(".ingredient-unit");
    const deleteButton = div.querySelector("button");

    nameInput.addEventListener("input", () => {
        const hasText = nameInput.value.trim() !== "";
        const list = document.getElementById("ingredientList");
        div.classList.toggle("ghost", !hasText);
        if (hasText && div === list.lastElementChild) {
            list.appendChild(createIngredientRow());
        }
    });

    qtyInput.addEventListener("input", () => {
        unitSelect.classList.remove("invalid");
    });

    unitSelect.addEventListener("change", () => {
        if (qtyInput.value.trim() === "") {
            unitSelect.value = "";
        }
        unitSelect.classList.remove("invalid");
    });

    deleteButton.onclick = () => {
        const list = document.getElementById("ingredientList");
        div.remove();
        const last = list.lastElementChild;
        if (!last || !last.classList.contains("ghost")) {
            list.appendChild(createIngredientRow());
        }
    };

    return div;
}

// Lee el formulario y devuelve la receta lista para enviar
function collectRecipe() {
    const ingredients = [];

    document.querySelectorAll(".ingredient-row").forEach(row => {
        const nameRaw = row.querySelector(".ingredient-name").value.trim();
        const qtyRaw = row.querySelector(".ingredient-qty").value.trim();
        const unitRaw = row.querySelector(".ingredient-unit").value;

        if (nameRaw === "") return;

        if (qtyRaw === "") {
            ingredients.push({ name: nameRaw, qty: null, unit: null });
            return;
        }

        ingredients.push({
            name: nameRaw,
            qty: Number(qtyRaw),
            unit: unitRaw === "" ? null : unitRaw
        });
    });

    return {
        name: document.getElementById("recipeName").value,
        type: (document.querySelector('input[name="recipeType"]:checked') || {}).value || "ambos",
        ingredients
    };
}

function resetRecipeForm() {
    document.getElementById("recipeForm").reset();
    const ingredientList = document.getElementById("ingredientList");
    ingredientList.innerHTML = "";
    ingredientList.appendChild(createIngredientRow());
}

// Guarda la receta en el servidor. Si falla, NO se limpia el formulario.
async function submitRecipe(recipe) {
    try {
        await api("/recipes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(recipe)
        });
    } catch (err) {
        alert("No se pudo guardar la receta: " + err.message);
        return;
    }
    resetRecipeForm();
}

async function saveRecipe(e) {
    e.preventDefault();
    const recipe = collectRecipe();

    // Antes de guardar: ¿ya hay otra receta con exactamente los mismos ingredientes?
    let duplicate = null;
    try {
        const result = await api("/recipes/check-duplicate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ingredients: recipe.ingredients })
        });
        duplicate = result.duplicate;
    } catch (err) {
        alert("No se pudo comprobar si la receta ya existe: " + err.message);
        return;
    }

    if (duplicate) {
        openDuplicateModal(recipe, duplicate.name);
        return;
    }

    await submitRecipe(recipe);
}

// ---------------------------------------------------------
// Modal de receta duplicada
// ---------------------------------------------------------

function setupDuplicateModal() {
    const modal = document.getElementById("duplicateModal");

    document.getElementById("duplicateYes").onclick = async () => {
        const recipe = pendingRecipe;
        closeDuplicateModal();
        if (recipe) await submitRecipe(recipe); // guarda y limpia el formulario
    };

    // "No" (o tocar fuera / Escape): se cierra sin guardar y el formulario se queda como está
    document.getElementById("duplicateNo").onclick = closeDuplicateModal;

    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeDuplicateModal();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !modal.classList.contains("hidden")) {
            closeDuplicateModal();
        }
    });
}

function openDuplicateModal(recipe, existingName) {
    pendingRecipe = recipe;
    document.getElementById("duplicateModalText").textContent =
        `Esta es la misma receta que: ${existingName}? Quiere agregarla?`;
    document.getElementById("duplicateModal").classList.remove("hidden");
    document.getElementById("duplicateNo").focus();
}

function closeDuplicateModal() {
    pendingRecipe = null;
    document.getElementById("duplicateModal").classList.add("hidden");
}