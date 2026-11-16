"""Observed-grid border classification.

A die is on the border when its coordinate lies on the outermost X or Y of the
points being classified. Remaining positions are interior. This is the bounding
box of the observed grid, not distance from the origin and not a circular wafer.
"""

from __future__ import annotations

Bounds = tuple[float, float, float, float]


def grid_bounds(points: list[tuple[float, float]]) -> Bounds:
    if not points:
        raise ValueError("grid_bounds requires at least one coordinate")
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), max(xs), min(ys), max(ys))


def is_grid_border(x: float, y: float, bounds: Bounds) -> bool:
    x_min, x_max, y_min, y_max = bounds
    return x == x_min or x == x_max or y == y_min or y == y_max


def is_positive_filled_grid(points: list[tuple[float, float]]) -> bool:
    """True for a corner-origin integer rectangle such as the V2 10×10 grid.

    Centered layouts that include the origin or negative coordinates keep the
    existing radial regions. This does not infer a circular wafer.
    """
    if len(points) < 4:
        return False
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    if min(xs) < 1 or min(ys) < 1:
        return False
    cells: set[tuple[int, int]] = set()
    for x, y in points:
        if x != int(x) or y != int(y):
            return False
        cells.add((int(x), int(y)))
    x_min, x_max = int(min(xs)), int(max(xs))
    y_min, y_max = int(min(ys)), int(max(ys))
    expected = {(x, y) for x in range(x_min, x_max + 1) for y in range(y_min, y_max + 1)}
    return cells == expected
