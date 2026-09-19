import os
import random

from flask import Flask, request, jsonify

import database as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Carpeta del frontend. En docker-compose se monta en /app/frontend.
FRONTEND_FOLDER = os.environ.get(
    "FRONTEND_FOLDER", os.path.join(BASE_DIR, "..", "frontend")
)

app = Flask(__name__, static_folder=FRONTEND_FOLDER, static_url_path="")


# ---------------------------------------------------------
# FRONTEND (mismo servidor -> sin CORS ni URLs absolutas)
# ---------------------------------------------------------

@app.route("/")
def serve_index():
    return app.send_static_file("index.html")


@app.route("/<path:filename>")
def serve_frontend_file(filename):
    # Sirve index.html, style.css, script.js, lista_compra.html, etc.
    return app.send_static_file(filename)


# ---------------------------------------------------------
# MENÚ SEMANAL
# ---------------------------------------------------------

@app.route("/menu", methods=["GET"])
def api_get_menu():
    menu = db.get_menu()

    result = {}
    for day, recipe in menu.items():
        if recipe:
            result[day] = {
                "id": recipe["id"],
                "name": recipe["name"],
                "ingredients": recipe["ingredients"],
            }
        else:
            result[day] = {"name": None, "ingredients": []}

    return jsonify(result)


@app.route("/menu/generate", methods=["POST"])
def api_generate_menu():
    recipes = db.get_all_recipes()

    db.clear_menu()

    if not recipes:
        return jsonify({"ok": True, "message": "No hay recetas guardadas."})

    if len(recipes) >= len(db.DAYS):
        chosen = random.sample(recipes, len(db.DAYS))
    else:
        # No hay recetas suficientes para no repetir: se rellena al azar
        chosen = [random.choice(recipes) for _ in db.DAYS]

    for day, recipe in zip(db.DAYS, chosen):
        db.set_menu_day(day, recipe["id"])

    return jsonify({"ok": True})


@app.route("/menu/swap", methods=["POST"])
def api_swap_menu_days():
    """Intercambia la receta de dos días (arrastrar una tarjeta sobre otra)."""
    data = request.get_json(silent=True) or {}

    day1 = data.get("day1")
    day2 = data.get("day2")

    if day1 not in db.DAYS or day2 not in db.DAYS:
        return jsonify({"error": "Día no válido"}), 400

    db.swap_menu_days(day1, day2)

    return jsonify({"ok": True})


@app.route("/menu/<day>", methods=["POST"])
def api_set_menu_day(day):
    """Asigna una receta concreta a un día (elegida desde el modal)."""
    if day not in db.DAYS:
        return jsonify({"error": "Día no válido"}), 400

    data = request.get_json(silent=True) or {}
    recipe_id = data.get("recipe_id")

    recipe = db.get_recipe(recipe_id)
    if not recipe:
        return jsonify({"error": "Receta no encontrada"}), 404

    db.set_menu_day(day, recipe_id)

    return jsonify({"ok": True})


# ---------------------------------------------------------
# LISTA DE LA COMPRA (se calcula a partir del menú actual)
# ---------------------------------------------------------

@app.route("/shopping-list", methods=["GET"])
def api_shopping_list():
    menu = db.get_menu()

    aggregated = {}

    for recipe in menu.values():
        if not recipe:
            continue

        for ing in recipe.get("ingredients", []):
            name = (ing.get("name") or "").strip()
            unit = (ing.get("unit") or "").strip()
            qty = ing.get("qty") or 0

            if not name:
                continue

            key = (name.lower(), unit.lower())

            if key not in aggregated:
                aggregated[key] = {"name": name, "unit": unit, "qty": 0}

            aggregated[key]["qty"] += qty

    return jsonify(list(aggregated.values()))


# ---------------------------------------------------------
# RECETAS (sin fotos: solo nombre e ingredientes)
# ---------------------------------------------------------

@app.route("/recipes", methods=["GET"])
def api_list_recipes():
    return jsonify(db.get_all_recipes())


@app.route("/recipes", methods=["POST"])
def api_create_recipe():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    ingredients = data.get("ingredients") or []

    if not name:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    recipe = {
        "id": db.next_recipe_id(),
        "name": name,
        "ingredients": ingredients,
    }

    db.save_recipe(recipe)

    return jsonify(recipe), 201


@app.route("/recipes/<int:recipe_id>", methods=["DELETE"])
def api_delete_recipe(recipe_id):
    db.delete_recipe(recipe_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)