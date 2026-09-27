import concurrent.futures
import dataclasses
import datetime
import os
import pathlib
import random
import shutil
import threading

from arena import book
from arena.game import EngineWrapper, GameRunner
from arena.pgn import write_game
from bots.baseline_wdl import BaselineWDLBot
from engines.uci import Engine

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAMES_DIR = ROOT / "games"
MAIA_DIR = pathlib.Path(os.path.expanduser("~/lc0-weights/maia"))

PHILIDOR_DEPTH = 10
ENGINE_TIMEOUT = 120.0


@dataclasses.dataclass(frozen=True)
class Level:
    number: int
    name: str
    kind: str
    setting: int
    represents: str

    @property
    def pgn_path(self):
        return GAMES_DIR / f"level{self.number}_{self.name}.pgn"


LEVELS = (
    Level(1, "maia1100", "maia", 1100, "beginner"),
    Level(2, "maia1500", "maia", 1500, "intermediate"),
    Level(3, "maia1900", "maia", 1900, "strong club"),
    Level(4, "stockfish_d8", "stockfish", 8, "expert"),
    Level(5, "stockfish_d20", "stockfish", 20, "far above human"),
)


def level_by_number(number):
    for level in LEVELS:
        if level.number == number:
            return level
    raise ValueError(f"no ladder level numbered {number}")


def stockfish_path():
    path = shutil.which("stockfish")
    if path is None:
        raise FileNotFoundError("stockfish not found on PATH")
    return path


def lc0_path():
    path = shutil.which("lc0")
    if path is None:
        raise FileNotFoundError("lc0 not found on PATH")
    return path


def maia_weights(rating):
    path = MAIA_DIR / f"maia-{rating}.pb.gz"
    if not path.exists():
        raise FileNotFoundError(f"missing Maia weights: {path}")
    return path


def open_philidor_engine():
    return Engine(
        stockfish_path(), {"UCI_ShowWDL": "true"}, timeout=ENGINE_TIMEOUT
    )


def open_opponent_engine(level):
    if level.kind == "maia":
        args = [
            lc0_path(),
            f"--weights={maia_weights(level.setting)}",
            "--backend=blas",
        ]
        return Engine(args, {}, timeout=ENGINE_TIMEOUT), {"nodes": 1}
    return Engine(stockfish_path(), {}, timeout=ENGINE_TIMEOUT), {
        "depth": level.setting
    }


def opponent_label(level):
    if level.kind == "maia":
        return f"Maia {level.setting} (nodes=1)"
    return f"Stockfish (depth={level.setting})"


@dataclasses.dataclass
class GameSpec:
    index: int
    opening: object
    philidor_is_white: bool
    seed: int


