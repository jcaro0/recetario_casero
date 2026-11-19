"""
Acceso centralizado a SQLite. Solo abre archivos existentes.
El esquema se comprueba en el primer acceso; la inicialización y las migraciones
se ejecutan explícitamente con manage.py, nunca desde una petición HTTP.
"""

import json
import os
import random
import sqlite3
import threading
from contextlib import closing, contextmanager

from backup import connect_existing
from normalize import (
    collapse_spaces, display_quantity, group_shopping, ingredient_key,
    normalize_unit, shopping_key, text_key,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fichero de la base de datos. En Docker se monta en /app/data (volumen).
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "recetario.db"))


# ---------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------

# Los 7 días posibles. La tabla menu los admite todos (así se puede ampliar
# el menú sin recrear la base de datos).
ALL_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DEFAULT_DAYS = ALL_DAYS[:5]  # laborables


def _parse_days(raw):
    """
    Lee MENU_DAYS, p. ej. "lunes,martes,miercoles,sabado" (con o sin tildes).
    Devuelve los días en orden de semana; si falta o no es válida, los 5 laborables.
    """
    if not raw:
        return list(DEFAULT_DAYS)
    wanted = {text_key(part) for part in raw.split(",")}
    days = [d for d in ALL_DAYS if text_key(d) in wanted]
    return days or list(DEFAULT_DAYS)


# Días activos del menú (los que se ven, se generan y entran en la lista de la compra).
DAYS = _parse_days(os.environ.get("MENU_DAYS"))
MEALS = ["comida", "cena"]
RECIPE_TYPES = ["ambos", "comida", "cena", "extra"]

# Versión del esquema (PRAGMA user_version). La define el esquema, no set_up.
SCHEMA_VERSION = 6
SCHEMA_COLUMNS = {
    "recipes": {"id", "name", "type", "servings", "preparation", "notes"},
    "ingredients": {"id", "recipe_id", "position", "name", "qty", "unit"},
    "menu": {"day", "meal", "recipe_id", "people"},
    "shopping_checked": {"name", "unit"},
    "settings": {"key", "value"},
    "manual_products": {"id", "name", "qty", "unit", "checked"},
}

_init_lock = threading.Lock()
_ready = False


