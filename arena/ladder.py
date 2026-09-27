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

    def filename(self):
        return f"level{self.number}_{self.name}.pgn"


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


def open_philidor_engine(timeout=ENGINE_TIMEOUT):
    return Engine(stockfish_path(), {"UCI_ShowWDL": "true"}, timeout=timeout)


def open_opponent_engine(level, timeout=ENGINE_TIMEOUT):
    if level.kind == "maia":
        args = [
            lc0_path(),
            f"--weights={maia_weights(level.setting)}",
            "--backend=blas",
        ]
        return Engine(args, {}, timeout=timeout), {"nodes": 1}
    return Engine(stockfish_path(), {}, timeout=timeout), {"depth": level.setting}


def opponent_label(level):
    if level.kind == "maia":
        return f"Maia {level.setting} (nodes=1)"
    return f"Stockfish (depth={level.setting})"


LCZERO_DIR = pathlib.Path(os.path.expanduser("~/lc0-weights/lczero"))
LCZERO_NET = "t1-256x10-distilled-swa-2432500.pb.gz"
LC0_CONTEMPT_NODES = 400


def lczero_weights(name=LCZERO_NET):
    path = LCZERO_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing lc0 network: {path}")
    return path


@dataclasses.dataclass(frozen=True)
class Challenger:
    name: str
    label: str
    open_engines: object
    make_player: object


def baseline_wdl_challenger(depth=PHILIDOR_DEPTH):
    def open_engines(timeout):
        return [open_philidor_engine(timeout)]

    def make_player(engines, seed):
        return BaselineWDLBot(engines[0], depth=depth, rng=random.Random(seed))

    return Challenger(
        name="baseline_wdl",
        label=f"Philidor baseline_wdl (Stockfish WDL depth={depth})",
        open_engines=open_engines,
        make_player=make_player,
    )


def lc0_contempt_challenger(nodes=LC0_CONTEMPT_NODES, draw_score=1.0):
    def open_engines(timeout):
        args = [
            lc0_path(),
            f"--weights={lczero_weights()}",
            "--backend=blas",
        ]
        options = {"DrawScore": f"{draw_score:.3f}", "UCI_ShowWDL": "true"}
        return [Engine(args, options, timeout=timeout)]

    def make_player(engines, seed):
        return EngineWrapper(engines[0], nodes=nodes)

    return Challenger(
        name="lc0_contempt",
        label=f"lc0 DrawScore={draw_score} (nodes={nodes})",
        open_engines=open_engines,
        make_player=make_player,
    )


CHALLENGERS = {
    "baseline_wdl": baseline_wdl_challenger,
    "lc0_contempt": lc0_contempt_challenger,
}


def challenger_by_name(name, **kwargs):
    if name not in CHALLENGERS:
        raise ValueError(f"unknown challenger {name}, pick from {sorted(CHALLENGERS)}")
    return CHALLENGERS[name](**kwargs)


def pgn_path(level, challenger_name):
    return GAMES_DIR / challenger_name / level.filename()


@dataclasses.dataclass
class GameSpec:
    index: int
    opening: object
    philidor_is_white: bool
    seed: int


class LevelRunner:
    def __init__(
        self, level, challenger, max_plies=None, timeout=ENGINE_TIMEOUT
    ):
        self.level = level
        self.challenger = challenger
        self.path = pgn_path(level, challenger.name)
        self.max_plies = max_plies
        self.timeout = timeout
        self.local = threading.local()
        self.engines = []
        self.engines_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.failures = []

    def _engines(self):
        cached = getattr(self.local, "engines", None)
        if cached is not None:
            challenger_engines, opponent_engine, opponent_kw = cached
            if opponent_engine.alive and all(e.alive for e in challenger_engines):
                return cached
            self._discard(cached)
        challenger_engines = self.challenger.open_engines(self.timeout)
        opponent_engine, opponent_kw = open_opponent_engine(self.level, self.timeout)
        cached = (challenger_engines, opponent_engine, opponent_kw)
        with self.engines_lock:
            self.engines.extend(challenger_engines)
            self.engines.append(opponent_engine)
        self.local.engines = cached
        return cached

    def _discard(self, cached):
        self.local.engines = None
        for engine in list(cached[0]) + [cached[1]]:
            with self.engines_lock:
                if engine in self.engines:
                    self.engines.remove(engine)
            try:
                engine.close()
            except Exception:
                pass

    def play(self, spec):
        challenger_engines, opponent_engine, opponent_kw = self._engines()
        bot = self.challenger.make_player(challenger_engines, spec.seed)
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
        names = (
            ",".join(engine.name for engine in challenger_engines),
            opponent_engine.name,
        )
        self._write(runner, spec, result, names)
        return result

    def _write(self, runner, spec, result, names):
        colour = "white" if spec.philidor_is_white else "black"
        label = opponent_label(self.level)
        mine = f"Philidor {self.challenger.name}"
        headers = {
            "Event": f"Philidor ladder {self.challenger.name}",
            "Site": "local",
            "Date": datetime.date.today().strftime("%Y.%m.%d"),
            "Round": spec.index + 1,
            "White": mine if spec.philidor_is_white else label,
            "Black": label if spec.philidor_is_white else mine,
            "PhilidorColor": colour,
            "PhilidorLevel": self.level.number,
            "Challenger": self.challenger.name,
            "ChallengerLabel": self.challenger.label,
            "Opponent": self.level.name,
            "PhilidorEngine": names[0],
            "OpponentEngine": names[1],
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
            self.path,
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


def run_level(
    level,
    challenger=None,
    games=100,
    workers=5,
    seed=0,
    max_plies=None,
    timeout=ENGINE_TIMEOUT,
    append=False,
    only_indices=None,
):
    challenger = challenger or baseline_wdl_challenger()
    path = pgn_path(level, challenger.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not append:
        path.unlink()
    specs = build_specs(level, games, seed)
    if only_indices is not None:
        wanted = set(only_indices)
        specs = [spec for spec in specs if spec.index in wanted]
        if not specs:
            raise ValueError(f"no specs match indices {sorted(wanted)}")
    runner = LevelRunner(
        level, challenger, max_plies=max_plies, timeout=timeout
    )
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
    parser.add_argument("--timeout", type=float, default=ENGINE_TIMEOUT)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--only-indices", default=None)
    parser.add_argument("--challenger", default="baseline_wdl")
    parser.add_argument("--nodes", type=int, default=LC0_CONTEMPT_NODES)
    parser.add_argument("--draw-score", type=float, default=1.0)
    args = parser.parse_args()

    only_indices = None
    if args.only_indices is not None:
        only_indices = [
            int(part) for part in args.only_indices.split(",") if part.strip()
        ]

    if args.challenger == "lc0_contempt":
        challenger = lc0_contempt_challenger(
            nodes=args.nodes, draw_score=args.draw_score
        )
    else:
        challenger = challenger_by_name(args.challenger, depth=args.depth)

    numbers = [int(part) for part in args.levels.split(",") if part.strip()]
    for number in numbers:
        level = level_by_number(number)
        total, failures = run_level(
            level,
            challenger=challenger,
            games=args.games,
            workers=args.workers,
            seed=args.seed,
            max_plies=args.max_plies,
            timeout=args.timeout,
            append=args.append,
            only_indices=only_indices,
        )
        print(
            f"level {level.number} {level.name} complete: "
            f"{total - len(failures)}/{total} games written to "
            f"{pgn_path(level, challenger.name)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