class LevelRunner:
    def __init__(self, level, depth=PHILIDOR_DEPTH, max_plies=None):
        self.level = level
        self.depth = depth
        self.max_plies = max_plies
        self.local = threading.local()
        self.engines = []
        self.engines_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.failures = []

    def _engines(self):
        cached = getattr(self.local, "engines", None)
        if cached is not None:
            philidor_engine, opponent_engine, opponent_kw = cached
            if philidor_engine.alive and opponent_engine.alive:
                return cached
            self._discard(cached)
        philidor_engine = open_philidor_engine()
        opponent_engine, opponent_kw = open_opponent_engine(self.level)
        cached = (philidor_engine, opponent_engine, opponent_kw)
        with self.engines_lock:
            self.engines.append(philidor_engine)
            self.engines.append(opponent_engine)
        self.local.engines = cached
        return cached

    def _discard(self, cached):
        self.local.engines = None
        for engine in cached[:2]:
            with self.engines_lock:
                if engine in self.engines:
                    self.engines.remove(engine)
            try:
                engine.close()
            except Exception:
                pass

    def play(self, spec):
        philidor_engine, opponent_engine, opponent_kw = self._engines()
        bot = BaselineWDLBot(
            philidor_engine, depth=self.depth, rng=random.Random(spec.seed)
        )
        opponent = EngineWrapper(opponent_engine, **opponent_kw)
        kwargs = {}
        if self.max_plies is not None:
            kwargs["max_plies"] = self.max_plies
        runner = GameRunner(
            bot,
            opponent,
            philidor_is_white=spec.philidor_is_white,
            opening=spec.opening,
            **kwargs,
        )
        result = runner.loop()
        self._write(runner, spec, result)
        return result

    def _write(self, runner, spec, result):
        colour = "white" if spec.philidor_is_white else "black"
        label = opponent_label(self.level)
        headers = {
            "Event": "Philidor phase one baseline",
            "Site": "local",
            "Date": datetime.date.today().strftime("%Y.%m.%d"),
            "Round": spec.index + 1,
            "White": "Philidor baseline_wdl" if spec.philidor_is_white else label,
            "Black": label if spec.philidor_is_white else "Philidor baseline_wdl",
            "PhilidorColor": colour,
            "PhilidorLevel": self.level.number,
            "PhilidorDepth": self.depth,
            "Opponent": self.level.name,
            "ECO": spec.opening.eco,
            "OpeningName": spec.opening.name,
            "OpeningPlies": runner.opening_plies,
            "TotalPlies": len(runner.board.move_stack),
            "FinalHalfmoveClock": runner.board.halfmove_clock,
            "Termination": runner.termination(),
            "Seed": spec.seed,
        }
        write_game(
            runner.board,
            result,
            self.level.pgn_path,
            headers=headers,
            lock=self.write_lock,
        )

    def close(self):
        with self.engines_lock:
            engines = list(self.engines)
            self.engines = []
        for engine in engines:
            try:
                engine.close()
            except Exception:
                pass


def build_specs(level, games, seed):
    band = book.load_book()
    rng = random.Random(seed * 1000 + level.number)
    pairs = (games + 1) // 2
    specs = []
    for pair in range(pairs):
        opening = rng.choice(band)
        for offset, is_white in enumerate((True, False)):
            index = pair * 2 + offset
            specs.append(
                GameSpec(
                    index=index,
                    opening=opening,
                    philidor_is_white=is_white,
                    seed=seed * 1000000 + level.number * 10000 + index,
                )
            )
    return specs


def run_level(level, games=100, workers=5, seed=0, depth=PHILIDOR_DEPTH, max_plies=None):
    GAMES_DIR.mkdir(exist_ok=True)
    if level.pgn_path.exists():
        level.pgn_path.unlink()
    specs = build_specs(level, games, seed)
    runner = LevelRunner(level, depth=depth, max_plies=max_plies)
    done = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(runner.play, spec): spec for spec in specs}
            for future in concurrent.futures.as_completed(futures):
                spec = futures[future]
                try:
                    future.result()
                except Exception as error:
                    runner.failures.append((spec.index, repr(error)))
                done += 1
                if done % 10 == 0 or done == len(specs):
                    print(
                        f"level {level.number} {level.name}: "
                        f"{done}/{len(specs)} games, {len(runner.failures)} failed",
                        flush=True,
                    )
    finally:
        runner.close()
    for index, error in runner.failures:
        print(f"  game {index} failed: {error}", flush=True)
    return len(specs), runner.failures


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the Philidor opponent ladder")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--depth", type=int, default=PHILIDOR_DEPTH)
    parser.add_argument("--max-plies", type=int, default=None)
    parser.add_argument("--levels", default="1,2,3,4,5")
    args = parser.parse_args()

    numbers = [int(part) for part in args.levels.split(",") if part.strip()]
    for number in numbers:
        level = level_by_number(number)
        total, failures = run_level(
            level,
            games=args.games,
            workers=args.workers,
            seed=args.seed,
            depth=args.depth,
            max_plies=args.max_plies,
        )
        print(
            f"level {level.number} {level.name} complete: "
            f"{total - len(failures)}/{total} games written to {level.pgn_path}",
            flush=True,
        )


if __name__ == "__main__":
    main()
