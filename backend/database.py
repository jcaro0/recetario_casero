"""
Acceso a datos (SQLite). Misma idea que la versión de Redis:
main.py solo habla con este módulo, nunca con SQL directamente.
"""

import set_up
from set_up import DAYS, connection


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
    recipes = {r["id"]: {"id": r["id"], "name": r["name"], "ingredients": []}
               for r in recipe_rows}
    for ing in ingredient_rows:
        recipe = recipes.get(ing["recipe_id"])
        if recipe is not None:
            recipe["ingredients"].append(_ingredient_dict(ing))
    return recipes


def create_recipe(name, ingredients):
    """Inserta receta + ingredientes en una sola transacción y la devuelve."""
    with connection() as conn:
        cur = conn.execute("INSERT INTO recipes (name) VALUES (?)", (name,))
        recipe_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO ingredients (recipe_id, position, name, qty, unit) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (recipe_id, pos, ing["name"], ing["qty"], ing["unit"])
                for pos, ing in enumerate(ingredients)
            ],
        )
    return get_recipe(recipe_id)


def get_recipe(recipe_id):
    try:
        recipe_id = int(recipe_id)
    except (TypeError, ValueError):
        return None

    with connection() as conn:
        recipe = conn.execute(
            "SELECT id, name FROM recipes WHERE id = ?", (recipe_id,)
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
            "SELECT id, name FROM recipes ORDER BY id"
        ).fetchall()
        ingredient_rows = conn.execute(
            "SELECT recipe_id, name, qty, unit FROM ingredients "
            "ORDER BY recipe_id, position, id"
        ).fetchall()
    return list(_group_recipes(recipe_rows, ingredient_rows).values())


def delete_recipe(recipe_id):
    # Los ingredientes se borran por ON DELETE CASCADE y el día del menú
    # que la usaba queda vacío por ON DELETE SET NULL.
    with connection() as conn:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


# ---------------------------------------------------------
# MENÚ SEMANAL
# ---------------------------------------------------------

def get_menu():
    """Devuelve un dict {dia: receta_completa_o_None}."""
    recipes = {r["id"]: r for r in get_all_recipes()}
    assigned = {row["day"]: row["recipe_id"] for row in set_up.read_menu()}
    return {day: recipes.get(assigned.get(day)) for day in DAYS}


def set_menu_day(day, recipe_id):
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = ? WHERE day = ?", (recipe_id, day))


def replace_menu(assignments):
    """Vacía el menú y asigna {dia: recipe_id} de golpe (una transacción)."""
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL")
        conn.executemany(
            "UPDATE menu SET recipe_id = ? WHERE day = ?",
            [(rid, day) for day, rid in assignments.items()],
        )


def swap_menu_days(day1, day2):
    """Intercambia la receta asignada a dos días (usado por el drag & drop)."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT day, recipe_id FROM menu WHERE day IN (?, ?)", (day1, day2)
        ).fetchall()
        current = {r["day"]: r["recipe_id"] for r in rows}
        conn.execute(
            "UPDATE menu SET recipe_id = ? WHERE day = ?", (current.get(day2), day1)
        )
        conn.execute(
            "UPDATE menu SET recipe_id = ? WHERE day = ?", (current.get(day1), day2)
        )


def clear_menu():
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL")


# ---------------------------------------------------------
# LISTA DE LA COMPRA (agregada en SQL a partir del menú actual)
# ---------------------------------------------------------

def get_shopping_list():
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT MIN(i.name)                      AS name,
                   COALESCE(i.unit, '')             AS unit,
                   COALESCE(SUM(i.qty), 0)          AS qty
            FROM menu m
            JOIN ingredients i ON i.recipe_id = m.recipe_id
            GROUP BY lower(trim(i.name)), lower(COALESCE(i.unit, ''))
            ORDER BY lower(MIN(i.name))
            """
        ).fetchall()

    return [
        {"name": r["name"], "unit": r["unit"], "qty": _clean_qty(r["qty"])}
        for r in rows
    ]