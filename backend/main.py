import math
import os
import random
from flask import Flask, request, jsonify
import database as db
from normalize import collapse_spaces

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_FOLDER = os.environ.get("FRONTEND_FOLDER", os.path.join(BASE_DIR, "..", "frontend"))

app = Flask(__name__, static_folder=FRONTEND_FOLDER, static_url_path="")

@app.route("/")
def serve_index():
    return app.send_static_file("menu.html")

@app.route("/<path:filename>")
def serve_frontend_file(filename):
    return app.send_static_file(filename)

@app.route("/days", methods=["GET"])
def api_get_days():
    return jsonify(db.DAYS)

def _slot_json(recipe):
    if recipe:
        return {"id": recipe["id"], "name": recipe["name"], "type": recipe["type"], "ingredients": recipe["ingredients"]}
    return {"name": None, "ingredients": []}

@app.route("/menu", methods=["GET"])
def api_get_menu():
    menu = db.get_menu()
    return jsonify({
        day: {meal: _slot_json(recipe) for meal, recipe in meals.items()}
        for day, meals in menu.items()
    })

def get_recipe_carbs(recipe):
    """Detecta qué tipo principal de carbohidrato tiene la receta."""
    carbs = set()
    for ing in recipe.get("ingredients", []):
        name = ing.get("name", "").lower()
        if "arroz" in name:
            carbs.add("arroz")
        elif "patata" in name:
            carbs.add("patata")
        elif any(p in name for p in ["pasta", "macarron", "espagueti", "fideo", "tallarin", "ravioli", "ñoqui"]):
            carbs.add("pasta")
    return carbs

def select_comidas_backtrack(pool, N, selected, used_carbs):
    """Busca una combinación de N comidas donde no se repitan los carbohidratos principales."""
    if len(selected) == N:
        return selected
    for i, recipe in enumerate(pool):
        rcarbs = get_recipe_carbs(recipe)
        if any(c in used_carbs for c in rcarbs):
            continue 
        new_used = used_carbs.union(rcarbs)
        res = select_comidas_backtrack(pool[:i] + pool[i+1:], N, selected + [recipe], new_used)
        if res:
            return res
    return None

def build_random_menu(recipes):
    N = len(db.DAYS)
    comidas = [r for r in recipes if r["type"] == "comida"]
    cenas = [r for r in recipes if r["type"] == "cena"]
    ambos = [r for r in recipes if r["type"] == "ambos"]

    random.shuffle(comidas)
    random.shuffle(cenas)
    random.shuffle(ambos)

    pool_comidas = comidas + ambos
    comidas_to_use = select_comidas_backtrack(pool_comidas, N, [], set())
    
    if not comidas_to_use:
        comidas_to_use = comidas[:N]
        needed = N - len(comidas_to_use)
        if needed > 0:
            comidas_to_use.extend(ambos[:needed])

    used_ids = {r["id"] for r in comidas_to_use}
    ambos_remaining = [r for r in ambos if r["id"] not in used_ids]

    cenas_to_use = cenas[:N]
    cenas_needed = N - len(cenas_to_use)
    if cenas_needed > 0:
        cenas_to_use.extend(ambos_remaining[:cenas_needed])

    random.shuffle(comidas_to_use)
    random.shuffle(cenas_to_use)

    assignments = {}
    for i, day in enumerate(db.DAYS):
        assignments[(day, "comida")] = comidas_to_use[i]["id"]
        assignments[(day, "cena")] = cenas_to_use[i]["id"]

    return assignments

@app.route("/menu/generate", methods=["POST"])
def api_generate_menu():
    recipes = [r for r in db.get_all_recipes() if r["type"] != "extra"]
    if not recipes:
        db.clear_menu()
        return jsonify({"ok": True, "message": "No hay recetas guardadas."})

    comidas_cnt = sum(1 for r in recipes if r["type"] == "comida")
    cenas_cnt = sum(1 for r in recipes if r["type"] == "cena")
    ambos_cnt = sum(1 for r in recipes if r["type"] == "ambos")
    N = len(db.DAYS)

    if comidas_cnt + ambos_cnt < N or cenas_cnt + ambos_cnt < N or comidas_cnt + cenas_cnt + ambos_cnt < 2 * N:
        return jsonify({"error": "No hay suficientes recetas"}), 400

    assignments = build_random_menu(recipes)
    db.replace_menu(assignments)
    return jsonify({"ok": True})

