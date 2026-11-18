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

# Alias completos, deliberadamente sin recortar sufijos de palabras desconocidas.
INGREDIENT_ALIASES = {
    'tomates': 'tomate', 'huevos': 'huevo', 'cebollas': 'cebolla',
    'patatas': 'patata', 'pimientos': 'pimiento',
    'dientes de ajo': 'diente de ajo',
}


def ingredient_key(name):
    text = strip_accents(collapse_spaces(name)).lower()
    canonical = INGREDIENT_ALIASES.get(text, text)
    return canonical[:1].upper() + canonical[1:]


def parse_quantity(value):
    """Decimal o fracción no negativa; devuelve None para texto libre/no numérico."""
    from decimal import Decimal, InvalidOperation
    from fractions import Fraction
    if value is None or isinstance(value, bool):
        return None
    text = collapse_spaces(value).replace(',', '.')
    for symbol, fraction in {'½': '1/2', '¼': '1/4', '¾': '3/4'}.items():
        text = text.replace(symbol, ' ' + fraction).strip()
    try:
        if re.fullmatch(r'\d+\s+\d+/\d+', text):
            whole, part = text.split()
            number = Fraction(whole) + Fraction(part)
            result = Decimal(number.numerator) / Decimal(number.denominator)
        elif re.fullmatch(r'\d+/\d+', text):
            number = Fraction(text)
            result = Decimal(number.numerator) / Decimal(number.denominator)
        else:
            result = Decimal(text)
        return result if result.is_finite() and result >= 0 else None
    except (ValueError, ZeroDivisionError, InvalidOperation):
        return None
