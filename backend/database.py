import os
import json
from typing import Optional, cast

import redis

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

# Deben coincidir EXACTAMENTE (en minúscula) con los nombres de DAYS en script.js
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

_client: Optional["redis.Redis"] = None


def get_redis() -> redis.Redis:
    """Devuelve un cliente Redis reutilizable (conexión perezosa)."""
    global _client
    if _client is None:
        # redis-py comparte la misma clase para el cliente síncrono y el
        # asíncrono, lo que a veces confunde a Pylance y le hace pensar que
        # los métodos devuelven Awaitable. Con decode_responses=True y este
        # cast fijamos el tipo correcto: es un cliente 100% síncrono.
        _client = cast(
            "redis.Redis",
            redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
            ),
        )
    return _client


# ---------------------------------------------------------
# RECETAS
# ---------------------------------------------------------

def next_recipe_id():
    return get_redis().incr("recipe:id:seq")


def save_recipe(recipe):
    r = get_redis()
    r.hset("recipes", str(recipe["id"]), json.dumps(recipe))
    return recipe


def get_recipe(recipe_id):
    if recipe_id is None:
        return None
    r = get_redis()
    data = cast(Optional[str], r.hget("recipes", str(recipe_id)))
    return json.loads(data) if data else None


def get_all_recipes():
    r = get_redis()
    values = cast(list, r.hvals("recipes"))
    recipes = [json.loads(v) for v in values]
    recipes.sort(key=lambda x: x["id"])
    return recipes


def delete_recipe(recipe_id):
    r = get_redis()
    r.hdel("recipes", str(recipe_id))

    # Si esa receta estaba puesta en el menú de algún día, se limpia
    menu = cast(dict, r.hgetall("menu"))
    for day, rid in menu.items():
        if str(rid) == str(recipe_id):
            r.hdel("menu", day)


# ---------------------------------------------------------
# MENÚ SEMANAL
# ---------------------------------------------------------

def get_menu():
    """Devuelve un dict {dia: receta_completa_o_None}."""
    r = get_redis()
    raw = cast(dict, r.hgetall("menu"))

    menu = {}
    for day in DAYS:
        rid = raw.get(day)
        menu[day] = get_recipe(rid) if rid else None
    return menu


def set_menu_day(day, recipe_id):
    get_redis().hset("menu", day, recipe_id)


def clear_menu():
    get_redis().delete("menu")