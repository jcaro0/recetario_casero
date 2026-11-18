"""
Acceso a datos (SQLite).

Este módulo es el único que habla con la base de datos:
  - centraliza la ruta (DB_PATH) y las constantes (DAYS, MEALS, RECIPE_TYPES)
  - ofrece el gestor de contexto connection()
  - se encarga de que las tablas existan (inicialización perezosa)
  - contiene todas las consultas que usa main.py

set_up.py solo define el esquema y las migraciones; este módulo lo importa
únicamente cuando hace falta (ver _ensure_ready), nunca al arrancar.
"""

import os
import json
from decimal import Decimal, InvalidOperation
import sqlite3
import threading
from contextlib import contextmanager

from normalize import (
    collapse_spaces,
    normalize_ingredient_name,
    normalize_unit,
    strip_accents,
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
    wanted = {strip_accents(collapse_spaces(part)).lower() for part in raw.split(",")}
    days = [d for d in ALL_DAYS if strip_accents(d) in wanted]
    return days or list(DEFAULT_DAYS)


# Días activos del menú (los que se ven, se generan y entran en la lista de la compra).
DAYS = _parse_days(os.environ.get("MENU_DAYS"))
MEALS = ["comida", "cena"]
RECIPE_TYPES = ["ambos", "comida", "cena", "extra"]

# Versión del esquema (PRAGMA user_version). La define el esquema, no set_up.
SCHEMA_VERSION = 4
REQUIRED_TABLES = ("recipes", "ingredients", "menu", "shopping_checked")


# ---------------------------------------------------------
# CONEXIÓN + INICIALIZACIÓN PEREZOSA
# ---------------------------------------------------------

# RLock: set_up.create_tables() llama a connection() mientras se está
# inicializando, y esa llamada (mismo hilo) debe poder entrar sin bloquearse.
_init_lock = threading.RLock()
_ready = False
_initializing = False


def _open():
    """Abre una conexión nueva (sin comprobar nada)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # hay que activarlo en cada conexión
    return conn


def _needs_setup():
    """True si falta alguna tabla o el esquema es de una versión anterior."""
    conn = _open()
    try:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    return not set(REQUIRED_TABLES) <= tables or version < SCHEMA_VERSION


def _ensure_ready():
    """
    Se ejecuta en la primera conexión. Si las tablas ya existen y están al día,
    no hace nada más (set_up ni se importa). Si falta algo, importa set_up y
    crea/migra el esquema.

    El lock evita que varias peticiones en paralelo (/menu, /recipes, /days...)
    lancen la creación a la vez: las demás esperan y, al entrar, ya está listo.
    """
    global _ready, _initializing
    if _ready:
        return
    with _init_lock:
        if _ready or _initializing:  # _initializing: re-entrada desde set_up
            return
        _initializing = True
        try:
            if _needs_setup():
                import set_up  # import tardío: evita importaciones circulares

                set_up.create_tables()
            _ready = True
        finally:
            _initializing = False


@contextmanager
def connection():
    """
    Abre una conexión, hace commit si todo va bien (rollback si hay error)
    y la cierra siempre. Una conexión por operación = seguro con hilos.
    """
    _ensure_ready()
    conn = _open()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------
# LECTURA DE TODAS LAS TABLAS (tal cual están guardadas)
# ---------------------------------------------------------

def read_recipes():
    with connection() as conn:
        rows = conn.execute("SELECT id, name, type, servings, preparation, notes FROM recipes ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def read_ingredients():
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, recipe_id, position, name, qty, unit "
            "FROM ingredients ORDER BY recipe_id, position, id"
        ).fetchall()
    return [dict(r) for r in rows]


def read_menu():
    """Todas las filas de la tabla menu (los 7 días, comida y cena)."""
    with connection() as conn:
        rows = conn.execute("SELECT day, meal, recipe_id, people FROM menu").fetchall()
    by_slot = {(r["day"], r["meal"]): dict(r) for r in rows}
    return [
        {"day": d, "meal": m, "recipe_id": by_slot.get((d, m), {}).get("recipe_id"),
         "people": by_slot.get((d, m), {}).get("people")}
        for d in ALL_DAYS
        for m in MEALS
    ]


def read_shopping_checked():
    with connection() as conn:
        rows = conn.execute("SELECT name, unit FROM shopping_checked ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def read_all():
    """Contenido completo de la base de datos, tabla por tabla."""
    return {
        "recipes": read_recipes(),
        "ingredients": read_ingredients(),
        "menu": read_menu(),
        "shopping_checked": read_shopping_checked(),
    }


# ---------------------------------------------------------
# RECETAS
# ---------------------------------------------------------

class IncompatibleMeal(ValueError):
    """Se intenta poner una receta de 'comida' en una cena (o al revés)."""


def fits_meal(recipe_type, meal):
    """Una receta 'ambos' o 'extra' vale para cualquier hueco; las demás, solo para el suyo."""
    return recipe_type in ("ambos", "extra", meal)


def _clean_qty(qty):
    """SQLite devuelve REAL (200.0); lo mostramos como 200 si es entero."""
    if qty is None or isinstance(qty, str):
        return qty
    return int(qty) if float(qty).is_integer() else qty


def _ingredient_dict(row):
    return {"name": row["name"], "qty": _clean_qty(row["qty"]), "unit": row["unit"]}


def _group_recipes(recipe_rows, ingredient_rows):
    recipes = {
        r["id"]: {"id": r["id"], "name": r["name"], "type": r["type"],
                  "servings": r["servings"], "preparation": json.loads(r["preparation"]),
                  "notes": r["notes"], "ingredients": []}
        for r in recipe_rows
    }
    for ing in ingredient_rows:
        recipe = recipes.get(ing["recipe_id"])
        if recipe is not None:
            recipe["ingredients"].append(_ingredient_dict(ing))
    return recipes


def _write_ingredients(conn, recipe_id, ingredients):
    rows = []
    for ing in ingredients:
        name = normalize_ingredient_name(ing["name"])
        if name:
            qty = ing.get("qty")
            unit = normalize_unit(ing.get("unit"))
            rows.append((recipe_id, len(rows), name, qty, unit))
    conn.executemany(
        "INSERT INTO ingredients (recipe_id, position, name, qty, unit) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


def create_recipe(name, ingredients, recipe_type="ambos", servings=2, preparation=None, notes=""):
    if recipe_type not in RECIPE_TYPES:
        raise ValueError(f"Tipo de receta no válido: {recipe_type}")
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO recipes (name, type, servings, preparation, notes) VALUES (?, ?, ?, ?, ?)",
            (collapse_spaces(name), recipe_type, servings, json.dumps(preparation or []), notes),
        )
        recipe_id = cur.lastrowid
        _write_ingredients(conn, recipe_id, ingredients)
    return get_recipe(recipe_id)


def update_recipe(recipe_id, name, ingredients, recipe_type="ambos", servings=2, preparation=None, notes=""):
    """Mantiene el ID y las referencias del menú; reemplaza ingredientes de forma atómica."""
    with connection() as conn:
        cur = conn.execute(
            "UPDATE recipes SET name=?, type=?, servings=?, preparation=?, notes=? WHERE id=?",
            (collapse_spaces(name), recipe_type, servings, json.dumps(preparation or []), notes, recipe_id),
        )
        if not cur.rowcount:
            return None
        conn.execute("DELETE FROM ingredients WHERE recipe_id=?", (recipe_id,))
        _write_ingredients(conn, recipe_id, ingredients)
        # Un cambio de tipo solo vacía los huecos que ya no admiten la receta.
        if recipe_type in MEALS:
            conn.execute("UPDATE menu SET recipe_id=NULL, people=NULL WHERE recipe_id=? AND meal != ?",
                         (recipe_id, recipe_type))
    return get_recipe(recipe_id)


def get_recipe(recipe_id):
    try:
        recipe_id = int(recipe_id)
    except (TypeError, ValueError):
        return None

    with connection() as conn:
        recipe = conn.execute(
            "SELECT id, name, type, servings, preparation, notes FROM recipes WHERE id = ?", (recipe_id,)
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
            "SELECT id, name, type, servings, preparation, notes FROM recipes ORDER BY id"
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


def find_duplicate_recipe(ingredients):
    """
    Busca una receta guardada con EXACTAMENTE el mismo conjunto de ingredientes.
    Se comparan nombres normalizados, sin importar el orden ni las cantidades.
    Devuelve {"id", "name"} de la primera coincidencia, o None.
    """
    wanted = {normalize_ingredient_name(i.get("name")) for i in ingredients}
    wanted.discard("")
    if not wanted:  # sin ingredientes no hay nada con lo que comparar
        return None

    with connection() as conn:
        rows = conn.execute(
            "SELECT r.id, r.name, i.name AS ingredient "
            "FROM recipes r JOIN ingredients i ON i.recipe_id = r.id "
            "ORDER BY r.id"
        ).fetchall()

    stored = {}
    for row in rows:
        entry = stored.setdefault(row["id"], {"id": row["id"], "name": row["name"], "set": set()})
        entry["set"].add(normalize_ingredient_name(row["ingredient"]))

    for entry in stored.values():
        if entry["set"] == wanted:
            return {"id": entry["id"], "name": entry["name"]}
    return None


# ---------------------------------------------------------
# MENÚ SEMANAL (comida y cena de cada día activo)
# ---------------------------------------------------------

def menu_status():
    """
    ¿Hay recetas suficientes para una semana sin repetir ningún plato?
    Con N días activos (2N huecos), sin contar las 'extra', se necesita a la vez:
        comidas + ambos >= N      cenas + ambos >= N      comidas + cenas + ambos >= 2N
    """
    counts = {"comida": 0, "cena": 0, "ambos": 0}
    with connection() as conn:
        rows = conn.execute(
            "SELECT type, COUNT(*) AS n FROM recipes WHERE type != 'extra' GROUP BY type"
        ).fetchall()
    for row in rows:
        counts[row["type"]] = row["n"]

    n = len(DAYS)
    c, d, a = counts["comida"], counts["cena"], counts["ambos"]
    enough = c + a >= n and d + a >= n and c + d + a >= 2 * n
    return {"enough": enough, "days": n, "counts": counts}


def get_menu():
    """Devuelve {dia: {"comida": receta_o_None, "cena": receta_o_None}} solo de los días activos."""
    recipes = {r["id"]: r for r in get_all_recipes()}
    menu = {day: {meal: None for meal in MEALS} for day in DAYS}
    for row in read_menu():
        if row["day"] in menu:  # ignora filas de días inactivos (p. ej. sábado)
            recipe = recipes.get(row["recipe_id"])
            menu[row["day"]][row["meal"]] = (
                dict(recipe, people=row["people"]) if recipe else None
            )
    return menu


def set_menu_slot(day, meal, recipe_id, people=None):
    with connection() as conn:
        conn.execute(
            "UPDATE menu SET recipe_id = ?, people = ? WHERE day = ? AND meal = ?",
            (recipe_id, people, day, meal),
        )


def replace_menu(assignments):
    """
    Vacía el menú y asigna {(dia, comida): recipe_id} de golpe (una transacción).
    Al ser un menú nuevo, también se desmarca la lista de la compra.
    """
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL, people = NULL")
        conn.executemany(
            "UPDATE menu SET recipe_id = ? WHERE day = ? AND meal = ?",
            [(rid, day, meal) for (day, meal), rid in assignments.items()],
        )
        conn.execute("DELETE FROM shopping_checked")


def swap_menu_slots(day1, meal1, day2, meal2):
    """
    Intercambia las recetas de dos huecos (drag & drop). Solo se valida que cada
    receta encaje en su nuevo hueco (una 'comida' no va en una cena); repetir
    recetas está permitido.
    """
    with connection() as conn:
        rows = conn.execute(
            "SELECT m.day, m.meal, m.recipe_id, m.people, r.type "
            "FROM menu m LEFT JOIN recipes r ON r.id = m.recipe_id "
            "WHERE (m.day = ? AND m.meal = ?) OR (m.day = ? AND m.meal = ?)",
            (day1, meal1, day2, meal2),
        ).fetchall()
        slots = {(r["day"], r["meal"]): (r["recipe_id"], r["type"], r["people"]) for r in rows}

        id1, type1, people1 = slots.get((day1, meal1), (None, None, None))
        id2, type2, people2 = slots.get((day2, meal2), (None, None, None))

        if id2 is not None and not fits_meal(type2, meal1):
            raise IncompatibleMeal("Esa receta no es válida para ese hueco del menú.")
        if id1 is not None and not fits_meal(type1, meal2):
            raise IncompatibleMeal("Esa receta no es válida para ese hueco del menú.")

        conn.execute(
            "UPDATE menu SET recipe_id = ?, people = ? WHERE day = ? AND meal = ?",
            (id2, people2, day1, meal1),
        )
        conn.execute(
            "UPDATE menu SET recipe_id = ?, people = ? WHERE day = ? AND meal = ?",
            (id1, people1, day2, meal2),
        )


def clear_menu():
    with connection() as conn:
        conn.execute("UPDATE menu SET recipe_id = NULL, people = NULL")
        conn.execute("DELETE FROM shopping_checked")


# ---------------------------------------------------------
# LISTA DE LA COMPRA (suma de ingredientes del menú actual)
# ---------------------------------------------------------

def shopping_unit(unit):
    aliases = {
        "kg": ("g", 1000), "kilogramo": ("g", 1000), "kilogramos": ("g", 1000),
        "gramos": ("g", 1), "gr": ("g", 1), "gramo": ("g", 1),
        "l": ("ml", 1000), "litro": ("ml", 1000), "litros": ("ml", 1000),
        "mililitro": ("ml", 1), "mililitros": ("ml", 1),
        "ud": ("uds", 1), "unidad": ("uds", 1), "unidades": ("uds", 1),
    }
    canonical, factor = aliases.get(unit, (unit, 1))
    return canonical, Decimal(factor)


def get_shopping_list():
    """
    Suma los ingredientes de todas las comidas y cenas de los días activos.

    - Se agrupa por nombre normalizado + unidad (1 Cebolla + 0.5 Cebolla = 1.5 Cebolla).
    - Sin unidad equivale a "uds" (así "1 cebolla" y "0.5 uds de cebolla" se suman).
    - Un ingrediente sin cantidad (p. ej. "Sal") sale una sola vez, y solo si no
      aparece ya con cantidad en otra receta.
    - Una receta repetida en varios huecos cuenta tantas veces como aparezca.
    - Cada elemento lleva "checked": si ya está comprado / en casa (se guarda en la BD).
    """
    marks = ", ".join("?" for _ in DAYS)
    with connection() as conn:
        rows = conn.execute(
            "SELECT i.name, i.qty, i.unit, m.people, r.servings "
            "FROM menu m JOIN recipes r ON r.id = m.recipe_id "
            "JOIN ingredients i ON i.recipe_id = m.recipe_id "
            f"WHERE m.day IN ({marks})",
            DAYS,
        ).fetchall()
        checked = {
            (r["name"], r["unit"])
            for r in conn.execute("SELECT name, unit FROM shopping_checked")
        }

    totals = {}
    without_qty = set()
    text_quantities = set()

    for r in rows:
        name = normalize_ingredient_name(r["name"])
        if not name:
            continue

        if r["qty"] is None:
            without_qty.add(name)
            continue

        unit = normalize_unit(r["unit"]) or "uds"
        try:
            qty = Decimal(str(r["qty"]))
            if not qty.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            text_quantities.add((name, str(r["qty"]), r["unit"]))
            continue
        unit, multiplier = shopping_unit(unit)
        qty *= multiplier * Decimal(r["people"] or r["servings"]) / Decimal(r["servings"])
        totals[(name, unit)] = totals.get((name, unit), Decimal(0)) + qty

    items = [
        {"name": name, "unit": unit, "qty": _clean_qty(float(round(qty, 3)))}
        for (name, unit), qty in totals.items()
    ]

    items += [{"name": name, "qty": qty, "unit": unit}
              for name, qty, unit in sorted(text_quantities, key=lambda x: (x[0], x[1], x[2] or ""))]
    names_with_qty = {name for name, _ in totals} | {name for name, _, _ in text_quantities}
    items += [
        {"name": name, "unit": None, "qty": None}
        for name in without_qty
        if name not in names_with_qty
    ]

    items.sort(key=lambda item: (item["name"], item["unit"] or ""))
    for item in items:
        # En la tabla la "sin unidad" se guarda como '' (así sirve de clave primaria)
        item["checked"] = (item["name"], item["unit"] or "") in checked
    return items


def set_shopping_checked(name, unit, checked):
    """Marca o desmarca un ingrediente de la lista de la compra."""
    key_name = normalize_ingredient_name(name)
    key_unit = normalize_unit(unit) or ""
    if not key_name:
        raise ValueError("Ingrediente no válido")

    with connection() as conn:
        if checked:
            conn.execute(
                "INSERT OR IGNORE INTO shopping_checked (name, unit) VALUES (?, ?)",
                (key_name, key_unit),
            )
        else:
            conn.execute(
                "DELETE FROM shopping_checked WHERE name = ? AND unit = ?",
                (key_name, key_unit),
            )