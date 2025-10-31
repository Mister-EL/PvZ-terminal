from __future__ import annotations

from typing import List, Optional

from .types import Plant


class Grid:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._cells: List[List[Optional[Plant]]] = [
            [None for _ in range(width)] for _ in range(height)
        ]

    def is_inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.height and 0 <= col < self.width

    def get(self, row: int, col: int) -> Optional[Plant]:
        return self._cells[row][col]

    def set(self, plant: Plant) -> None:
        self._cells[plant.row][plant.col] = plant

    def remove(self, row: int, col: int) -> None:
        self._cells[row][col] = None

    def iter_plants(self) -> List[Plant]:
        return [plant for row in self._cells for plant in row if plant]
