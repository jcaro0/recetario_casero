"""
Creación de la base de datos SQL (SQLite) y lectura de todas sus tablas.

Uso:
    python set_up.py          # crea/actualiza las tablas y muestra un resumen

También lo importa main.py, así que la base de datos se crea (o se actualiza
desde la versión anterior) sola cada vez que arranca la aplicación.

Esquema (versión 2):
    recipes      (id, name, type)                 type: ambos | comida | cena | extra
    ingredients  (id, recipe_id, position, name, qty, unit)
    menu         (day, meal, recipe_id)           meal: comida | cena
"""

import os
import sqlite3
from contextlib import contextmanager

from normalize import collapse_spaces, normalize_ingredient_name, normalize_unit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fichero de la base de datos. En Docker se monta en /app/data (volumen).
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "recetario.db"))

SCHEMA_VERSION = 2

# Deben coincidir EXACTAMENTE (en minúscula) con los nombres de DAYS en menu.js
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MEALS = ["comida", "cena"]
RECIPE_TYPES = ["ambos", "comida", "cena", "extra"]


def _sql_list(values):
    return ", ".join(f"'{v}'" for v in values)


# ---------------------------------------------------------
# CONEXIÓN
# ---------------------------------------------------------

@contextmanager
def connection():
    """
    Abre una conexión, hace commit si todo va bien (rollback si hay error)
    y la cierra siempre. Una conexión por operación = seguro con hilos.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # hay que activarlo en cada conexión
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------
# ESQUEMA
# ---------------------------------------------------------

def _menu_sql():
    return f"""
    -- Dos filas por día (comida y cena); recipe_id NULL = sin receta.
    -- Si se borra la receta, el hueco queda vacío automáticamente.
    CREATE TABLE IF NOT EXISTS menu (
        day       TEXT NOT NULL CHECK (day IN ({_sql_list(DAYS)})),
        meal      TEXT NOT NULL CHECK (meal IN ({_sql_list(MEALS)})),
        recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
        PRIMARY KEY (day, meal)
    );
    """


def _schema_sql():
    return f"""
    CREATE TABLE IF NOT EXISTS recipes (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        name  TEXT NOT NULL CHECK (length(trim(name)) > 0),
        type  TEXT NOT NULL DEFAULT 'ambos'
              CHECK (type IN ({_sql_list(RECIPE_TYPES)}))
    );

    CREATE TABLE IF NOT EXISTS ingredients (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        position  INTEGER NOT NULL DEFAULT 0,   -- orden dentro de la receta
        name      TEXT NOT NULL CHECK (length(trim(name)) > 0),  -- ya normalizado
        qty       REAL,                         -- NULL = sin cantidad
        unit      TEXT                          -- NULL = sin unidad
    );

    CREATE INDEX IF NOT EXISTS idx_ingredients_recipe
        ON ingredients(recipe_id, position);

    {_menu_sql()}
    """


def _migrate_to_v2(conn):
    """
    Actualiza una base creada con la versión 1 (sin tipo de receta, menú de una
    sola comida al día e ingredientes sin normalizar). No pierde datos:
      - las recetas existentes pasan a tipo 'ambos'
      - lo que había en el menú pasa a la 'comida' de cada día
      - los nombres de ingredientes se normalizan
    """
    conn.execute("BEGIN")

    recipe_cols = {r["name"] for r in conn.execute("PRAGMA table_info(recipes)")}
    if "type" not in recipe_cols:
        conn.execute(
            "ALTER TABLE recipes ADD COLUMN type TEXT NOT NULL DEFAULT 'ambos' "
            f"CHECK (type IN ({_sql_list(RECIPE_TYPES)}))"
        )

    menu_cols = {r["name"] for r in conn.execute("PRAGMA table_info(menu)")}
    if menu_cols and "meal" not in menu_cols:
        conn.execute("ALTER TABLE menu RENAME TO menu_old")
        conn.execute(_menu_sql())
        conn.execute(
            "INSERT OR IGNORE INTO menu (day, meal, recipe_id) "
            "SELECT day, 'comida', recipe_id FROM menu_old WHERE recipe_id IS NOT NULL"
        )
        conn.execute("DROP TABLE menu_old")

    for row in conn.execute("SELECT id, name, unit FROM ingredients").fetchall():
        name = normalize_ingredient_name(row["name"]) or row["name"]
        unit = normalize_unit(row["unit"])
        if name != row["name"] or unit != row["unit"]:
            conn.execute(
                "UPDATE ingredients SET name = ?, unit = ? WHERE id = ?",
                (name, unit, row["id"]),
            )

    for row in conn.execute("SELECT id, name FROM recipes").fetchall():
        name = collapse_spaces(row["name"]) or row["name"]
        if name != row["name"]:
            conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (name, row["id"]))

    conn.commit()


def create_tables():
    """Crea todas las tablas (o actualiza las antiguas). Idempotente."""
    with connection() as conn:
        # WAL: más robusto ante cortes de luz y permite leer mientras se escribe.
        conn.execute("PRAGMA journal_mode = WAL")

        has_recipes = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recipes'"
        ).fetchone()
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        if has_recipes and version < SCHEMA_VERSION:
            _migrate_to_v2(conn)

        conn.executescript(_schema_sql())
        conn.executemany(
            "INSERT OR IGNORE INTO menu (day, meal, recipe_id) VALUES (?, ?, NULL)",
            [(d, m) for d in DAYS for m in MEALS],
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ---------------------------------------------------------
# LECTURA DE TODAS LAS TABLAS
# ---------------------------------------------------------

def read_recipes():
    """Todas las filas de la tabla recipes."""
    with connection() as conn:
        rows = conn.execute("SELECT id, name, type FROM recipes ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def read_ingredients():
    """Todas las filas de la tabla ingredients."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, recipe_id, position, name, qty, unit "
            "FROM ingredients ORDER BY recipe_id, position, id"
        ).fetchall()
    return [dict(r) for r in rows]


def read_menu():
    """Todas las filas de la tabla menu (en el orden de la semana: comida y cena)."""
    with connection() as conn:
        rows = conn.execute("SELECT day, meal, recipe_id FROM menu").fetchall()
    by_slot = {(r["day"], r["meal"]): r["recipe_id"] for r in rows}
    return [
        {"day": d, "meal": m, "recipe_id": by_slot.get((d, m))}
        for d in DAYS
        for m in MEALS
    ]


def read_all():
    """Contenido completo de la base de datos, tabla por tabla."""
    return {
        "recipes": read_recipes(),
        "ingredients": read_ingredients(),
        "menu": read_menu(),
    }


# ---------------------------------------------------------
# EJECUCIÓN DIRECTA
# ---------------------------------------------------------

if __name__ == "__main__":
    create_tables()
    data = read_all()
    print(f"✔ Base de datos lista en: {DB_PATH}")
    print(f"  recipes:     {len(data['recipes'])} filas")
    print(f"  ingredients: {len(data['ingredients'])} filas")
    print(f"  menu:        {len(data['menu'])} filas")