@app.route("/menu/<day>/generate", methods=["POST"])
def api_generate_day(day):
    """Regenera aleatoriamente un solo día respetando el resto de la semana."""
    if day not in db.DAYS:
        return jsonify({"error": "Día no válido"}), 400

    recipes = [r for r in db.get_all_recipes() if r["type"] != "extra"]
    current_menu = db.get_menu()

    used_recipe_ids = set()
    used_carbs = set()

    # Leemos qué recetas y carbohidratos están ocupados en el RESTO de días
    for d, meals in current_menu.items():
        if d != day:
            comida = meals.get("comida")
            cena = meals.get("cena")
            if comida:
                used_recipe_ids.add(comida["id"])
                used_carbs.update(get_recipe_carbs(comida))
            if cena:
                used_recipe_ids.add(cena["id"])

    # Filtramos la bolsa de recetas disponibles
    available_recipes = [r for r in recipes if r["id"] not in used_recipe_ids]
    
    # 1. Escoger comida intentando no repetir carbohidratos
    available_comidas = [r for r in available_recipes if r["type"] in ("comida", "ambos")]
    valid_comidas = [r for r in available_comidas if not get_recipe_carbs(r).intersection(used_carbs)]
    
    if not valid_comidas:
        valid_comidas = available_comidas # Fallback si nos quedamos sin opciones
        
    if not valid_comidas:
        return jsonify({"error": "No hay recetas suficientes sin usar para generar la comida."}), 400

    new_comida = random.choice(valid_comidas)

    # 2. Escoger cena excluyendo la comida que acabamos de poner
    available_cenas = [r for r in available_recipes if r["type"] in ("cena", "ambos") and r["id"] != new_comida["id"]]
    if not available_cenas:
        return jsonify({"error": "No hay recetas suficientes sin usar para generar la cena."}), 400
        
    new_cena = random.choice(available_cenas)

    # Guardamos los cambios de ese día concreto
    db.set_menu_slot(day, "comida", new_comida["id"])
    db.set_menu_slot(day, "cena", new_cena["id"])

    return jsonify({"ok": True})

@app.route("/menu/swap", methods=["POST"])
def api_swap_menu_slots():
    data = request.get_json(silent=True) or {}
    day1, meal1 = data.get("day1"), data.get("meal1")
    day2, meal2 = data.get("day2"), data.get("meal2")
    if day1 not in db.DAYS or day2 not in db.DAYS:
        return jsonify({"error": "Día no válido"}), 400
    if meal1 not in db.MEALS or meal2 not in db.MEALS:
        return jsonify({"error": "Comida no válida"}), 400
    try:
        db.swap_menu_slots(day1, meal1, day2, meal2)
    except db.IncompatibleMeal as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})

@app.route("/menu/<day>/<meal>", methods=["POST"])
def api_set_menu_slot(day, meal):
    if day not in db.DAYS:
        return jsonify({"error": "Día no válido"}), 400
    if meal not in db.MEALS:
        return jsonify({"error": "Comida no válida"}), 400
    data = request.get_json(silent=True) or {}
    recipe = db.get_recipe(data.get("recipe_id"))
    if not recipe:
        return jsonify({"error": "Receta no encontrada"}), 404
    if not db.fits_meal(recipe["type"], meal):
        return jsonify({"error": f"'{recipe['name']}' es una receta de {recipe['type']}, no se puede poner en la {meal}."}), 400
    
    db.set_menu_slot(day, meal, recipe["id"])
    return jsonify({"ok": True})

@app.route("/shopping-list", methods=["GET"])
def api_shopping_list():
    return jsonify(db.get_shopping_list())

@app.route("/shopping-list/tick", methods=["POST"])
def api_set_shopping_tick():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    unit = data.get("unit")
    checked = data.get("checked", False)
    if not name:
        return jsonify({"error": "Nombre es obligatorio"}), 400
    db.set_shopping_tick(name, unit, checked)
    return jsonify({"ok": True})

def clean_ingredients(raw):
    if not isinstance(raw, list): return []
    cleaned = []
    for ing in raw:
        if not isinstance(ing, dict): continue
        name = collapse_spaces(ing.get("name"))
        if not name: continue
        qty = ing.get("qty")
        if qty in (None, ""):
            qty = None
        else:
            try: qty = float(qty)
            except (TypeError, ValueError): qty = None
            else:
                if not math.isfinite(qty) or qty < 0: qty = None
        cleaned.append({"name": name, "qty": qty, "unit": ing.get("unit")})
    return cleaned

@app.route("/recipes", methods=["GET"])
def api_list_recipes():
    return jsonify(db.get_all_recipes())

@app.route("/recipes/check-duplicate", methods=["POST"])
def api_check_duplicate_recipe():
    data = request.get_json(silent=True) or {}
    ingredients = clean_ingredients(data.get("ingredients"))
    duplicate_name = db.check_duplicate_by_ingredients(ingredients)
    if duplicate_name:
        return jsonify({"duplicate": True, "name": duplicate_name})
    return jsonify({"duplicate": False})

@app.route("/recipes", methods=["POST"])
def api_create_recipe():
    data = request.get_json(silent=True) or {}
    name = collapse_spaces(data.get("name"))
    if not name: return jsonify({"error": "El nombre es obligatorio"}), 400
    recipe_type = collapse_spaces(data.get("type") or "ambos").lower()
    if recipe_type not in db.RECIPE_TYPES:
        return jsonify({"error": "Tipo no válido"}), 400
    
    recipe = db.create_recipe(name, clean_ingredients(data.get("ingredients")), recipe_type)
    return jsonify(recipe), 201

@app.route("/recipes/<int:recipe_id>", methods=["DELETE"])
def api_delete_recipe(recipe_id):
    db.delete_recipe(recipe_id)
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)