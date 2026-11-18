"""
Esquema de la base de datos y migraciones entre versiones.

Este módulo SOLO crea tablas y migra datos antiguos. La conexión, las rutas y
las constantes viven en database.py. Este módulo se ejecuta únicamente mediante
la administración explícita. La API nunca aplica migraciones.

Uso manual (con la aplicación detenida):
    python manage.py migrate

Esquema (versión 5):
    recipes           (id, name, type, servings, preparation, notes)
    ingredients       (id, recipe_id, position, name, qty, unit)
    menu              (day, meal, recipe_id, people) meal: comida | cena
    shopping_checked  (name, unit)                 ingredientes ya comprados / en casa
    settings          (key, value)                 preferencias de la semana
"""

from database import (
    ALL_DAYS,
    DB_PATH,
    MEALS,
    RECIPE_TYPES,
    SCHEMA_VERSION,
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
    --  * name conserva el nombre legible; los alias se aplican al calcular compra.
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
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

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
            "INSERT INTO menu (day, meal, recipe_id) "
            "SELECT day, 'comida', recipe_id FROM menu_old"
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



# La versión 3 solo añade la tabla shopping_checked: no hace falta migrar datos,
# la crea _schema_sql() con IF NOT EXISTS.


def initialize():
    """Solo instalaciones nuevas, nunca sobrescribe un archivo existente."""
    import os
    import database as db
    from pathlib import Path
    path = Path(db.DB_PATH)
    if not path.is_absolute():
        raise ValueError('DB_PATH debe ser absoluto')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    create_tables(_new=True)


def create_tables(_new=False):
    """Migración explícita, respaldada y atómica; no crea archivos ausentes."""
    import os
    import database as db
    from contextlib import closing
    from backup import backup
    with closing(db._open()) as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError('Esquema demasiado nuevo. Actualiza el código; no restaures una copia antigua.')
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not _new:
            if not {'recipes', 'ingredients', 'menu'} <= tables:
                raise RuntimeError('Esquema desconocido o vacío: comprueba la base activa.')
            if version == SCHEMA_VERSION:
                if db._needs_setup():
                    raise RuntimeError('Esquema incompleto; revisa la base sin inicializarla.')
                return
            directory = os.environ.get('BACKUP_DIR')
            if not directory:
                raise RuntimeError('Configura BACKUP_DIR fuera del repositorio antes de migrar.')
            saved = backup(db.DB_PATH, directory, label='before-migration')
            print(f'Copia verificada antes de migrar: {saved}')
        try:
            conn.execute('BEGIN IMMEDIATE')
            if not _new and version < 2:
                _migrate_to_v2(conn)
            # executescript hace commit implícito: ejecutar cada sentencia conserva
            # toda la migración en una única transacción, incluso DDL.
            import sqlite3
            statement = ''
            for line in _schema_sql().splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    conn.execute(statement)
                    statement = ''
            _upgrade_columns(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Relaciones inválidas: migración cancelada.')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        conn.execute('PRAGMA journal_mode=WAL')


def _upgrade_columns(conn):
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
