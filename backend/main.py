import os
import sqlite3
import sys

from flask import Flask, jsonify, render_template, request, send_from_directory

import database as db
from normalize import clean_quantity, collapse_spaces

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_FOLDER = os.environ.get("FRONTEND_FOLDER", os.path.join(BASE_DIR, "..", "frontend"))
app = Flask(__name__, static_folder=None, template_folder=os.path.join(FRONTEND_FOLDER, "templates"))


@app.before_request
def validate_json_object():
    if request.is_json and not isinstance(request.get_json(silent=True), dict):
        raise ValueError("Se esperaba un objeto JSON válido")


@app.errorhandler(ValueError)
def invalid_data(error):
    return jsonify(error=str(error)), 400


def json_data():
    return request.get_json(silent=True) or {}


def positive_integer(value, label):
    if type(value) is not int or not 0 < value <= 2147483647:
        raise ValueError(f"{label} deben ser un entero positivo")
    return value


def menu_people(data, *, allow_original=False):
    people = data["people"] if "people" in data else db.get_week_people()
    if people is None and allow_original:
        return None
    return positive_integer(people, "Los comensales")


def validate_slots(*slots):
    if any(day not in db.DAYS for day, _ in slots):
        raise ValueError("Día no válido")
    if any(meal not in db.MEALS for _, meal in slots):
        raise ValueError("Comida no válida")


@app.get("/")
def serve_index():
    return serve_page("menu.html")


@app.get("/<any(menu.html,recetas.html,agregar_recetas.html,lista_compra.html):page>")
def serve_page(page):
    return render_template(page, page=page.removesuffix(".html"))


