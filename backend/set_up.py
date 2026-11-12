""" 
Creación de la base de datos SQL (SQLite) y migraciones.
Importa desde database.py evitando ciclos.
"""
import database as db
from normalize import collapse_spaces, normalize_ingredient_name, normalize_unit

SCHEMA_VERSION = 2

def _sql_list(values):
    return ", ".join(f"'{v}'" for v in values)

def _menu_sql():
    return f"""
    CREATE TABLE IF NOT EXISTS menu (
        day       TEXT NOT NULL CHECK (day IN ({_sql_list(db.ALL_DAYS)})),
        meal      TEXT NOT NULL CHECK (meal IN ({_sql_list(db.MEALS)})),
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
              CHECK (type IN ({_sql_list(db.RECIPE_TYPES)}))
    );
    CREATE TABLE IF NOT EXISTS ingredients (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        position  INTEGER NOT NULL DEFAULT 0,
        name      TEXT NOT NULL CHECK (length(trim(name)) > 0),
        qty       REAL,
        unit      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ingredients_recipe
        ON ingredients(recipe_id, position);
        
    CREATE TABLE IF NOT EXISTS shopping_ticks (
        name TEXT NOT NULL,
        unit TEXT NOT NULL,
        checked INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (name, unit)
    );
    {_menu_sql()}
    """

def _migrate_to_v2(conn):
    conn.execute("BEGIN")
    recipe_cols = {r["name"] for r in conn.execute("PRAGMA table_info(recipes)")}
    if "type" not in recipe_cols:
        conn.execute(
            "ALTER TABLE recipes ADD COLUMN type TEXT NOT NULL DEFAULT 'ambos' "
            f"CHECK (type IN ({_sql_list(db.RECIPE_TYPES)}))"
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
            conn.execute("UPDATE ingredients SET name = ?, unit = ? WHERE id = ?", (name, unit, row["id"]))
            
    for row in conn.execute("SELECT id, name FROM recipes").fetchall():
        name = collapse_spaces(row["name"]) or row["name"]
        if name != row["name"]:
            conn.execute("UPDATE recipes SET name = ? WHERE id = ?", (name, row["id"]))
    conn.commit()

def create_tables():
    with db.connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        has_recipes = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recipes'").fetchone()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        
        if has_recipes and version < SCHEMA_VERSION:
            _migrate_to_v2(conn)
            
        conn.executescript(_schema_sql())
        
        conn.executemany(
            "INSERT OR IGNORE INTO menu (day, meal, recipe_id) VALUES (?, ?, NULL)",
            [(d, m) for d in db.ALL_DAYS for m in db.MEALS],
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")