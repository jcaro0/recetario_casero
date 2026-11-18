import math
import os
import random

from flask import Flask, request, jsonify

import database as db
from normalize import collapse_spaces

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Carpeta del frontend. En docker-compose se monta en /app/frontend.
FRONTEND_FOLDER = os.environ.get(
    "FRONTEND_FOLDER", os.path.join(BASE_DIR, "..", "frontend")
)

app = Flask(__name__, static_folder=FRONTEND_FOLDER, static_url_path="")

# La base de datos se crea sola en la primera consulta (ver database.py).


# ---------------------------------------------------------
# FRONTEND (mismo servidor -> sin CORS ni URLs absolutas)
# ---------------------------------------------------------

@app.route("/")
def serve_index():
    return app.send_static_file("menu.html")


@app.route("/<path:filename>")
def serve_frontend_file(filename):
    # Sirve menu.html, style.css, script.js, lista_compra.html, etc.
    return app.send_static_file(filename)


# ---------------------------------------------------------
# DÍAS ACTIVOS (configurables con la variable de entorno MENU_DAYS)
# ---------------------------------------------------------

@app.route("/days", methods=["GET"])
def api_days():
    return jsonify(db.DAYS)


# ---------------------------------------------------------
# MENÚ SEMANAL (comida y cena de cada día)
# ---------------------------------------------------------

def _slot_json(recipe):
    if recipe:
        return recipe
    return {"name": None, "ingredients": []}


@app.route("/menu", methods=["GET"])
def api_get_menu():
    """{dia: {"comida": {...}, "cena": {...}}} solo con los días activos."""
    menu = db.get_menu()
    return jsonify({
        day: {meal: _slot_json(recipe) for meal, recipe in meals.items()}
        for day, meals in menu.items()
    })


@app.route("/menu/status", methods=["GET"])
def api_menu_status():
    """¿Hay recetas suficientes para montar la semana? (ver db.menu_status)"""
    return jsonify(db.menu_status())


def build_random_menu(recipes):
    """
    Genera la semana sin repetir ninguna receta (las 'extra' nunca entran).
    Para no gastar antes de tiempo las recetas comodín ('ambos'):
      1. se barajan y se asignan primero las exclusivas: 'comida' a los
         mediodías y 'cena' a las noches
      2. los mediodías que falten se completan con 'ambos'
      3. las noches que falten se completan con los 'ambos' que hayan sobrado
      4. se baraja el orden final de cada franja antes de repartirlo por los días
    Con el mínimo de recetas de db.menu_status() siempre hay para todos los huecos.
    """
    n = len(db.DAYS)

    only_lunch = [r for r in recipes if r["type"] == "comida"]
    only_dinner = [r for r in recipes if r["type"] == "cena"]
    wildcards = [r for r in recipes if r["type"] == "ambos"]
    for pool in (only_lunch, only_dinner, wildcards):
        random.shuffle(pool)

    lunches = only_lunch[:n]
    dinners = only_dinner[:n]

    missing = n - len(lunches)
    lunches += wildcards[:missing]
    wildcards = wildcards[missing:]

    missing = n - len(dinners)
    dinners += wildcards[:missing]

    random.shuffle(lunches)
    random.shuffle(dinners)

    assignments = {}
    for day, recipe in zip(db.DAYS, lunches):
        assignments[(day, "comida")] = recipe["id"]
    for day, recipe in zip(db.DAYS, dinners):
        assignments[(day, "cena")] = recipe["id"]
    return assignments


@app.route("/menu/generate", methods=["POST"])
def api_generate_menu():
    if not db.menu_status()["enough"]:
        return jsonify({"error": "No hay suficientes recetas"}), 400

    db.replace_menu(build_random_menu(db.get_all_recipes()))

    return jsonify({"ok": True})


@app.route("/menu/swap", methods=["POST"])
def api_swap_menu_slots():
    """Intercambia dos huecos del menú (arrastrar uno sobre otro)."""
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
    """
    Asigna una receta concreta a la comida o cena de un día (desde el modal).
    Aquí se puede repetir receta libremente; solo se exige que encaje en el hueco.
    """
    if day not in db.DAYS:
        return jsonify({"error": "Día no válido"}), 400
    if meal not in db.MEALS:
        return jsonify({"error": "Comida no válida"}), 400

    data = request.get_json(silent=True) or {}
    recipe = db.get_recipe(data.get("recipe_id"))
    if not recipe:
        return jsonify({"error": "Receta no encontrada"}), 404

    if not db.fits_meal(recipe["type"], meal):
        return jsonify({
            "error": f"'{recipe['name']}' es una receta de {recipe['type']}, "
                     f"no se puede poner en la {meal}."
        }), 400

    people = data.get("people")
    if people is not None and not positive_integer(people):
        return jsonify({"error": "Los comensales deben ser un entero positivo"}), 400
    db.set_menu_slot(day, meal, recipe["id"], people)

    return jsonify({"ok": True})


