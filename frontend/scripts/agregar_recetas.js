document.addEventListener("DOMContentLoaded", () => {
    setupRecipeForm();
});

let pendingRecipeData = null;

function setupRecipeForm() {
    const ingredientList = document.getElementById("ingredientList");
    ingredientList.appendChild(createIngredientRow());
    document.getElementById("recipeForm").addEventListener("submit", handleRecipeSubmit);

    // Controles Modal de Duplicados
    document.getElementById("duplicateNoBtn").onclick = () => {
        document.getElementById("duplicateRecipeModal").classList.add("hidden");
        pendingRecipeData = null; // Cierra sin limpiar los inputs
    };

    document.getElementById("duplicateYesBtn").onclick = () => {
        document.getElementById("duplicateRecipeModal").classList.add("hidden");
        if (pendingRecipeData) {
            doSaveRecipe(pendingRecipeData);
        }
    };
}

function createIngredientRow() {
    const div = document.createElement("div");
    div.className = "ingredient-row ghost";
    div.innerHTML = `
        <input placeholder="Nuevo ingrediente" class="ingredient-name">
        <input placeholder="Cantidad" class="ingredient-qty" type="number" min="0" step="any">
        <select class="ingredient-unit">
            <option value="">Default</option>
            <option value="g">g – gramos</option>
            <option value="ml">ml – mililitros</option>
            <option value="uds">uds – unidades</option>
            <option value="cda">cda – cucharada</option>
            <option value="taza">taza – tazas</option>
        </select>
        <button type="button" class="deleteIngredient">✖</button>
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
        if (qtyInput.value.trim() === "") unitSelect.value = "";
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

async function handleRecipeSubmit(e) {
    e.preventDefault();
    const ingredients = [];
    document.querySelectorAll(".ingredient-row").forEach(row => {
        const nameInput = row.querySelector(".ingredient-name");
        const qtyInput = row.querySelector(".ingredient-qty");
        const unitSelect = row.querySelector(".ingredient-unit");

        const nameRaw = nameInput.value.trim();
        const qtyRaw = qtyInput.value.trim();
        let unitRaw = unitSelect.value;

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

    const recipeData = {
        name: document.getElementById("recipeName").value,
        type: (document.querySelector('input[name="recipeType"]:checked') || {}).value || "ambos",
        ingredients
    };

    try {
        const checkRes = await api("/recipes/check-duplicate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ingredients: recipeData.ingredients })
        });

        if (checkRes.duplicate) {
            pendingRecipeData = recipeData;
            document.getElementById("duplicateModalText").textContent = 
                `¿Esta es la misma receta que: ${checkRes.name}? ¿Quiere agregarla?`;
            document.getElementById("duplicateRecipeModal").classList.remove("hidden");
        } else {
            await doSaveRecipe(recipeData);
        }
    } catch (err) {
        alert("Error al comprobar receta duplicada: " + err.message);
    }
}

async function doSaveRecipe(recipeData) {
    try {
        await api("/recipes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(recipeData)
        });
    } catch (err) {
        alert("No se pudo guardar la receta: " + err.message);
        return;
    }

    document.getElementById("recipeForm").reset();
    const ingredientList = document.getElementById("ingredientList");
    ingredientList.innerHTML = "";
    ingredientList.appendChild(createIngredientRow());
    pendingRecipeData = null;
}