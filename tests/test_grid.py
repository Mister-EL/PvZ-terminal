import unittest
from pvz.grid import Grid
from pvz.types import Plant, PlantType


class GridTests(unittest.TestCase):
    def test_outside_reads_do_not_wrap(self):
        grid = Grid(2, 2)
        grid.set(Plant(PlantType.SUNFLOWER, 1, 1, 200))
        for row, col in ((-1, -1), (2, 0), (0, 2)):
            self.assertIsNone(grid.get(row, col))

    def test_outside_writes_cannot_change_last_cell(self):
        grid = Grid(2, 2)
        plant = Plant(PlantType.SUNFLOWER, 1, 1, 200)
        grid.set(plant)
        with self.assertRaises(ValueError):
            grid.remove(-1, -1)
        with self.assertRaises(ValueError):
            grid.set(Plant(PlantType.SUNFLOWER, -1, -1, 200))
        self.assertIs(grid.get(1, 1), plant)

    def test_grid_requires_positive_integer_dimensions(self):
        for dimensions in ((0, 2), (2, -1), (1.5, 2), (True, 2)):
            with self.assertRaises(ValueError):
                Grid(*dimensions)
