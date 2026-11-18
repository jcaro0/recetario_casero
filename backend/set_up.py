"""
Esquema de la base de datos y migraciones entre versiones.

Este módulo SOLO crea tablas y migra datos antiguos. La conexión, las rutas y
las constantes viven en database.py, que importa este módulo únicamente cuando
detecta que falta una tabla o que el esquema es de una versión anterior.

Uso manual (opcional, la app también lo hace sola):
    python set_up.py

Esquema (versión 4):
    recipes           (id, name, type, servings, preparation, notes)
    ingredients       (id, recipe_id, position, name, qty, unit)
    menu              (day, meal, recipe_id, people) meal: comida | cena
    shopping_checked  (name, unit)                 ingredientes ya comprados / en casa
"""

from database import (
    ALL_DAYS,
    DB_PATH,
    MEALS,
    RECIPE_TYPES,
    SCHEMA_VERSION,
    connection,
    read_all,
)
from normalize import collapse_spaces, normalize_ingredient_name, normalize_unit


def _sql_list(values):
    """['a', 'b'] -> "'a', 'b'" para usar dentro de un CHECK (... IN (...))."""
    return ", ".join(f"'{v}'" for v in values)


# ---------------------------------------------------------
# ESQUEMA
# ---------------------------------------------------------

def _menu_sql():
    return f"""
    -- Dos filas por día (comida y cena); recipe_id NULL = sin receta.
    --  * CHECK (day IN ...): valida contra los 7 días (ALL_DAYS), no solo contra
    --    los activos, así se puede pasar de 5 a 7 días (MENU_DAYS) sin recrear la BD.
    --  * CHECK (meal IN ...): solo 'comida' o 'cena'.
    --  * ON DELETE SET NULL: si se borra la receta, el hueco queda vacío solo.
    CREATE TABLE IF NOT EXISTS menu (
        day       TEXT NOT NULL CHECK (day IN ({_sql_list(ALL_DAYS)})),
        meal      TEXT NOT NULL CHECK (meal IN ({_sql_list(MEALS)})),
        recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
        PRIMARY KEY (day, meal)
    );
    """


def _schema_sql():
    return f"""
    -- Recetas. El tipo decide en qué hueco del menú pueden entrar:
    --   'ambos' (por defecto) comida o cena, 'comida', 'cena', y
    --   'extra' = elaboraciones especiales que nunca entran en el menú automático.
    CREATE TABLE IF NOT EXISTS recipes (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        name  TEXT NOT NULL CHECK (length(trim(name)) > 0),
        type  TEXT NOT NULL DEFAULT 'ambos'
              CHECK (type IN ({_sql_list(RECIPE_TYPES)}))
    );

    -- Ingredientes de cada receta.
    --  * ON DELETE CASCADE: al borrar la receta se borran sus ingredientes.
    --  * position conserva el orden en que se escribieron.
    --  * name se guarda ya normalizado (Cebolla, Pina...) para poder sumarlos.
    CREATE TABLE IF NOT EXISTS ingredients (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        position  INTEGER NOT NULL DEFAULT 0,
        name      TEXT NOT NULL CHECK (length(trim(name)) > 0),
        qty       REAL,                         -- NULL = sin cantidad
        unit      TEXT                          -- NULL = sin unidad
    );

    CREATE INDEX IF NOT EXISTS idx_ingredients_recipe
        ON ingredients(recipe_id, position);

    {_menu_sql()}

    -- Lista de la compra: ingredientes ya comprados o que ya hay en casa.
    -- La lista en sí se calcula al vuelo a partir del menú; aquí solo se guarda
    -- la marca. Clave = (nombre normalizado, unidad); '' significa "sin unidad".
    -- Se vacía al generar un menú nuevo.
    CREATE TABLE IF NOT EXISTS shopping_checked (
        name TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (name, unit)
    );
    """


# ---------------------------------------------------------
# MIGRACIONES
# ---------------------------------------------------------

def _migrate_to_v2(conn):
    """
    Actualiza una base de la versión 1 (sin tipo de receta, menú de una sola
    comida al día e ingredientes sin normalizar). No pierde datos:
      - las recetas existentes pasan a tipo 'ambos'
      - lo que había en el menú pasa a la 'comida' de cada día
      - los nombres de ingredientes y las unidades se normalizan
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
        # SQLite no puede cambiar la clave primaria: se renombra, se crea la
        # tabla nueva y se copian las filas.
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


# La versión 3 solo añade la tabla shopping_checked: no hace falta migrar datos,
# la crea _schema_sql() con IF NOT EXISTS.


def create_tables():
    """Crea las tablas (o actualiza las antiguas). Se puede llamar cuantas veces se quiera."""
    with connection() as conn:
        # WAL: más robusto ante cortes de luz y permite leer mientras se escribe.
        conn.execute("PRAGMA journal_mode = WAL")

        has_recipes = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recipes'"
        ).fetchone()
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        if has_recipes and version < 2:
            _migrate_to_v2(conn)

        conn.executescript(_schema_sql())

        # Migración aditiva: conserva IDs, ingredientes, menú y marcas existentes.
        recipe_cols = {r["name"] for r in conn.execute("PRAGMA table_info(recipes)")}
        for column, definition in {
            "servings": "INTEGER NOT NULL DEFAULT 2 CHECK (servings > 0)",
            "preparation": "TEXT NOT NULL DEFAULT '[]'",
            "notes": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in recipe_cols:
                conn.execute(f"ALTER TABLE recipes ADD COLUMN {column} {definition}")
        menu_cols = {r["name"] for r in conn.execute("PRAGMA table_info(menu)")}
        if "people" not in menu_cols:
            conn.execute("ALTER TABLE menu ADD COLUMN people INTEGER CHECK (people > 0)")


        # Una fila por cada día y comida (los 7 días), para poder activar más
        # días con MENU_DAYS sin tocar la base de datos.
        conn.executemany(
            "INSERT OR IGNORE INTO menu (day, meal, recipe_id) VALUES (?, ?, NULL)",
            [(d, m) for d in ALL_DAYS for m in MEALS],
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ---------------------------------------------------------
# EJECUCIÓN DIRECTA
# ---------------------------------------------------------

if __name__ == "__main__":
    create_tables()
    data = read_all()
    print(f"✔ Base de datos lista en: {DB_PATH}")
    for table, rows in data.items():
        print(f"  {table + ':':18} {len(rows)} filas")