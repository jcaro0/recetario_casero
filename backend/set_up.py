"""
Esquema de la base de datos y migraciones entre versiones.

Este módulo SOLO crea tablas y migra datos antiguos. La conexión, las rutas y
las constantes viven en database.py. Este módulo se ejecuta únicamente mediante
la administración explícita. La API nunca aplica migraciones.

Uso manual (con la aplicación detenida):
    python manage.py migrate

Esquema (versión 6):
    recipes           (id, name, type, servings, preparation, notes)
    ingredients       (id, recipe_id, position, name, qty, unit)
    menu              (day, meal, recipe_id, people) meal: comida | cena
    shopping_checked  (name, unit)                 ingredientes ya comprados / en casa
    settings          (key, value)                 preferencias de la semana
    manual_products   (id, name, qty, unit, checked)
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import backup
import database as db
from database import ALL_DAYS, MEALS, RECIPE_TYPES, SCHEMA_VERSION
from normalize import collapse_spaces, normalize_unit, text_key


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

    CREATE TABLE IF NOT EXISTS manual_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        qty REAL,
        unit TEXT,
        checked INTEGER NOT NULL DEFAULT 0 CHECK (checked IN (0, 1))
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

    recipe_cols = db.columns(conn, "recipes")
    if "type" not in recipe_cols:
        conn.execute(
            "ALTER TABLE recipes ADD COLUMN type TEXT NOT NULL DEFAULT 'ambos' "
            f"CHECK (type IN ({_sql_list(RECIPE_TYPES)}))"
        )

    menu_cols = db.columns(conn, "menu")
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
        folded = text_key(row["name"])
        name = (folded[:1].upper() + folded[1:]) or row["name"]
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
    path = Path(db.DB_PATH)
    if not path.is_absolute():
        raise ValueError('DB_PATH debe ser absoluto')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    create_tables(_new=True)


def initialize_if_missing():
    """Crea la base solo si falta su archivo y no quedan auxiliares de SQLite."""
    path = Path(db.DB_PATH)
    try:
        path.lstat()
    except FileNotFoundError:
        for suffix in ("-wal", "-shm", "-journal"):
            if os.path.lexists(str(path) + suffix):
                raise RuntimeError(f"Falta {path} pero existe {path}{suffix}. Revisa los archivos de SQLite.")
        try:
            initialize()
        except FileExistsError:
            # Otro arranque pudo crear el archivo. Se valida después, igual que uno existente.
            return False
        return True
    return False


def create_tables(_new=False):
    """Migración explícita, respaldada y atómica; no crea archivos ausentes."""
    with closing(db._open()) as conn:
        version = 0 if _new else db.check_schema(conn)
        if not _new:
            if version == SCHEMA_VERSION:
                return
            directory = os.environ.get('BACKUP_DIR')
            if not directory:
                raise RuntimeError('Configura BACKUP_DIR fuera del repositorio antes de migrar.')
            saved = backup.backup(db.DB_PATH, directory, label='before-migration')
            print(f'Copia verificada antes de migrar: {saved}')
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            if not _new and version < 2:
                _migrate_to_v2(conn)
            # executescript hace commit implícito: ejecutar cada sentencia conserva
            # toda la migración en una única transacción, incluso DDL.
            statement = ''
            for line in _schema_sql().splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    conn.execute(statement)
                    statement = ''
            _upgrade_columns(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Relaciones inválidas: migración cancelada.')
        conn.execute('PRAGMA journal_mode=WAL')


def _upgrade_columns(conn):
    # Migración aditiva: conserva IDs, ingredientes, menú y marcas existentes.
    recipe_cols = db.columns(conn, "recipes")
    for column, definition in {
        "servings": "INTEGER NOT NULL DEFAULT 2 CHECK (servings > 0)",
        "preparation": "TEXT NOT NULL DEFAULT '[]'",
        "notes": "TEXT NOT NULL DEFAULT ''",
    }.items():
        if column not in recipe_cols:
            conn.execute(f"ALTER TABLE recipes ADD COLUMN {column} {definition}")
    menu_cols = db.columns(conn, "menu")
    if "people" not in menu_cols:
        conn.execute("ALTER TABLE menu ADD COLUMN people INTEGER CHECK (people > 0)")

    # Una fila por cada día y comida (los 7 días), para poder activar más
    # días con MENU_DAYS sin tocar la base de datos.
    conn.executemany(
        "INSERT OR IGNORE INTO menu (day, meal, recipe_id) VALUES (?, ?, NULL)",
        [(d, m) for d in ALL_DAYS for m in MEALS],
    )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
