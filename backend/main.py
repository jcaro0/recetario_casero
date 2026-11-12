import math
import os
import random

from flask import Flask, request, jsonify

import set_up
import database as db
from normalize import collapse_spaces

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Carpeta del frontend. En docker-compose se monta en /app/frontend.
FRONTEND_FOLDER = os.environ.get(
    "FRONTEND_FOLDER", os.path.join(BASE_DIR, "..", "frontend")
)

app = Flask(__name__, static_folder=FRONTEND_FOLDER, static_url_path="")

# Crea las tablas si no existen (o actualiza una base de la versión anterior).
set_up.create_tables()


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
# MENÚ SEMANAL (comida y cena de cada día)
# ---------------------------------------------------------

def _slot_json(recipe):
    if recipe:
        return {
            "id": recipe["id"],
            "name": recipe["name"],
            "type": recipe["type"],
            "ingredients": recipe["ingredients"],
        }
    return {"name": None, "ingredients": []}


@app.route("/menu", methods=["GET"])
def api_get_menu():
    """{dia: {"comida": {...}, "cena": {...}}}"""
    menu = db.get_menu()
    return jsonify({
        day: {meal: _slot_json(recipe) for meal, recipe in meals.items()}
        for day, meals in menu.items()
    })


def build_random_menu(recipes):
    """
    Elige receta para cada comida y cena:
      - comidas: recetas 'comida' o 'ambos'; cenas: 'cena' o 'ambos'
      - las 'extra' nunca entran en el menú automático
      - no se repite ninguna mientras queden recetas sin usar
    """
    pools = {
        meal: [r for r in recipes if r["type"] in ("ambos", meal)]
        for meal in db.MEALS
    }

    assignments = {}
    used = set()

    # Primero el tipo de comida con menos recetas posibles
    for meal in sorted(db.MEALS, key=lambda m: len(pools[m])):
        pool = pools[meal]
        if not pool:
            continue
        for day in db.DAYS:
            unused = [r for r in pool if r["id"] not in used]
            recipe = random.choice(unused or pool)
            used.add(recipe["id"])
            assignments[(day, meal)] = recipe["id"]

    return assignments


@app.route("/menu/generate", methods=["POST"])
def api_generate_menu():
    recipes = db.get_all_recipes()

    if not recipes:
        db.clear_menu()
        return jsonify({"ok": True, "message": "No hay recetas guardadas."})

    assignments = build_random_menu(recipes)
    db.replace_menu(assignments)

    if not assignments:
        return jsonify({"ok": True, "message": "No hay recetas de comida ni de cena."})

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
    """Asigna una receta concreta a la comida o cena de un día (desde el modal)."""
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

    db.set_menu_slot(day, meal, recipe["id"])

    return jsonify({"ok": True})


# ---------------------------------------------------------
# LISTA DE LA COMPRA (se calcula a partir del menú actual)
# ---------------------------------------------------------

@app.route("/shopping-list", methods=["GET"])
def api_shopping_list():
    return jsonify(db.get_shopping_list())


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
                qty = None
            else:
                if not math.isfinite(qty) or qty < 0:
                    qty = None

        cleaned.append({"name": name, "qty": qty, "unit": ing.get("unit")})

    return cleaned


@app.route("/recipes", methods=["GET"])
def api_list_recipes():
    return jsonify(db.get_all_recipes())


@app.route("/recipes", methods=["POST"])
def api_create_recipe():
    data = request.get_json(silent=True) or {}

    name = collapse_spaces(data.get("name"))
    if not name:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    recipe_type = collapse_spaces(data.get("type") or "ambos").lower()
    if recipe_type not in db.RECIPE_TYPES:
        return jsonify({
            "error": "Tipo no válido (usa: " + ", ".join(db.RECIPE_TYPES) + ")"
        }), 400

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