# -*- coding: utf-8 -*-
"""Pure numerical rules; lengths are Revit internal feet."""
TOL = 1.0e-4


def suggest_wall_type(thickness, candidates):
    """Return a width-based UI suggestion, not a material/structural equivalence.

    Candidates are (index, width). Stable ordering breaks equal-width ties;
    the user reviews the actual type in the mapping dropdown before creation.
    """
    valid = [(index, width) for index, width in candidates if width > TOL]
    if thickness <= TOL or not valid:
        return None, False
    index, width = min(valid, key=lambda item: (abs(item[1]-thickness), item[0]))
    return index, abs(width-thickness) <= TOL


def structure_layer(layers):
    """(width, is_structure) in exterior-to-interior order. Never use names."""
    candidates = [i for i, layer in enumerate(layers) if layer[1] and layer[0] > TOL]
    if not candidates:
        raise ValueError('No positive-width Structure [1] layer.')
    index = max(candidates, key=lambda i: layers[i][0])
    total = sum(layer[0] for layer in layers)
    center = total / 2.0 - sum(layers[i][0] for i in range(index)) - layers[index][0] / 2.0
    return index, layers[index][0], center