@app.get("/<any(style,scripts,img,fonts):directory>/<path:filename>")
def serve_asset(directory, filename):
    return send_from_directory(os.path.join(FRONTEND_FOLDER, directory), filename)


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(FRONTEND_FOLDER, "manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    response = send_from_directory(FRONTEND_FOLDER, "sw.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/days")
def api_days():
    return jsonify(db.DAYS)


def menu_response(menu):
    return {
        day: {meal: recipe or {"name": None, "ingredients": []} for meal, recipe in meals.items()}
        for day, meals in menu.items()
    }


@app.get("/menu")
def api_get_menu():
    return jsonify(menu_response(db.get_menu()))


@app.get("/connection")
def api_connection():
    return jsonify(ok=True), 200, {"Cache-Control": "no-store"}


@app.get("/snapshot")
def api_snapshot():
    data = db.read_snapshot()
    data["menu"] = menu_response(data["menu"])
    return jsonify(data), 200, {"Cache-Control": "no-store"}


@app.get("/menu/status")
def api_menu_status():
    return jsonify(db.menu_status())


@app.post("/menu/generate")
def api_generate_menu():
    db.generate_menu(menu_people(json_data()))
    return jsonify(ok=True)


@app.route("/menu/people", methods=["GET", "POST"])
def api_week_people():
    if request.method == "GET":
        return jsonify(people=db.get_week_people())
    people = menu_people(json_data())
    db.set_week_people(people)
    return jsonify(people=people)


@app.post("/menu/swap")
def api_swap_menu_slots():
    data = json_data()
    first = data.get("day1"), data.get("meal1")
    second = data.get("day2"), data.get("meal2")
    validate_slots(first, second)
    db.swap_menu_slots(*first, *second)
    return jsonify(ok=True)


@app.post("/menu/<day>/<meal>")
def api_set_menu_slot(day, meal):
    validate_slots((day, meal))
    data = json_data()
    recipe = db.get_recipe(data.get("recipe_id"))
    if not recipe:
        return jsonify(error="Receta no encontrada"), 404
    if not db.fits_meal(recipe["type"], meal):
        raise ValueError(f"'{recipe['name']}' es una receta de {recipe['type']}, no se puede poner en la {meal}.")
    db.set_menu_slot(day, meal, recipe["id"], menu_people(data, allow_original=True))
    return jsonify(ok=True)


@app.get("/shopping-list")
def api_shopping_list():
    return jsonify(db.get_shopping_list())


@app.post("/shopping-list/check")
def api_shopping_check():
    data = json_data()
    name = collapse_spaces(data.get("name"))
    checked = data.get("checked")
    if not name:
        raise ValueError("Falta el ingrediente")
    if not isinstance(checked, bool):
        raise ValueError("'checked' debe ser true o false")
    db.set_shopping_checked(name, data.get("unit"), checked)
    return jsonify(ok=True)


@app.post("/shopping-list/manual")
@app.put("/shopping-list/manual/<int:product_id>")
def api_save_manual_product(product_id=None):
    data = json_data()
    name = data.get("name")
    unit = data.get("unit")
    if not isinstance(name, str) or not (name := collapse_spaces(name)):
        raise ValueError("El nombre del producto es obligatorio")
    if unit is not None and not isinstance(unit, str):
        raise ValueError("La unidad debe ser texto")
    saved = db.save_manual_product(name, clean_quantity(data.get("qty")), collapse_spaces(unit) or None, product_id)
    if saved is None:
        return jsonify(error="Producto no encontrado"), 404
    return jsonify(manual_id=saved), 201 if product_id is None else 200


@app.patch("/shopping-list/manual/<int:product_id>")
def api_check_manual_product(product_id):
    checked = json_data().get("checked")
    if not isinstance(checked, bool):
        raise ValueError("'checked' debe ser true o false")
    if not db.check_manual_product(product_id, checked):
        return jsonify(error="Producto no encontrado"), 404
    return jsonify(ok=True)


@app.delete("/shopping-list/manual/<int:product_id>")
def api_delete_manual_product(product_id):
    if not db.delete_manual_product(product_id):
        return jsonify(error="Producto no encontrado"), 404
    return jsonify(ok=True)


def clean_ingredients(raw):
    if not isinstance(raw, list):
        raise ValueError("Los ingredientes deben ser una lista")
    cleaned = []
    for ingredient in raw:
        if not isinstance(ingredient, dict) or not isinstance(ingredient.get("name"), str):
            raise ValueError("Cada ingrediente debe tener un nombre de texto")
        name = collapse_spaces(ingredient["name"])
        if not name:
            continue
        unit = ingredient.get("unit")
        if unit is not None and not isinstance(unit, str):
            raise ValueError("La unidad debe ser texto")
        cleaned.append(dict(name=name, qty=clean_quantity(ingredient.get("qty")), unit=unit))
    return cleaned


@app.get("/recipes")
def api_list_recipes():
    recipes = db.get_all_recipes()
    meal = request.args.get("meal")
    if meal is None:
        return jsonify(recipes)
    if meal not in db.MEALS:
        raise ValueError("Comida no válida")
    return jsonify(has_recipes=bool(recipes), recipes=[r for r in recipes if db.fits_meal(r["type"], meal)])


@app.post("/recipes/check-duplicate")
def api_check_duplicate():
    return jsonify(duplicate=db.find_duplicate_recipe(clean_ingredients(json_data().get("ingredients"))))


@app.post("/recipes")
@app.put("/recipes/<int:recipe_id>")
def save_recipe(recipe_id=None):
    data = json_data()
    if not isinstance(data.get("name"), str):
        raise ValueError("El nombre debe ser texto")
    name = collapse_spaces(data["name"])
    if not name:
        raise ValueError("El nombre es obligatorio")

    recipe_type = collapse_spaces(data.get("type") or "ambos").lower()
    servings = positive_integer(data.get("servings", 2), "Las raciones")
    preparation = data.get("preparation", [])
    notes = data.get("notes", "")
    if not isinstance(preparation, list) or any(not isinstance(step, str) for step in preparation):
        raise ValueError("La preparación debe ser una lista de pasos de texto")
    if not isinstance(notes, str):
        raise ValueError("Las notas deben ser texto")
    ingredients = clean_ingredients(data.get("ingredients"))
    if not ingredients:
        raise ValueError("Añade al menos un ingrediente")

    recipe = db.save_recipe(name, ingredients, recipe_type, servings,
                            [step.strip() for step in preparation if step.strip()], notes.strip(),
                            recipe_id=recipe_id)
    if recipe is None:
        return jsonify(error="Receta no encontrada"), 404
    return jsonify(recipe), 201 if recipe_id is None else 200


@app.get("/recipes/<int:recipe_id>")
def api_recipe(recipe_id):
    recipe = db.get_recipe(recipe_id)
    if recipe is None:
        return jsonify(error="Receta no encontrada"), 404
    return jsonify(recipe)


@app.delete("/recipes/<int:recipe_id>")
def api_delete_recipe(recipe_id):
    db.delete_recipe(recipe_id)
    return jsonify(ok=True)


def main():
    from waitress import serve

    try:
        db._ensure_ready()
        port = int(os.environ.get("PORT", "8000"))
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        sys.exit(f"ERROR al arrancar: {error}")

    print(f"Recetario: DB_PATH={db.DB_PATH}; puerto={port}", flush=True)
    try:
        serve(app, host="0.0.0.0", port=port, threads=2,
              connection_limit=32, channel_timeout=30, max_request_body_size=1024 * 1024)
    except PermissionError:
        sys.exit("ERROR: sin permiso para escuchar. Para puerto 80 usa systemd con CAP_NET_BIND_SERVICE.")
    except Exception as error:
        sys.exit(f"ERROR al arrancar: {error}")


if __name__ == "__main__":
    main()