# ---------------------------------------------------------
# LISTA DE LA COMPRA (se calcula a partir del menú actual)
# ---------------------------------------------------------

@app.route("/shopping-list", methods=["GET"])
def api_shopping_list():
    return jsonify(db.get_shopping_list())


@app.route("/shopping-list/check", methods=["POST"])
def api_shopping_check():
    """Marca/desmarca un ingrediente como comprado: {name, unit, checked}."""
    data = request.get_json(silent=True) or {}

    name = collapse_spaces(data.get("name"))
    checked = data.get("checked")

    if not name:
        return jsonify({"error": "Falta el ingrediente"}), 400
    if not isinstance(checked, bool):
        return jsonify({"error": "'checked' debe ser true o false"}), 400

    db.set_shopping_checked(name, data.get("unit"), checked)

    return jsonify({"ok": True})


# ---------------------------------------------------------
# RECETAS (sin fotos: nombre, tipo e ingredientes)
# ---------------------------------------------------------

def clean_ingredients(raw):
    """Valida la lista de ingredientes que llega del frontend (la normalización
    de nombres y unidades se hace después, en database.create_recipe)."""
    if not isinstance(raw, list):
        return []

    cleaned = []
    for ing in raw:
        if not isinstance(ing, dict):
            continue

        name = collapse_spaces(ing.get("name"))
        if not name:
            continue

        qty = ing.get("qty")
        if qty in (None, ""):
            qty = None
        else:
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                # Texto libre: se conserva, pero nunca se escala en la compra.
                qty = str(ing.get("qty")).strip()
            else:
                if not math.isfinite(qty) or qty < 0:
                    qty = None

        cleaned.append({"name": name, "qty": qty, "unit": ing.get("unit")})

    return cleaned


@app.route("/recipes", methods=["GET"])
def api_list_recipes():
    return jsonify(db.get_all_recipes())


@app.route("/recipes/check-duplicate", methods=["POST"])
def api_check_duplicate():
    """
    ¿Existe ya una receta con los mismos ingredientes (sin importar orden ni cantidades)?
    Responde {"duplicate": {"id", "name"}} o {"duplicate": null}.
    """
    data = request.get_json(silent=True) or {}
    duplicate = db.find_duplicate_recipe(clean_ingredients(data.get("ingredients")))
    return jsonify({"duplicate": duplicate})


@app.route("/recipes", methods=["POST"])
def api_create_recipe():
    return save_recipe()


def positive_integer(value):
    return type(value) is int and 0 < value <= 2147483647


def save_recipe(recipe_id=None):
    data = request.get_json(silent=True) or {}

    name = collapse_spaces(data.get("name"))
    if not name:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    recipe_type = collapse_spaces(data.get("type") or "ambos").lower()
    if recipe_type not in db.RECIPE_TYPES:
        return jsonify({
            "error": "Tipo no válido (usa: " + ", ".join(db.RECIPE_TYPES) + ")"
        }), 400

    servings = data.get("servings", 2)
    if not positive_integer(servings):
        return jsonify({"error": "Las raciones deben ser un entero positivo"}), 400
    preparation = data.get("preparation", [])
    notes = data.get("notes", "")
    if not isinstance(preparation, list) or any(not isinstance(step, str) for step in preparation):
        return jsonify({"error": "La preparación debe ser una lista de pasos de texto"}), 400
    if not isinstance(notes, str):
        return jsonify({"error": "Las notas deben ser texto"}), 400
    ingredients = clean_ingredients(data.get("ingredients"))
    if not ingredients:
        return jsonify({"error": "Añade al menos un ingrediente"}), 400
    values = dict(name=name, ingredients=ingredients, recipe_type=recipe_type,
                  servings=servings, preparation=[step.strip() for step in preparation if step.strip()],
                  notes=notes.strip())
    recipe = (db.update_recipe(recipe_id, **values) if recipe_id is not None
              else db.create_recipe(**values))
    if recipe is None:
        return jsonify({"error": "Receta no encontrada"}), 404

    return jsonify(recipe), 200 if recipe_id is not None else 201


@app.route("/recipes/<int:recipe_id>", methods=["GET", "PUT"])
def api_recipe(recipe_id):
    if request.method == "PUT":
        return save_recipe(recipe_id)
    recipe = db.get_recipe(recipe_id)
    if recipe is None:
        return jsonify({"error": "Receta no encontrada"}), 404
    return jsonify(recipe)


@app.route("/recipes/<int:recipe_id>", methods=["DELETE"])
def api_delete_recipe(recipe_id):
    db.delete_recipe(recipe_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
