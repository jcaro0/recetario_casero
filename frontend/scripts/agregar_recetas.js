let pendingRecipe = null;
let editingRecipeId = null;
let savingRecipe = false;

document.addEventListener("DOMContentLoaded", () => {
    setupDuplicateModal();
    byId("recipeForm").addEventListener("submit", saveRecipe);
    byId("recipeForm").addEventListener("keydown", advanceOnEnter);
    byId("addStep").onclick = () => addPreparationStep().focus();
    loadRecipeForm();
    document.addEventListener("recetario:refreshed", event => {
        if (event.detail.recovered) loadRecipeForm();
    });
    document.addEventListener("recetario:locked", () => { pendingRecipe = null; });
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
            byId("recipeForm").querySelector(".submitButton").lastChild.textContent = " Guardar cambios";
            document.querySelector(".recipeHero h1").textContent = "Editar receta";
            document.querySelector(".logo span").textContent = "Editar receta";
            byId("typeChangeHint").classList.remove("hidden");
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

async function submitRecipe(recipe) {
    if (!canWrite() || savingRecipe) return;
    savingRecipe = true;
    byId("recipeFields").disabled = true;
    try {
        if (editingRecipeId === null) {
            await api("/recipes", "POST", recipe);
        } else {
            await api(`/recipes/${editingRecipeId}`, "PUT", recipe);
        }
        if (editingRecipeId !== null) location.href = "recetas.html";
        else { resetRecipeForm(); byId("formStatus").textContent = "Receta guardada."; }
    } catch (err) {
        byId("formStatus").textContent = "No se pudo guardar: " + err.message;
    } finally {
        savingRecipe = false;
        byId("recipeFields").disabled = false;
        applyWriteAccess();
    }
}

async function saveRecipe(e) {
    e.preventDefault();
    // Solo el botón Guardar puede enviar: ningún envío implícito desde otro campo.
    if (!canWrite() || !e.submitter?.matches('.submitButton') || savingRecipe) return;
    if (!byId("recipeForm").reportValidity()) return;
    const recipe = collectRecipe();
    if (!recipe.name) { byId("recipeName").focus(); return; }
    if (!recipe.ingredients.length) {
        const input = document.querySelector(".ingredient-name");
        input.setCustomValidity("Añade al menos un ingrediente"); input.reportValidity(); return;
    }
    byId("formStatus").textContent = "Guardando receta…";
    if (editingRecipeId !== null) { await submitRecipe(recipe); return; }
    // Se mantiene la comprobación de duplicados para las recetas nuevas.
    savingRecipe = true;
    try {
        const result = await api("/recipes/check-duplicate", "POST", { ingredients: recipe.ingredients });
        savingRecipe = false;
        if (result.duplicate) openDuplicateModal(recipe, result.duplicate.name);
        else await submitRecipe(recipe);
    } catch (err) {
        byId("formStatus").textContent = "No se pudo comprobar la receta: " + err.message;
    } finally { savingRecipe = false; }
}

// ---------------------------------------------------------
// Modal de receta duplicada
// ---------------------------------------------------------

function setupDuplicateModal() {
    byId("duplicateYes").onclick = async () => {
        const recipe = pendingRecipe;
        closeDuplicateModal();
        if (recipe) await submitRecipe(recipe); // guarda y limpia el formulario
    };

    // "No" (o tocar fuera / Escape): se cierra sin guardar y el formulario se queda como está
    byId("duplicateNo").onclick = closeDuplicateModal;

    dismissModalOnBackdropOrEscape("duplicateModal", closeDuplicateModal);
}

function openDuplicateModal(recipe, existingName) {
    pendingRecipe = recipe;
    byId("formStatus").textContent = "Ya existe una receta con estos ingredientes. Confirma si quieres añadir otra.";
    byId("duplicateModalText").textContent =
        `Esta es la misma receta que: ${existingName}? Quiere agregarla?`;
    byId("duplicateModal").classList.remove("hidden");
    byId("duplicateNo").focus();
}

function closeDuplicateModal() {
    pendingRecipe = null;
    byId("duplicateModal").classList.add("hidden");
}
