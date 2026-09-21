// El frontend se sirve desde el mismo Flask que expone la API,
// así que las llamadas fetch("/menu"), fetch("/recipes")... son
// relativas a quien esté sirviendo la página (localhost,
// raspberrypi.local, o lo que sea) y no hace falta ninguna URL fija.

// ---------- DÍAS ----------
const DAYS = [
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes"
];

// Día que se está editando en el modal de "elegir receta"
let currentEditDay = null;

// Caché de recetas cargadas para el modal de elegir receta (evita
// pedirlas de nuevo cada vez que el usuario escribe en el buscador)
let allRecipesCache = [];

// ---------- INICIO ----------

// Si habíamos hecho scroll hacia abajo (por ejemplo en la lista de
// recetas o en el menú semanal), la transición de deslizamiento
// entre páginas puede "saltar" o verse rayada porque la página
// vieja se capturaba desplazada y la nueva siempre empieza arriba.
// Subimos el scroll justo antes de navegar para que la animación
// salga siempre limpia, también en la segunda navegación y
// siguientes.
document.addEventListener("click",(e)=>{

    const link = e.target.closest("a[href]");
    if(!link) return;
    if(link.target === "_blank") return;

    let url;
    try{
        url = new URL(link.href, location.href);
    }catch{
        return;
    }

    if(url.origin !== location.origin) return;

    window.scrollTo(0,0);

});

document.addEventListener("DOMContentLoaded", () => {

    setupShareDropdown();

    const page = window.location.pathname.split("/").pop();

    if(page === "index.html" || page === ""){
        loadWeeklyMenu();
        setupModal();
        setupChooseRecipeModal();
        setupWeekGridEvents();
    }

    if(page === "lista_compra.html"){
        loadShoppingList();
    }

    if(page === "recetas.html"){
        loadRecipesView();
        setupRecipeExpansion();
    }

    if(page === "agregar_recetas.html"){
        setupRecipeForm();
    }

});

// =======================================================
// MENÚ SEMANAL
// =======================================================

