"""Nombres, cantidades y agrupación de ingredientes para la compra."""

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from fractions import Fraction

def collapse_spaces(text):
    """Quita espacios al principio/final y reduce cualquier hueco a un solo espacio."""
    return re.sub(r"\s+", " ", str(text if text is not None else "")).strip()


def strip_accents(text):
    """Quita tildes y diéresis. La ñ se convierte en n (es una n + tilde combinada)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def text_key(text):
    return strip_accents(collapse_spaces(text)).lower()


def normalize_unit(unit):
    """Unidad en minúscula y sin tildes. Devuelve None si queda vacía."""
    return text_key(unit) or None

# Alias completos, deliberadamente sin recortar sufijos de palabras desconocidas.
INGREDIENT_ALIASES = {
    'tomates': 'tomate', 'huevos': 'huevo', 'cebollas': 'cebolla',
    'patatas': 'patata', 'pimientos': 'pimiento',
    'dientes de ajo': 'diente de ajo',
}


def ingredient_key(name):
    text = text_key(name)
    canonical = INGREDIENT_ALIASES.get(text, text)
    return canonical[:1].upper() + canonical[1:]


UNIT_ALIASES = {
    "kg": ("g", 1000), "kilogramo": ("g", 1000), "kilogramos": ("g", 1000),
    "gramos": ("g", 1), "gr": ("g", 1), "gramo": ("g", 1),
    "l": ("ml", 1000), "litro": ("ml", 1000), "litros": ("ml", 1000),
    "mililitro": ("ml", 1), "mililitros": ("ml", 1),
    "cucharada": ("cda", 1), "cucharadas": ("cda", 1),
    "cucharadita": ("cdta", 1), "cucharaditas": ("cdta", 1),
    "tazas": ("taza", 1),
    "ud": ("uds", 1), "unidad": ("uds", 1), "unidades": ("uds", 1),
}
FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4"}


def _decimal_quantity(value):
    if value is None or isinstance(value, bool):
        return None
    text = collapse_spaces(value).replace(",", ".")
    for symbol, fraction in FRACTIONS.items():
        text = text.replace(symbol, " " + fraction).strip()
    try:
        if re.fullmatch(r"(?:(\d+) )?(\d+/\d+)", text):
            parts = text.split()
            fraction = Fraction(parts[-1]) + (int(parts[0]) if len(parts) == 2 else 0)
            return Decimal(fraction.numerator) / Decimal(fraction.denominator)
        return Decimal(text)
    except (ValueError, ZeroDivisionError, InvalidOperation):
        return None


def parse_quantity(value):
    """Para el cálculo, ignora el texto libre y las cifras inválidas de bases antiguas."""
    number = _decimal_quantity(value)
    return number if number is not None and number.is_finite() and number >= 0 else None


def clean_quantity(value):
    """Valida la cantidad recibida y conserva el texto libre."""
    if value in (None, ""):
        return None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ValueError("La cantidad debe ser un número o texto")
    number = _decimal_quantity(value)
    if number is None:
        return str(value).strip()
    if not number.is_finite() or number < 0:
        raise ValueError("La cantidad debe ser finita y positiva o cero")
    result = float(number)
    if not math.isfinite(result):
        raise ValueError("Cantidad fuera de rango")
    return result


def display_quantity(qty):
    """SQLite devuelve REAL incluso cuando la cantidad es un entero."""
    return int(qty) if isinstance(qty, float) and qty.is_integer() else qty


def _shopping_unit(unit):
    unit = normalize_unit(unit)
    return UNIT_ALIASES.get(unit, (unit, 1))


def shopping_key(name, unit):
    """Las marcas antiguas pueden tener nombres o unidades no canónicos."""
    return ingredient_key(name), _shopping_unit(unit)[0] or ""


def group_shopping(rows, checked):
    totals = {}
    unscaled = set()
    for row in rows:
        name = ingredient_key(row["name"])
        if not name:
            continue
        qty = parse_quantity(row["qty"])
        unit, factor = _shopping_unit(row["unit"])
        if qty is None:
            # Conserva el texto y las ausencias aunque también haya una cantidad numérica.
            raw = row["qty"]
            unscaled.add((name, unit, None if raw is None else str(raw)))
        else:
            servings = row["servings"]
            key = (name, unit or "uds")
            scaled = qty * factor * Decimal(row["people"] or servings) / Decimal(servings)
            totals[key] = totals.get(key, Decimal(0)) + scaled

    amounts = [(name, unit, display_quantity(float(round(qty, 6))))
               for (name, unit), qty in totals.items()]
    amounts.extend(unscaled)
    amounts.sort(key=lambda item: (item[0], item[1] or "", str(item[2])))
    return [dict(name=name, unit=unit, qty=qty, checked=(name, unit or "") in checked)
            for name, unit, qty in amounts]
