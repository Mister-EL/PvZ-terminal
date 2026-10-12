import unittest

from pvz.game import Game
from pvz.ui import Screen, clip_text, draw_game


class Window:
    def __init__(self, rows=24, cols=80):
        self.rows, self.cols = rows, cols
        self.lines = {}

    def getmaxyx(self):
        return self.rows, self.cols

    def addstr(self, y, x, value, style=0):
        if not (0 <= y < self.rows and 0 <= x < self.cols - 1):
            raise AssertionError("out of bounds")
        width = sum(0 if __import__('unicodedata').combining(c) else 2 if __import__('unicodedata').east_asian_width(c) in 'WF' else 1 for c in value)
        if x + width >= self.cols:
            raise AssertionError("line overflow")
        self.lines[y, x] = value

    def erase(self):
        self.lines.clear()

    def refresh(self):
        pass


class TerminalRenderingTests(unittest.TestCase):
    def test_unicode_clipping_and_control_filtering(self):
        self.assertEqual(clip_text("A界Б", 3), "A界")
        self.assertEqual(clip_text("е\u0301щё", 1), "е\u0301")
        self.assertEqual(clip_text("x\n\x1b[31m", 10), "x[31m")

    def test_render_is_safe_at_minimum_and_tiny_sizes(self):
        game = Game(0.2, 1)
        for rows, cols in ((24, 76), (24, 80), (1, 1), (10, 30), (50, 160)):
            with self.subTest(rows=rows, cols=cols):
                window = Window(rows, cols)
                draw_game(window, game)
                self.assertEqual(game.time_elapsed, 0)
                if rows >= 24 and cols >= 76:
                    self.assertTrue(any("Косилки" in s for s in window.lines.values()))

    def test_all_nine_slots_and_cursor_are_visible(self):
        window = Window()
        game = Game(.2, 1)
        draw_game(window, game)
        values = list(window.lines.values())
        for slot in range(1, 10):
            self.assertTrue(any(s.startswith(str(slot)) for s in values))
        self.assertTrue(any("[ . ]" == s for s in values))
