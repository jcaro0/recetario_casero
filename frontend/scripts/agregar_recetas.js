let editingRecipeId = null;
let savingRecipe = false;

document.addEventListener("DOMContentLoaded", () => {
    byId("recipeForm").addEventListener("submit", saveRecipe);
    byId("recipeName").oninput = event => event.target.setCustomValidity("");
    byId("recipeForm").addEventListener("keydown", advanceOnEnter);
    byId("addStep").onclick = () => addPreparationStep().focus();
    byId("cancelRecipe").onclick = event => { if (savingRecipe) event.preventDefault(); };
    loadRecipeForm();
    document.addEventListener("recetario:refreshed", event => {
        if (event.detail.recovered) loadRecipeForm();
    });
});

async function loadRecipeForm() {
    byId("recipeFields").disabled = true;
    byId("recipeForm").reset();
    byId("ingredientList").replaceChildren();
    byId("preparationList").replaceChildren();
    byId("formStatus").textContent = "";
    try {
        await initializeSnapshot();
        const id = new URLSearchParams(location.search).get("id");
        if (id !== null) {
            if (!/^\d+$/.test(id)) throw new Error("Identificador de receta no válido");
            editingRecipeId = Number(id);
            const recipe = await api(`/recipes/${editingRecipeId}`);
            document.title = "Editar receta";
            byId("saveRecipeLabel").textContent = "Guardar cambios";
            byId("recipeHeading").textContent = "Editar receta";
            byId("pageBrand").textContent = "Editar receta";
            byId("typeChangeHint").hidden = false;
            byId("recipeName").value = recipe.name;
            byId("recipeServings").value = recipe.servings || 2;
            byId(`type-${recipe.type || "ambos"}`).checked = true;
            recipe.ingredients.forEach(ing => byId("ingredientList").appendChild(createIngredientRow(ing)));
            (recipe.preparation || []).forEach(step => addPreparationStep(step));
            byId("recipeNotes").value = recipe.notes || "";
        }
        byId("ingredientList").appendChild(createIngredientRow());
        byId("recipeFields").disabled = false;
    } catch (err) {
        byId("formStatus").textContent = "No se pudo abrir la receta: " + err.message;
    } finally {
        applyWriteAccess();
    }
}

function createIngredientRow(ingredient = {}) {
    const div = document.createElement("div");
    div.className = "ingredient-row" + (ingredient.name ? "" : " ghost");
    div.innerHTML = `
        <input placeholder="Nuevo ingrediente" aria-label="Ingrediente" class="ingredient-name">
        <input placeholder="Cantidad" aria-label="Cantidad" class="ingredient-qty" inputmode="decimal">
        <button type="button" class="deleteIngredient" aria-label="Eliminar ingrediente">✕</button>`;
    const name = div.querySelector(".ingredient-name");
    const qty = div.querySelector(".ingredient-qty");
    const unit = createUnitSelector(null, () => Boolean(name.value.trim()));
    unit.element.querySelector("select").classList.add("ingredient-unit");
    div.insertBefore(unit.element, div.querySelector("button"));
    div.unitSelector = unit;
    name.value = ingredient.name || "";
    qty.value = ingredient.qty ?? "";
    unit.setValue(ingredient.unit);
    name.oninput = () => {
        div.classList.toggle("ghost", !name.value.trim());
        name.setCustomValidity("");
        unit.validate();
        if (name.value.trim() && div === byId("ingredientList").lastElementChild) {
            byId("ingredientList").appendChild(createIngredientRow());
        }
    };
    div.querySelector("button").onclick = () => {
        div.remove();
        const list = byId("ingredientList");
        if (!list.lastElementChild || !list.lastElementChild.classList.contains("ghost")) {
            list.appendChild(createIngredientRow());
        }
    };
    return div;
}

function addPreparationStep(text = "") {
    const row = document.createElement("div");
    row.className = "preparation-row";
    row.innerHTML = `<label></label><textarea rows="2" class="preparation-step"></textarea>
        <div class="step-actions">
            <button type="button" class="secondary move-up" aria-label="Subir paso">↑</button>
            <button type="button" class="secondary move-down" aria-label="Bajar paso">↓</button>
            <button type="button" class="deleteIngredient" aria-label="Eliminar paso">✕</button>
        </div>`;
    const textarea = row.querySelector("textarea");
    textarea.value = text;
    row.querySelector(".move-up").onclick = () => {
        if (row.previousElementSibling) row.previousElementSibling.before(row);
        numberSteps();
    };
    row.querySelector(".move-down").onclick = () => {
        if (row.nextElementSibling) row.nextElementSibling.after(row);
        numberSteps();
    };
    row.querySelector(".deleteIngredient").onclick = () => { row.remove(); numberSteps(); };
    byId("preparationList").appendChild(row);
    numberSteps();
    return textarea;
}

