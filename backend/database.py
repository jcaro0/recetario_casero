"""
Acceso a datos (SQLite). main.py solo habla con este módulo,
nunca con SQL directamente.
"""

import set_up
from set_up import DAYS, MEALS, RECIPE_TYPES, connection
from normalize import collapse_spaces, normalize_ingredient_name, normalize_unit


class IncompatibleMeal(ValueError):
    """Se intenta poner una receta de 'comida' en una cena (o al revés)."""


def fits_meal(recipe_type, meal):
    """Una receta 'ambos' o 'extra' vale para cualquier hueco; las demás, solo para el suyo."""
    return recipe_type in ("ambos", "extra", meal)


# ---------------------------------------------------------
# RECETAS
# ---------------------------------------------------------

def _clean_qty(qty):
    """SQLite devuelve REAL (200.0); lo mostramos como 200 si es entero."""
    if qty is None:
        return None
    return int(qty) if float(qty).is_integer() else qty


def _ingredient_dict(row):
    return {"name": row["name"], "qty": _clean_qty(row["qty"]), "unit": row["unit"]}


def _group_recipes(recipe_rows, ingredient_rows):
    recipes = {
        r["id"]: {"id": r["id"], "name": r["name"], "type": r["type"], "ingredients": []}
        for r in recipe_rows
    }
    for ing in ingredient_rows:
        recipe = recipes.get(ing["recipe_id"])
        if recipe is not None:
            recipe["ingredients"].append(_ingredient_dict(ing))
    return recipes


def create_recipe(name, ingredients, recipe_type="ambos"):
    """
    Inserta receta + ingredientes en una sola transacción y la devuelve.
    Los nombres de ingredientes se normalizan aquí (Cebolla, Pina, ...).
    """
    if recipe_type not in RECIPE_TYPES:
        raise ValueError(f"Tipo de receta no válido: {recipe_type}")

    rows = []
    for ing in ingredients:
        ing_name = normalize_ingredient_name(ing["name"])
        if not ing_name:
            continue
        qty = ing.get("qty")
        unit = normalize_unit(ing.get("unit")) if qty is not None else None
        rows.append((ing_name, qty, unit))

    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO recipes (name, type) VALUES (?, ?)",
            (collapse_spaces(name), recipe_type),
        )
        recipe_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO ingredients (recipe_id, position, name, qty, unit) "
            "VALUES (?, ?, ?, ?, ?)",
            [(recipe_id, pos, n, q, u) for pos, (n, q, u) in enumerate(rows)],
        )
    return get_recipe(recipe_id)


def get_recipe(recipe_id):
    try:
        recipe_id = int(recipe_id)
    except (TypeError, ValueError):
        return None

    with connection() as conn:
        recipe = conn.execute(
            "SELECT id, name, type FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        if recipe is None:
            return None
        ingredients = conn.execute(
            "SELECT recipe_id, name, qty, unit FROM ingredients "
            "WHERE recipe_id = ? ORDER BY position, id",
            (recipe_id,),
        ).fetchall()

    return _group_recipes([recipe], ingredients)[recipe_id]


def get_all_recipes():
    with connection() as conn:
        recipe_rows = conn.execute(
            "SELECT id, name, type FROM recipes ORDER BY id"
        ).fetchall()
        ingredient_rows = conn.execute(
            "SELECT recipe_id, name, qty, unit FROM ingredients "
            "ORDER BY recipe_id, position, id"
        ).fetchall()
    return list(_group_recipes(recipe_rows, ingredient_rows).values())


def delete_recipe(recipe_id):
    # Los ingredientes se borran por ON DELETE CASCADE y los huecos del menú
    # que la usaban quedan vacíos por ON DELETE SET NULL.
    with connection() as conn:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


# ---------------------------------------------------------
# MENÚ SEMANAL (comida y cena de cada día)
# ---------------------------------------------------------

def get_menu():
    """Devuelve {dia: {"comida": receta_o_None, "cena": receta_o_None}}."""
    recipes = {r["id"]: r for r in get_all_recipes()}
    menu = {day: {meal: None for meal in MEALS} for day in DAYS}
    for row in set_up.read_menu():
        menu[row["day"]][row["meal"]] = recipes.get(row["recipe_id"])
    return menu


def set_menu_slot(day, meal, recipe_id):
    with connection() as conn:
        conn.execute(
            "UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?",
            (recipe_id, day, meal),
        )


def replace_menu(assignments):
    """Vacía el menú y asigna {(dia, comida): recipe_id} de golpe (una transacción)."""
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL")
        conn.executemany(
            "UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?",
            [(rid, day, meal) for (day, meal), rid in assignments.items()],
        )


def swap_menu_slots(day1, meal1, day2, meal2):
    """
    Intercambia las recetas de dos huecos (drag & drop). Si alguna receta no
    encaja en su nuevo hueco (p. ej. una 'comida' en una cena) lanza IncompatibleMeal.
    """
    with connection() as conn:
        rows = conn.execute(
            "SELECT m.day, m.meal, m.recipe_id, r.type "
            "FROM menu m LEFT JOIN recipes r ON r.id = m.recipe_id "
            "WHERE (m.day = ? AND m.meal = ?) OR (m.day = ? AND m.meal = ?)",
            (day1, meal1, day2, meal2),
        ).fetchall()
        slots = {(r["day"], r["meal"]): (r["recipe_id"], r["type"]) for r in rows}

        id1, type1 = slots.get((day1, meal1), (None, None))
        id2, type2 = slots.get((day2, meal2), (None, None))

        if id2 is not None and not fits_meal(type2, meal1):
            raise IncompatibleMeal("Esa receta no es válida para ese hueco del menú.")
        if id1 is not None and not fits_meal(type1, meal2):
            raise IncompatibleMeal("Esa receta no es válida para ese hueco del menú.")

        conn.execute(
            "UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?",
            (id2, day1, meal1),
        )
        conn.execute(
            "UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?",
            (id1, day2, meal2),
        )


def clear_menu():
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL")


# ---------------------------------------------------------
# LISTA DE LA COMPRA (suma de ingredientes del menú actual)
# ---------------------------------------------------------

def get_shopping_list():
    """
    Suma los ingredientes de todas las comidas y cenas del menú.

    - Se agrupa por nombre normalizado + unidad (1 Cebolla + 0.5 Cebolla = 1.5 Cebolla).
    - Sin unidad equivale a "uds" (así "1 cebolla" y "0.5 uds de cebolla" se suman).
    - Un ingrediente sin cantidad (p. ej. "Sal") sale una sola vez, y solo si no
      aparece ya con cantidad en otra receta.
    - Una receta repetida en varios huecos cuenta tantas veces como aparezca.
    """
    with connection() as conn:
        rows = conn.execute(
            "SELECT i.name, i.qty, i.unit "
            "FROM menu m JOIN ingredients i ON i.recipe_id = m.recipe_id"
        ).fetchall()

    totals = {}
    without_qty = set()

    for r in rows:
        name = normalize_ingredient_name(r["name"])
        if not name:
            continue

        if r["qty"] is None:
            without_qty.add(name)
            continue

        unit = normalize_unit(r["unit"]) or "uds"
        totals[(name, unit)] = totals.get((name, unit), 0) + r["qty"]

    items = [
        {"name": name, "unit": unit, "qty": _clean_qty(round(qty, 2))}
        for (name, unit), qty in totals.items()
    ]

    names_with_qty = {name for name, _ in totals}
    items += [
        {"name": name, "unit": None, "qty": None}
        for name in without_qty
        if name not in names_with_qty
    ]

    items.sort(key=lambda item: (item["name"], item["unit"] or ""))
    return items