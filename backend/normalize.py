"""
Normalización de textos para que los ingredientes se puedan comparar y sumar.

    "  CEBOLLA "   -> "Cebolla"
    "piña  tropical" -> "Pina tropical"
    "Pimiento Rojo" -> "Pimiento rojo"
"""

import re
import unicodedata


def collapse_spaces(text):
    """Quita espacios al principio/final y reduce cualquier hueco a un solo espacio."""
    return re.sub(r"\s+", " ", str(text if text is not None else "")).strip()


def strip_accents(text):
    """Quita tildes y diéresis. La ñ se convierte en n (es una n + tilde combinada)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_ingredient_name(name):
    """Primera letra en mayúscula, el resto en minúscula, sin tildes ni ñ."""
    text = strip_accents(collapse_spaces(name)).lower()
    return text[:1].upper() + text[1:]


def normalize_unit(unit):
    """Unidad en minúscula y sin tildes. Devuelve None si queda vacía."""
    text = strip_accents(collapse_spaces(unit)).lower()
    return text or None