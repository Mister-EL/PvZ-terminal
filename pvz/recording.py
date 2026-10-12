"""Record ordinary live inputs without changing the game's rules."""
from __future__ import annotations

from .replay import ReplayRecorder
from .types import PlantType


class MatchRecording:
    def __init__(self, game):
        self.game = game
        self.recorder = ReplayRecorder(game.seed, scenario=game.scenario.id if game.scenario else None,
                                       difficulty=game.difficulty)

    def handle_keypress(self, key: int) -> None:
        game = self.game
        if game.game_over:
            return
        kind, extra = None, {}
        if key in (ord("q"), ord("Q")):
            kind = "quit"
        elif key in (ord("p"), ord("P")):
            kind = "resume" if game.paused else "pause"
        elif key in (ord("w"), ord("W"), ord("s"), ord("S"), ord("a"), ord("A"), ord("d"), ord("D")):
            kind = "move"
            extra = {"direction": {"w": "up", "s": "down", "a": "left", "d": "right"}[chr(key).lower()]}
        elif ord("1") <= key <= ord("9"):
            plant = tuple(PlantType)[key - ord("1")]
            if plant in game.allowed_plants:
                kind, extra = "select", {"plant": plant.name}
        elif key == ord(" "):
            kind = "plant"
        elif key in (ord("r"), ord("R")):
            kind = "dig"
        if kind:
            self.recorder.record(game.time_elapsed, kind, **extra)
        game.handle_keypress(key)

    def finish(self):
        return self.recorder.finish(self.game.time_elapsed)
