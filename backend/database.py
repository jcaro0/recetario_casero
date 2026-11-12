""" Acceso a datos (SQLite). main.py solo habla con este módulo, nunca con SQL directamente. """
import os
import sqlite3
import threading
from contextlib import contextmanager
from normalize import collapse_spaces, normalize_ingredient_name, normalize_unit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "recetario.db"))

ALL_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

env_days = os.environ.get("MENU_DAYS")
if env_days:
    DAYS = [d.strip().lower() for d in env_days.split(",") if d.strip().lower() in ALL_DAYS]
else:
    DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes"]

MEALS = ["comida", "cena"]
RECIPE_TYPES = ["ambos", "comida", "cena", "extra"]

# Usamos RLock (Reentrant Lock) para que el mismo hilo no se bloquee a sí mismo
_db_lock = threading.RLock()
_db_initialized = False
_is_initializing = False

def _init_db():
    global _db_initialized, _is_initializing
    # Si ya está lista o estamos en medio de inicializarla (bucle), salimos
    if _db_initialized or _is_initializing:
        return
        
    with _db_lock:
        if _db_initialized or _is_initializing:
            return
            
        _is_initializing = True
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            conn = sqlite3.connect(DB_PATH, timeout=10)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('recipes', 'ingredients', 'menu', 'shopping_ticks')")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            
            if not {"recipes", "ingredients", "menu", "shopping_ticks"}.issubset(tables):
                import set_up
                set_up.create_tables()
            
            _db_initialized = True
        finally:
            _is_initializing = False

@contextmanager
def connection():
    _init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

class IncompatibleMeal(ValueError):
    pass

def fits_meal(recipe_type, meal):
    return recipe_type in ("ambos", "extra", meal)

def _clean_qty(qty):
    if qty is None: return None
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
    if recipe_type not in RECIPE_TYPES:
        raise ValueError(f"Tipo de receta no válido: {recipe_type}")
    rows = []
    for ing in ingredients:
        ing_name = normalize_ingredient_name(ing["name"])
        if not ing_name: continue
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
            "INSERT INTO ingredients (recipe_id, position, name, qty, unit) VALUES (?, ?, ?, ?, ?)",
            [(recipe_id, pos, n, q, u) for pos, (n, q, u) in enumerate(rows)],
        )
    return get_recipe(recipe_id)

def get_recipe(recipe_id):
    try: recipe_id = int(recipe_id)
    except (TypeError, ValueError): return None
    with connection() as conn:
        recipe = conn.execute("SELECT id, name, type FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if recipe is None: return None
        ingredients = conn.execute(
            "SELECT recipe_id, name, qty, unit FROM ingredients WHERE recipe_id = ? ORDER BY position, id",
            (recipe_id,)
        ).fetchall()
    return _group_recipes([recipe], ingredients)[recipe_id]

def get_all_recipes():
    with connection() as conn:
        recipe_rows = conn.execute("SELECT id, name, type FROM recipes ORDER BY id").fetchall()
        ingredient_rows = conn.execute("SELECT recipe_id, name, qty, unit FROM ingredients ORDER BY recipe_id, position, id").fetchall()
    return list(_group_recipes(recipe_rows, ingredient_rows).values())

def delete_recipe(recipe_id):
    with connection() as conn:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))

def get_menu():
    recipes = {r["id"]: r for r in get_all_recipes()}
    menu = {day: {meal: None for meal in MEALS} for day in DAYS}
    with connection() as conn:
        rows = conn.execute("SELECT day, meal, recipe_id FROM menu").fetchall()
    
    for row in rows:
        if row["day"] in DAYS:
            menu[row["day"]][row["meal"]] = recipes.get(row["recipe_id"])
    return menu

def set_menu_slot(day, meal, recipe_id):
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?", (recipe_id, day, meal))

def replace_menu(assignments):
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL")
        conn.executemany(
            "UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?",
            [(rid, day, meal) for (day, meal), rid in assignments.items()],
        )
        # Limpia los ticks de la lista al generar una nueva semana entera
        conn.execute("DELETE FROM shopping_ticks")

def swap_menu_slots(day1, meal1, day2, meal2):
    with connection() as conn:
        rows = conn.execute(
            "SELECT m.day, m.meal, m.recipe_id, r.type FROM menu m LEFT JOIN recipes r ON r.id = m.recipe_id "
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
        
        conn.execute("UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?", (id2, day1, meal1))
        conn.execute("UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?", (id1, day2, meal2))

def clear_menu():
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL")
        conn.execute("DELETE FROM shopping_ticks")

def get_shopping_list():
    with connection() as conn:
        placeholders = ",".join("?" for _ in DAYS)
        rows = conn.execute(
            f"SELECT i.name, i.qty, i.unit FROM menu m JOIN ingredients i ON i.recipe_id = m.recipe_id "
            f"WHERE m.day IN ({placeholders})", DAYS
        ).fetchall()
        ticks_rows = conn.execute("SELECT name, unit, checked FROM shopping_ticks").fetchall()
        
    totals = {}
    without_qty = set()
    for r in rows:
        name = normalize_ingredient_name(r["name"])
        if not name: continue
        if r["qty"] is None:
            without_qty.add(name)
            continue
        unit = normalize_unit(r["unit"]) or "uds"
        totals[(name, unit)] = totals.get((name, unit), 0) + r["qty"]
        
    items = [{"name": name, "unit": unit, "qty": _clean_qty(round(qty, 2))} for (name, unit), qty in totals.items()]
    names_with_qty = {name for name, _ in totals}
    items += [{"name": name, "unit": None, "qty": None} for name in without_qty if name not in names_with_qty]
    items.sort(key=lambda item: (item["name"], item["unit"] or ""))
    
    # Aplicar estado "ticked" guardado
    ticks = {(r["name"], r["unit"]): bool(r["checked"]) for r in ticks_rows}
    for item in items:
        u_key = item["unit"] or ""
        item["checked"] = ticks.get((item["name"], u_key), False)

    return items

def set_shopping_tick(name, unit, checked):
    u_key = unit if unit is not None else ""
    with connection() as conn:
        conn.execute(
            """INSERT INTO shopping_ticks (name, unit, checked) 
               VALUES (?, ?, ?) 
               ON CONFLICT(name, unit) DO UPDATE SET checked = excluded.checked""",
            (name, u_key, 1 if checked else 0)
        )

def check_duplicate_by_ingredients(ingredients):
    incoming = set()
    for ing in ingredients:
        n = normalize_ingredient_name(ing.get("name", ""))
        if n: incoming.add(n)
            
    if not incoming: return None
        
    for r in get_all_recipes():
        existing = {normalize_ingredient_name(i["name"]) for i in r["ingredients"] if normalize_ingredient_name(i["name"])}
        if incoming == existing:
            return r["name"]
    return None