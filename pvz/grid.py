from __future__ import annotations

from typing import List, Optional

from .types import Plant


class Grid:
    def __init__(self, width: int, height: int) -> None:
        if any(type(n) is not int or n <= 0 for n in (width, height)):
            raise ValueError("Grid dimensions must be positive integers")
        self.width = width
        self.height = height
        self._cells: List[List[Optional[Plant]]] = [
            [None for _ in range(width)] for _ in range(height)
        ]

    def is_inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.height and 0 <= col < self.width

    def get(self, row: int, col: int) -> Optional[Plant]:
        if not self.is_inside(row, col):
            return None
        return self._cells[row][col]

    def set(self, plant: Plant) -> None:
        if not self.is_inside(plant.row, plant.col):
            raise ValueError("Plant is outside the grid")
        self._cells[plant.row][plant.col] = plant

    def remove(self, row: int, col: int) -> None:
        if not self.is_inside(row, col):
            raise ValueError("Cell is outside the grid")
        self._cells[row][col] = None

    def iter_plants(self) -> List[Plant]:
        return [plant for row in self._cells for plant in row if plant]