def _open():
    """Abre una conexión existente, también para migrar un esquema antiguo."""
    conn = connect_existing(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def check_schema(conn):
    """Valida que el esquema sea conocido y devuelve su versión."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Esquema {version} demasiado nuevo; esta versión admite {SCHEMA_VERSION}.")
    if version == SCHEMA_VERSION:
        for table, required in SCHEMA_COLUMNS.items():
            if not required <= columns(conn, table):
                raise RuntimeError(f"Esquema incompleto en {table}; no se reparará creando una base vacía.")
    else:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"recipes", "ingredients", "menu"} <= tables:
            raise RuntimeError("Base vacía o esquema desconocido. Revisa DB_PATH.")
    return version


def _ensure_ready():
    """Comprueba el esquema una vez por proceso, sin crear ni migrar datos."""
    global _ready
    if _ready:
        return
    with _init_lock:
        if not _ready:
            with closing(_open()) as conn:
                if check_schema(conn) != SCHEMA_VERSION:
                    raise RuntimeError("La base requiere migración. Detén la app y ejecuta manage.py migrate con BACKUP_DIR configurado.")
            _ready = True


@contextmanager
def connection():
    """Una conexión por operación, con commit o rollback y cierre garantizado."""
    _ensure_ready()
    with closing(_open()) as conn, conn:
        yield conn


# Recetas

def fits_meal(recipe_type, meal):
    """Una receta 'ambos' o 'extra' vale para cualquier hueco; las demás, solo para el suyo."""
    return recipe_type in ("ambos", "extra", meal)


def _load_recipes(conn, recipe_id=None):
    query = """
        SELECT r.id, r.name, r.type, r.servings, r.preparation, r.notes,
               i.id AS ingredient_id, i.name AS ingredient, i.qty, i.unit
        FROM recipes r LEFT JOIN ingredients i ON r.id = i.recipe_id
    """
    if recipe_id is not None:
        query += " WHERE r.id = ?"
    params = () if recipe_id is None else (recipe_id,)
    recipes = {}
    for row in conn.execute(query + " ORDER BY r.id, i.position, i.id", params):
        rid = row["id"]
        if rid not in recipes:
            recipes[rid] = {"id": rid, "name": row["name"], "type": row["type"],
                            "servings": row["servings"], "preparation": json.loads(row["preparation"]),
                            "notes": row["notes"], "ingredients": []}
        if row["ingredient_id"] is not None:
            recipes[rid]["ingredients"].append(
                dict(name=row["ingredient"], qty=display_quantity(row["qty"]), unit=row["unit"])
            )
    return recipes


def save_recipe(name, ingredients, recipe_type="ambos", servings=2, preparation=None, notes="",
                *, recipe_id=None):
    if recipe_type not in RECIPE_TYPES:
        raise ValueError("Tipo no válido (usa: " + ", ".join(RECIPE_TYPES) + ")")
    values = (collapse_spaces(name), recipe_type, servings, json.dumps(preparation or []), notes)
    with connection() as conn:
        if recipe_id is None:
            recipe_id = conn.execute(
                "INSERT INTO recipes (name, type, servings, preparation, notes) VALUES (?, ?, ?, ?, ?)",
                values,
            ).lastrowid
        else:
            updated = conn.execute(
                "UPDATE recipes SET name=?, type=?, servings=?, preparation=?, notes=? WHERE id=?",
                (*values, recipe_id),
            )
            if not updated.rowcount:
                return None
            conn.execute("DELETE FROM ingredients WHERE recipe_id=?", (recipe_id,))
            if recipe_type in MEALS:
                conn.execute("UPDATE menu SET recipe_id=NULL, people=NULL WHERE recipe_id=? AND meal != ?",
                             (recipe_id, recipe_type))

        rows = []
        for ingredient in ingredients:
            name = collapse_spaces(ingredient["name"])
            if name:
                rows.append((recipe_id, len(rows), name, ingredient.get("qty"),
                             normalize_unit(ingredient.get("unit"))))
        conn.executemany(
            "INSERT INTO ingredients (recipe_id, position, name, qty, unit) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        return _load_recipes(conn, recipe_id)[recipe_id]


def get_recipe(recipe_id):
    try:
        recipe_id = int(recipe_id)
    except (TypeError, ValueError, OverflowError):
        return None
    if not -(2**63) <= recipe_id < 2**63:
        return None
    with connection() as conn:
        return _load_recipes(conn, recipe_id).get(recipe_id)


def get_all_recipes():
    with connection() as conn:
        return list(_load_recipes(conn).values())


def delete_recipe(recipe_id):
    # Los ingredientes se borran por ON DELETE CASCADE y los huecos del menú
    # que la usaban quedan vacíos por ON DELETE SET NULL.
    with connection() as conn:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


def find_duplicate_recipe(ingredients):
    """Primera receta con el mismo conjunto de nombres, sin orden ni cantidades."""
    wanted = {ingredient_key(i["name"]) for i in ingredients} - {""}
    if wanted:
        for recipe in get_all_recipes():
            if {ingredient_key(i["name"]) for i in recipe["ingredients"]} == wanted:
                return {key: recipe[key] for key in ("id", "name")}
    return None


# Menú semanal

SLOT_UPDATE = "UPDATE menu SET recipe_id=?, people=? WHERE day=? AND meal=?"


def _menu_pools(conn):
    pools = {kind: [] for kind in (*MEALS, "ambos")}
    for row in conn.execute("SELECT id, type FROM recipes WHERE type != 'extra'"):
        pools[row["type"]].append(row["id"])
    return pools


def _menu_shortages(pools):
    return {meal: max(0, len(DAYS) - len(pools[meal])) for meal in MEALS}


def menu_status():
    with connection() as conn:
        pools = _menu_pools(conn)
    return {
        "enough": sum(_menu_shortages(pools).values()) <= len(pools["ambos"]),
        "days": len(DAYS),
        "counts": {kind: len(ids) for kind, ids in pools.items()},
    }


def get_menu():
    menu = {day: dict.fromkeys(MEALS) for day in DAYS}
    with connection() as conn:
        conn.execute("BEGIN")  # Usa la misma vista de SQLite para el menú y sus recetas.
        recipes = _load_recipes(conn)
        for row in conn.execute("SELECT day, meal, recipe_id, people FROM menu"):
            recipe = recipes.get(row["recipe_id"])
            if row["day"] in menu and recipe:
                menu[row["day"]][row["meal"]] = dict(recipe, people=row["people"])
    return menu


def set_menu_slot(day, meal, recipe_id, people=None):
    with connection() as conn:
        conn.execute(SLOT_UPDATE, (recipe_id, people, day, meal))


def generate_menu(people):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        pools = _menu_pools(conn)
        shortages = _menu_shortages(pools)
        wildcards = pools["ambos"]
        if sum(shortages.values()) > len(wildcards):
            raise ValueError("No hay suficientes recetas")

        # Reparte primero las exclusivas y usa cada comodín a lo sumo una vez.
        random.shuffle(wildcards)
        assignments = []
        for meal in MEALS:
            exclusive = pools[meal]
            random.shuffle(exclusive)
            recipes = exclusive[:len(DAYS)] + [wildcards.pop() for _ in range(shortages[meal])]
            random.shuffle(recipes)
            assignments.extend((rid, people, day, meal) for day, rid in zip(DAYS, recipes))

        conn.execute("UPDATE menu SET recipe_id=NULL, people=NULL")
        conn.executemany(SLOT_UPDATE, assignments)
        conn.execute("DELETE FROM shopping_checked")
        _save_week_people(conn, people)


def get_week_people():
    with connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='week_people'").fetchone()
    return int(row[0]) if row else 2


def _save_week_people(conn, people):
    conn.execute("INSERT INTO settings(key,value) VALUES ('week_people',?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(people),))


def set_week_people(people):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _save_week_people(conn, people)
        conn.executemany("UPDATE menu SET people=? WHERE day=? AND meal=?",
                         [(people, d, m) for d in ALL_DAYS for m in MEALS])


def swap_menu_slots(day1, meal1, day2, meal2):
    """Intercambia receta y comensales en una misma transacción."""
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        slots = {(row["day"], row["meal"]): row for row in conn.execute(
            "SELECT m.day, m.meal, m.recipe_id, m.people, r.type "
            "FROM menu m LEFT JOIN recipes r ON r.id = m.recipe_id "
            "WHERE (m.day = ? AND m.meal = ?) OR (m.day = ? AND m.meal = ?)",
            (day1, meal1, day2, meal2),
        )}
        changes = []
        first, second = (day1, meal1), (day2, meal2)
        for source, target in ((first, second), (second, first)):
            row = slots.get(source)
            if row and row["recipe_id"] is not None and not fits_meal(row["type"], target[1]):
                raise ValueError("Esa receta no es válida para ese hueco del menú.")
            changes.append((row["recipe_id"] if row else None, row["people"] if row else None, *target))
        conn.executemany(SLOT_UPDATE, changes)


# Compra

def get_shopping_list():
    marks = ", ".join("?" for _ in DAYS)
    with connection() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT i.name, i.qty, i.unit, m.people, r.servings "
            "FROM menu m JOIN recipes r ON r.id = m.recipe_id "
            "JOIN ingredients i ON i.recipe_id = m.recipe_id "
            f"WHERE m.day IN ({marks})",
            DAYS,
        ).fetchall()
        checked = {shopping_key(row["name"], row["unit"]) for row in
                   conn.execute("SELECT name, unit FROM shopping_checked")}
        manual = [
            dict(manual_id=row["id"], name=row["name"], qty=display_quantity(row["qty"]),
                 unit=row["unit"], checked=bool(row["checked"]))
            for row in conn.execute("SELECT * FROM manual_products ORDER BY name COLLATE NOCASE, id")
        ]
    return group_shopping(rows, checked) + manual


def set_shopping_checked(name, unit, checked):
    key = shopping_key(name, unit)
    if not key[0]:
        raise ValueError("Ingrediente no válido")
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Borra también marcas antiguas equivalentes para que no reaparezcan.
        previous = conn.execute("SELECT name, unit FROM shopping_checked").fetchall()
        conn.executemany("DELETE FROM shopping_checked WHERE name=? AND unit=?",
                         (row for row in previous if shopping_key(*row) == key))
        if checked:
            conn.execute("INSERT OR IGNORE INTO shopping_checked (name, unit) VALUES (?, ?)", key)


def save_manual_product(name, qty, unit, product_id=None):
    with connection() as conn:
        if product_id is None:
            return conn.execute("INSERT INTO manual_products (name, qty, unit) VALUES (?, ?, ?)",
                                (name, qty, unit)).lastrowid
        updated = conn.execute("UPDATE manual_products SET name=?, qty=?, unit=? WHERE id=?",
                               (name, qty, unit, product_id))
        return product_id if updated.rowcount else None


def check_manual_product(product_id, checked):
    with connection() as conn:
        return bool(conn.execute("UPDATE manual_products SET checked=? WHERE id=?",
                                 (checked, product_id)).rowcount)


def delete_manual_product(product_id):
    with connection() as conn:
        return bool(conn.execute("DELETE FROM manual_products WHERE id=?", (product_id,)).rowcount)
