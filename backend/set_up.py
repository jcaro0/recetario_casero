"""
Creación de la base de datos SQL (SQLite) y lectura de todas sus tablas.

Uso:
    python set_up.py          # crea las tablas (si no existen) y muestra un resumen

También lo importa database.py / main.py, así que la base de datos
se crea sola la primera vez que arranca la aplicación.
"""

import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fichero de la base de datos. En Docker se monta en /app/data (volumen).
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "recetario.db"))

# Deben coincidir EXACTAMENTE (en minúscula) con los nombres de DAYS en menu.js
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


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
# CREACIÓN DE TABLAS
# ---------------------------------------------------------

def create_tables():
    """Crea todas las tablas. Es idempotente: se puede llamar cuantas veces se quiera."""
    days_sql = ", ".join(f"'{d}'" for d in DAYS)

    schema = f"""
    CREATE TABLE IF NOT EXISTS recipes (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        name  TEXT NOT NULL CHECK (length(trim(name)) > 0)
    );

    CREATE TABLE IF NOT EXISTS ingredients (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        position  INTEGER NOT NULL DEFAULT 0,   -- orden dentro de la receta
        name      TEXT NOT NULL CHECK (length(trim(name)) > 0),
        qty       REAL,                         -- NULL = sin cantidad
        unit      TEXT                          -- NULL = sin unidad
    );

    CREATE INDEX IF NOT EXISTS idx_ingredients_recipe
        ON ingredients(recipe_id, position);

    -- Una fila por día de la semana; recipe_id NULL = sin receta.
    -- Si se borra la receta, el día queda vacío automáticamente.
    CREATE TABLE IF NOT EXISTS menu (
        day       TEXT PRIMARY KEY CHECK (day IN ({days_sql})),
        recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL
    );
    """

    with connection() as conn:
        # WAL: más robusto ante cortes de luz y permite leer mientras se escribe.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(schema)
        conn.executemany(
            "INSERT OR IGNORE INTO menu (day, recipe_id) VALUES (?, NULL)",
            [(d,) for d in DAYS],
        )


# ---------------------------------------------------------
# LECTURA DE TODAS LAS TABLAS
# ---------------------------------------------------------

def read_recipes():
    """Todas las filas de la tabla recipes."""
    with connection() as conn:
        rows = conn.execute("SELECT id, name FROM recipes ORDER BY id").fetchall()
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
    """Todas las filas de la tabla menu (en el orden de la semana)."""
    with connection() as conn:
        rows = conn.execute("SELECT day, recipe_id FROM menu").fetchall()
    by_day = {r["day"]: r["recipe_id"] for r in rows}
    return [{"day": d, "recipe_id": by_day.get(d)} for d in DAYS]


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