function numberSteps() {
    document.querySelectorAll(".preparation-row").forEach((row, index) => {
        const textarea = row.querySelector("textarea");
        textarea.id = `preparation-${index}`;
        row.querySelector("label").htmlFor = textarea.id;
        row.querySelector("label").textContent = `Paso ${index + 1}`;
        row.querySelector(".move-up").disabled = index === 0;
        row.querySelector(".move-down").disabled = !row.nextElementSibling;
    });
}

function advanceOnEnter(e) {
    if (e.key !== "Enter" || e.isComposing) return;
    const target = e.target;
    // Botones explícitos conservan su activación. Notas y Mayús+Enter son multilínea.
    if (target.closest("button, a") || target.id === "recipeNotes" ||
        (target.tagName === "TEXTAREA" && e.shiftKey)) return;
    e.preventDefault();
    if (target.classList.contains("preparation-step")) {
        const next = target.closest(".preparation-row").nextElementSibling;
        if (next) next.querySelector("textarea").focus();
        else if (target.value.trim()) addPreparationStep().focus();
        else byId("recipeNotes").focus();
        return;
    }
    const row = target.closest(".ingredient-row");
    if (row) {
        const inputs = Array.from(row.querySelectorAll("input:not(:disabled), select"));
        const index = inputs.indexOf(target);
        if (index === 0 && !target.value.trim()) {
            const step = document.querySelector(".preparation-step");
            (step || byId("addStep")).focus();
        } else if (index < inputs.length - 1) inputs[index + 1].focus();
        else {
            const next = row.nextElementSibling || byId("ingredientList").appendChild(createIngredientRow());
            next.querySelector("input").focus();
        }
        return;
    }
    if (target.id === "recipeName") byId("recipeServings").focus();
    else if (target.id === "recipeServings" || target.name === "recipeType") {
        byId("ingredientList").querySelector("input").focus();
    }
}

function collectRecipe() {
    const ingredients = Array.from(document.querySelectorAll(".ingredient-row")).map(row => ({
        name: row.querySelector(".ingredient-name").value.trim(),
        qty: row.querySelector(".ingredient-qty").value.trim() || null,
        unit: row.unitSelector.value || null
    })).filter(ing => ing.name);
    return {
        name: byId("recipeName").value.trim(),
        servings: Number(byId("recipeServings").value),
        type: document.querySelector('input[name="recipeType"]:checked').value,
        ingredients,
        preparation: Array.from(document.querySelectorAll(".preparation-step")).map(el => el.value.trim()).filter(Boolean),
        notes: byId("recipeNotes").value
    };
}

function resetRecipeForm() {
    byId("recipeForm").reset();
    byId("ingredientList").replaceChildren(createIngredientRow());
    byId("preparationList").replaceChildren();
}

function setRecipeSaving(saving) {
    savingRecipe = saving;
    byId("recipeFields").disabled = saving;
    byId("formStatus").textContent = saving ? "Guardando receta…" : "";
    if (!saving) applyWriteAccess();
}

function writeRecipe(recipe) {
    return editingRecipeId === null
        ? api("/recipes", "POST", recipe)
        : api(`/recipes/${editingRecipeId}`, "PUT", recipe);
}

function recipeSaved() {
    if (editingRecipeId === null) {
        resetRecipeForm();
        notify("Receta añadida correctamente", "success");
    } else {
        navigateWithNotice("recetas.html", "Cambios de la receta guardados");
    }
}

async function saveRecipe(event) {
    event.preventDefault();
    const trigger = event.submitter;
    if (!canWrite() || !trigger?.matches(".submitButton") || savingRecipe) return;
    if (!byId("recipeForm").reportValidity()) return;
    const recipe = collectRecipe();
    if (!recipe.name) {
        const name = byId("recipeName");
        name.setCustomValidity("Escribe el nombre de la receta.");
        name.reportValidity();
        return;
    }
    if (!recipe.ingredients.length) {
        const input = document.querySelector(".ingredient-name");
        input.setCustomValidity("Añade al menos un ingrediente");
        input.reportValidity();
        return;
    }

    let duplicate;
    dismissToast();
    setRecipeSaving(true);
    try {
        if (editingRecipeId === null) {
            const result = await api("/recipes/check-duplicate", "POST", { ingredients: recipe.ingredients });
            duplicate = result.duplicate;
        }
        if (!duplicate) await writeRecipe(recipe);
    } catch (error) {
        notify("No se pudo guardar la receta. " + error.message, "error");
        return;
    } finally {
        setRecipeSaving(false);
        if (canWrite()) trigger.focus({ preventScroll: true });
    }

    if (!duplicate) {
        recipeSaved();
        return;
    }
    confirmAction({
        title: "Ya hay una receta con esos ingredientes",
        message: `«${duplicate.name}» tiene los mismos ingredientes. ¿Quieres guardar otra receta?`,
        label: "Guardar receta",
        trigger,
        action: () => writeRecipe(recipe),
        onSuccess: recipeSaved,
        errorPrefix: "No se pudo guardar la receta. "
    });
}
