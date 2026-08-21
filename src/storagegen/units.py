"""Unit helpers.

Everything inside the generators is millimetres.  Inches only appear at the
edges: preset tables transcribed from a manufacturer's spec sheet, and the
human-readable listing text.
"""

MM_PER_INCH = 25.4


def inch(value: float) -> float:
    """Inches -> mm."""
    return value * MM_PER_INCH


def to_inch(value_mm: float) -> float:
    """mm -> inches."""
    return value_mm / MM_PER_INCH


def mm_in(value_mm: float, places: int = 1) -> str:
    """Format a millimetre value as `123.4 mm (4.86 in)` for listings."""
    return f"{value_mm:.{places}f} mm ({to_inch(value_mm):.2f} in)"
