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
    "Viernes",
    "Sábado",
    "Domingo"
];

// ---------- INICIO ----------
document.addEventListener("DOMContentLoaded", () => {

    setupShareDropdown();

    const page = window.location.pathname.split("/").pop();

    if(page === "index.html" || page === ""){
        loadWeeklyMenu();
        setupModal();
    }

    if(page === "lista_compra.html"){
        loadShoppingList();
    }

    if(page === "agregar_recetas.html"){
        setupRecipeForm();
        loadRecipes();
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

            const recipe = menu[day.toLowerCase()] || {};

            grid.innerHTML += `
                <div class="day-card">

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

                </div>
            `;

        });

    }catch(e){

        grid.innerHTML = "<p>No se pudo cargar el menú.</p>";

    }

}

// ---------- Modal ----------

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
        text += `${day}: ${recipe.name}\n`;

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

        container.innerHTML = "";

        shopping.forEach(item=>{

            container.innerHTML += `
                <label class="shopping-item">

                    <input type="checkbox">

                    <div class="shopping-info">
                        <strong>${item.name}</strong>
                        <span>${item.qty} ${item.unit}</span>
                    </div>

                </label>
            `;

        });

    }catch{

        container.innerHTML = "<p>Error al cargar.</p>";

    }

}

// =======================================================
// RECETAS
// =======================================================

function setupRecipeForm(){

    const addIngredient = document.getElementById("addIngredient");
    const ingredientList = document.getElementById("ingredientList");

    addIngredient.onclick = ()=>{

        ingredientList.appendChild(createIngredientRow());

    }

    document.getElementById("recipeForm")
        .addEventListener("submit",saveRecipe);

}

function createIngredientRow(){

    const div = document.createElement("div");
    div.className = "ingredient-row";

    div.innerHTML = `
        <input placeholder="Ingrediente" class="ingredient-name">

        <input placeholder="Cantidad"
               class="ingredient-qty"
               type="number">

        <input placeholder="Unidad"
               class="ingredient-unit">

        <button type="button" class="deleteIngredient">✕</button>
    `;

    div.querySelector("button").onclick = ()=> div.remove();

    return div;

}

async function saveRecipe(e){

    e.preventDefault();

    const form = new FormData();

    form.append(
        "name",
        document.getElementById("recipeName").value
    );

    const image = document.getElementById("recipeImage").files[0];

    if(image)
        form.append("image",image);

    const ingredients = [];

    document.querySelectorAll(".ingredient-row").forEach(row=>{

        ingredients.push({

            name: row.querySelector(".ingredient-name").value,

            qty: Number(
                row.querySelector(".ingredient-qty").value
            ),

            unit: row.querySelector(".ingredient-unit").value

        });

    });

    form.append("ingredients",JSON.stringify(ingredients));

    await fetch("/recipes",{

        method:"POST",
        body:form

    });

    document.getElementById("recipeForm").reset();
    document.getElementById("ingredientList").innerHTML="";

    loadRecipes();

}

async function loadRecipes(){

    const list = document.getElementById("recipesContainer");
    if(!list) return;

    list.innerHTML = "<p>Cargando recetas...</p>";

    try{

        const res = await fetch("/recipes");
        const recipes = await res.json();

        list.innerHTML = "";

        recipes.forEach(recipe=>{

            list.innerHTML += `
                <div class="recipe-card">

                    ${recipe.image ?
                        `<img src="/${recipe.image}" class="recipe-photo">`
                        :
                        `<div class="recipe-placeholder">🍲</div>`
                    }

                    <div class="recipe-content">

                        <h3>${recipe.name}</h3>

                        <ul>
                            ${recipe.ingredients.map(i=>`
                                <li>${i.name} - ${i.qty} ${i.unit}</li>
                            `).join("")}
                        </ul>

                    </div>

                    <button
                        class="deleteRecipe"
                        onclick="deleteRecipe(${recipe.id})">

                        <span class="material-symbols-rounded">delete</span>

                    </button>

                </div>
            `;

        });

    }catch{

        list.innerHTML = "<p>Error.</p>";

    }

}

async function deleteRecipe(id){

    if(!confirm("¿Eliminar receta?"))
        return;

    await fetch("/recipes/"+id,{
        method:"DELETE"
    });

    loadRecipes();

}