import csv
import dataclasses
import pathlib
import random

import chess

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENINGS_DIR = ROOT / "data" / "openings"
BALANCED_PATH = ROOT / "data" / "balanced_openings.tsv"

MIN_PLY = 6
MAX_PLY = 12
BALANCE_CP = 50
BALANCE_DEPTH = 12


@dataclasses.dataclass(frozen=True)
class Opening:
    eco: str
    name: str
    pgn: str
    moves: tuple[str, ...]

    def apply(self, board):
        for san in self.moves:
            board.push_san(san)


def _parse_row(row):
    moves = tuple(tok for tok in row["pgn"].split() if not tok.endswith("."))
    return Opening(eco=row["eco"], name=row["name"], pgn=row["pgn"], moves=moves)


def _read_tsv(path):
    with open(path, newline="") as fh:
        return [_parse_row(row) for row in csv.DictReader(fh, delimiter="\t")]


def load_all():
    openings = []
    for path in sorted(OPENINGS_DIR.glob("openings_*.tsv")):
        openings.extend(_read_tsv(path))
    if not openings:
        raise FileNotFoundError(f"no opening files in {OPENINGS_DIR}")
    return openings


def load_book(min_ply=MIN_PLY, max_ply=MAX_PLY):
    if BALANCED_PATH.exists():
        openings = _read_tsv(BALANCED_PATH)
    else:
        openings = load_all()
    return [o for o in openings if min_ply <= len(o.moves) <= max_ply]


def random_opening(rng=None, book=None):
    rng = rng or random.Random()
    book = book if book is not None else load_book()
    return rng.choice(book)


def _evaluate(engine, opening):
    board = chess.Board()
    opening.apply(board)
    if board.is_game_over():
        return None
    return engine.analyze(board, depth=BALANCE_DEPTH)


def build_balanced(engine, limit_cp=BALANCE_CP, progress_every=100):
    candidates = [o for o in load_all() if MIN_PLY <= len(o.moves) <= MAX_PLY]
    kept = []
    for i, opening in enumerate(candidates, 1):
        try:
            result = _evaluate(engine, opening)
        except (ValueError, chess.IllegalMoveError):
            continue
        if result is None or result.mate_in is not None or result.score_cp is None:
            continue
        if abs(result.score_cp) <= limit_cp:
            kept.append(opening)
        if i % progress_every == 0:
            print(f"{i}/{len(candidates)} scanned, {len(kept)} kept", flush=True)
    return kept


def write_book(openings, path=BALANCED_PATH):
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["eco", "name", "pgn"])
        for o in openings:
            writer.writerow([o.eco, o.name, o.pgn])


if __name__ == "__main__":
    import shutil

    from engines.uci import Engine

    with Engine(shutil.which("stockfish"), {}) as engine:
        kept = build_balanced(engine)
    write_book(kept)
    print(f"wrote {len(kept)} balanced openings to {BALANCED_PATH}")