async function loadWeeklyMenu(){

    const grid = document.getElementById("weekGrid");
    if(!grid) return;

    grid.innerHTML = "<p>Cargando menú...</p>";

    try{

        const res = await fetch("/menu");
        const menu = await res.json();

        grid.innerHTML = "";

        DAYS.forEach(day=>{

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
                        Toca para cambiar · arrastra para mover
                    </div>

                </div>
            `;

        });

    }catch(e){

        grid.innerHTML = "<p>No se pudo cargar el menú.</p>";

    }

}

// ---------- Modal: regenerar menú ----------

function setupModal(){

    const modal = document.getElementById("modal");
    const open = document.getElementById("generateButton");
    const cancel = document.getElementById("cancelModal");
    const confirm = document.getElementById("confirmModal");

    open.onclick = ()=> modal.classList.remove("hidden");

    cancel.onclick = ()=> modal.classList.add("hidden");

    confirm.onclick = async ()=>{

        modal.classList.add("hidden");

        await fetch("/menu/generate",{
            method:"POST"
        });

        loadWeeklyMenu();

    }

}

// ---------- Modal: elegir receta para un día ----------

function setupChooseRecipeModal(){

    const modal = document.getElementById("chooseRecipeModal");
    const closeBtn = document.getElementById("closeChooseModal");
    const searchInput = document.getElementById("recipeSearchInput");

    closeBtn.onclick = ()=> closeChooseRecipeModal();

    // Tocar el fondo oscuro también cierra el modal
    modal.addEventListener("click",(e)=>{
        if(e.target === modal) closeChooseRecipeModal();
    });

    searchInput.addEventListener("input",()=>{
        renderChooseRecipeList(searchInput.value);
    });

}

async function openChooseRecipeModal(day){

    currentEditDay = day;

    const modal = document.getElementById("chooseRecipeModal");
    const dayLabel = document.getElementById("chooseRecipeDay");
    const searchInput = document.getElementById("recipeSearchInput");
    const list = document.getElementById("chooseRecipeList");

    dayLabel.textContent = capitalize(day);
    searchInput.value = "";

    modal.classList.remove("hidden");

    list.innerHTML = "<p class=\"choose-recipe-empty\">Cargando recetas...</p>";

    try{

        const res = await fetch("/recipes");
        allRecipesCache = await res.json();

        renderChooseRecipeList("");

    }catch{

        list.innerHTML = "<p class=\"choose-recipe-empty\">No se pudieron cargar las recetas.</p>";

    }

    searchInput.focus();

}

function closeChooseRecipeModal(){
    document.getElementById("chooseRecipeModal").classList.add("hidden");
    currentEditDay = null;
}

function renderChooseRecipeList(query){

    const list = document.getElementById("chooseRecipeList");
    const q = query.trim().toLowerCase();

    const filtered = allRecipesCache.filter(r=>
        r.name.toLowerCase().includes(q)
    );

    if(allRecipesCache.length === 0){
        list.innerHTML = `
            <p class="choose-recipe-empty">
                Todavía no tienes recetas guardadas.<br>Añade alguna primero.
            </p>
        `;
        return;
    }

    if(filtered.length === 0){
        list.innerHTML = "<p class=\"choose-recipe-empty\">No hay recetas que coincidan.</p>";
        return;
    }

    list.innerHTML = filtered.map(r => `
        <button class="choose-recipe-item" data-id="${r.id}">
            <span class="choose-recipe-name">${r.name}</span>
            <span class="choose-recipe-count">${r.ingredients.length} ingredientes</span>
        </button>
    `).join("");

    list.querySelectorAll(".choose-recipe-item").forEach(btn=>{
        btn.onclick = ()=> selectRecipeForDay(Number(btn.dataset.id));
    });

}

async function selectRecipeForDay(recipeId){

    if(!currentEditDay) return;

    await fetch(`/menu/${encodeURIComponent(currentEditDay)}`,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({recipe_id: recipeId})
    });

    closeChooseRecipeModal();
    loadWeeklyMenu();

}

// ---------- Tocar y arrastrar tarjetas de día ----------

function setupWeekGridEvents(){

    const grid = document.getElementById("weekGrid");
    if(!grid) return;

    // Tocar una tarjeta (sin arrastrar) abre el selector de receta
    grid.addEventListener("click",(e)=>{

        const card = e.target.closest(".day-card");
        if(!card) return;

        openChooseRecipeModal(card.dataset.day);

    });

    // Arrastrar una tarjeta sobre otra intercambia sus recetas
    grid.addEventListener("dragstart",(e)=>{

        const card = e.target.closest(".day-card");
        if(!card) return;

        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", card.dataset.day);

        card.classList.add("dragging");

    });

    grid.addEventListener("dragend",(e)=>{

        const card = e.target.closest(".day-card");
        if(card) card.classList.remove("dragging");

        grid.querySelectorAll(".day-card.drag-over").forEach(c=>{
            c.classList.remove("drag-over");
        });

    });

    grid.addEventListener("dragover",(e)=>{

        const card = e.target.closest(".day-card");
        if(!card) return;

        e.preventDefault();
        card.classList.add("drag-over");

    });

    grid.addEventListener("dragleave",(e)=>{

        const card = e.target.closest(".day-card");
        if(card) card.classList.remove("drag-over");

    });

    grid.addEventListener("drop", async (e)=>{

        const card = e.target.closest(".day-card");
        if(!card) return;

        e.preventDefault();
        card.classList.remove("drag-over");

        const fromDay = e.dataTransfer.getData("text/plain");
        const toDay = card.dataset.day;

        if(fromDay && toDay && fromDay !== toDay){

            await fetch("/menu/swap",{
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body: JSON.stringify({day1: fromDay, day2: toDay})
            });

            loadWeeklyMenu();

        }

    });

}

function capitalize(text){
    return text.charAt(0).toUpperCase() + text.slice(1);
}

// Formatea "cantidad + unidad" para mostrarlos, omitiendo lo que
// falte (ambos son opcionales, pero si hay cantidad siempre hay
// unidad porque el formulario lo exige).
function formatQtyUnit(qty, unit){

    if(qty === null || qty === undefined || qty === "") return "";

    return ` - ${qty}${unit ? " " + unit : ""}`;

}

// =======================================================
// COMPARTIR
// =======================================================

function setupShareDropdown(){

    const button = document.getElementById("shareMenuButton");
    const dropdown = document.getElementById("shareDropdown");

    if(!button || !dropdown) return;

    button.onclick = ()=>{

        dropdown.classList.toggle("hidden");

    }

    document.addEventListener("click",(e)=>{

        if(!dropdown.contains(e.target) && !button.contains(e.target))
            dropdown.classList.add("hidden");

    })

}

async function shareMenu(type){

    const res = await fetch("/menu");
    const menu = await res.json();

    let text = "🍽️ MENÚ SEMANAL\n\n";

    DAYS.forEach(day=>{

        const recipe = menu[day.toLowerCase()];
        text += `${day}: ${recipe?.name || "Sin receta"}\n`;

    });

    shareText(text,type);

}

async function shareShopping(type){

    const res = await fetch("/shopping-list");
    const shopping = await res.json();

    let text = "🛒 LISTA DE LA COMPRA\n\n";

    shopping.forEach(item=>{
        text += `• ${item.name} (${item.qty} ${item.unit})\n`;
    });

    shareText(text,type);

}

function shareText(text,type){

    switch(type){

        case "copy":
            navigator.clipboard.writeText(text);
            alert("Copiado al portapapeles");
            break;

        case "whatsapp":
            window.open(
                "https://wa.me/?text="+encodeURIComponent(text)
            );
            break;

        case "email":
            window.location =
                "mailto:?subject=Menú Semanal&body="+encodeURIComponent(text);
            break;

    }

}

// =======================================================
// LISTA COMPRA
// =======================================================

async function loadShoppingList(){

    const container = document.getElementById("shoppingList");

    container.innerHTML = "<p>Cargando...</p>";

    try{

        const res = await fetch("/shopping-list");
        const shopping = await res.json();

        if(shopping.length === 0){
            container.innerHTML = "<p>No hay nada en la lista todavía.</p>";
            return;
        }

        container.innerHTML = "";

        shopping.forEach(item=>{

            container.innerHTML += `
                <label class="shopping-item">

                    <input type="checkbox">

                    <div class="shopping-info">
                        <strong>${item.name}</strong>
                        <span>${formatQtyUnit(item.qty, item.unit).replace(/^\s*-\s*/, "")}</span>
                    </div>

                </label>
            `;

        });

    }catch{

        container.innerHTML = "<p>Error al cargar.</p>";

    }

}

// =======================================================
// AÑADIR RECETA
// =======================================================

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
            <option value="g">g · gramos</option>
            <option value="ml">ml · mililitros</option>
            <option value="uds">uds · unidades</option>
            <option value="cda">cda · cucharada</option>
            <option value="taza">taza · tazas</option>
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

    // Si se selecciona una unidad sin haber escrito cantidad previa,
    // regresa a Default ("") automáticamente.
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

async function saveRecipe(e) {
    e.preventDefault();

    const ingredients = [];

    document.querySelectorAll(".ingredient-row").forEach(row => {
        const nameInput = row.querySelector(".ingredient-name");
        const qtyInput = row.querySelector(".ingredient-qty");
        const unitSelect = row.querySelector(".ingredient-unit");

        const nameRaw = nameInput.value.trim();
        const qtyRaw = qtyInput.value.trim();
        let unitRaw = unitSelect.value;

        // Fila vacía al final, se descarta
        if (nameRaw === "") return;

        // Si no hay cantidad, no se guarda ni cantidad ni unidad
        if (qtyRaw === "") {
            ingredients.push({
                name: nameRaw,
                qty: null,
                unit: null
            });
            return;
        }

        ingredients.push({
            name: nameRaw,
            qty: Number(qtyRaw),
            unit: unitRaw === "" ? null : unitRaw
        });
    });

    await fetch("/recipes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name: document.getElementById("recipeName").value,
            ingredients
        })
    });

    document.getElementById("recipeForm").reset();

    const ingredientList = document.getElementById("ingredientList");
    ingredientList.innerHTML = "";
    ingredientList.appendChild(createIngredientRow());
}

// =======================================================
// VER RECETAS (recetas.html)
// =======================================================

async function loadRecipesView(){

    const list = document.getElementById("recipesContainer");
    if(!list) return;

    list.innerHTML = "<p>Cargando recetas...</p>";

    try{

        const res = await fetch("/recipes");
        const recipes = await res.json();

        if(recipes.length === 0){
            list.innerHTML = "<p>Todavía no has guardado ninguna receta.</p>";
            return;
        }

        list.innerHTML = recipes.map(recipe=>`
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
                    ${recipe.ingredients.map(i=>`
                        <li>${i.name}${formatQtyUnit(i.qty, i.unit)}</li>
                    `).join("")}
                </ul>

            </div>
        `).join("");

    }catch{

        list.innerHTML = "<p>Error.</p>";

    }

}

function setupRecipeExpansion(){

    // Un solo listener en el documento: si tocas dentro de una tarjeta
    // (que no sea el botón de borrar) se abre/cierra; si tocas fuera,
    // se cierra la que estuviera abierta. Así imitamos "focus/unfocus"
    // de forma fiable también en móvil.
    document.addEventListener("click",(e)=>{

        if(e.target.closest(".deleteRecipe")) return;

        const card = e.target.closest(".recipe-card");

        document.querySelectorAll(".recipe-card.expanded").forEach(c=>{
            if(c !== card) c.classList.remove("expanded");
        });

        if(card) card.classList.toggle("expanded");

    });

}

async function deleteRecipe(id){

    if(!confirm("¿Eliminar receta?"))
        return;

    await fetch("/recipes/"+id,{
        method:"DELETE"
    });

    loadRecipesView();

}