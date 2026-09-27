import dataclasses

import chess.pgn

TIME_CONTROL_BOUNDS = (
    ("ultrabullet", 30),
    ("bullet", 180),
    ("blitz", 480),
    ("rapid", 1500),
)
CORRESPONDENCE = "correspondence"
CLASSICAL = "classical"
CATEGORIES = [name for name, _ in TIME_CONTROL_BOUNDS] + [CLASSICAL, CORRESPONDENCE]


def estimated_seconds(time_control):
    if time_control in ("-", "", None):
        return None
    base, _, increment = time_control.partition("+")
    try:
        return int(base) + 40 * int(increment or 0)
    except ValueError:
        return None


def classify_time_control(time_control):
    seconds = estimated_seconds(time_control)
    if seconds is None:
        return CORRESPONDENCE
    for name, bound in TIME_CONTROL_BOUNDS:
        if seconds < bound:
            return name
    return CLASSICAL


def parse_elo(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclasses.dataclass(frozen=True)
class GameFilter:
    min_elo: int = 0
    max_elo: int = 4000
    time_controls: tuple = ("blitz", "rapid", "classical")
    min_ply: int = 10
    require_termination: tuple = ("Normal",)
    both_players_in_band: bool = True

    def rejects(self, headers):
        white = parse_elo(headers.get("WhiteElo"))
        black = parse_elo(headers.get("BlackElo"))
        if white is None or black is None:
            return "missing_elo"
        elos = [white, black] if self.both_players_in_band else [max(white, black)]
        if any(elo < self.min_elo or elo > self.max_elo for elo in elos):
            return "elo_out_of_band"
        category = classify_time_control(headers.get("TimeControl"))
        if category not in self.time_controls:
            return "time_control"
        if headers.get("Result") not in ("1-0", "0-1", "1/2-1/2"):
            return "unfinished"
        if self.require_termination:
            termination = headers.get("Termination", "Normal")
            if termination not in self.require_termination:
                return "termination"
        return None


@dataclasses.dataclass
class GameRecord:
    white_elo: int
    black_elo: int
    result: str
    time_control: str
    category: str
    eco: str
    moves: list


class FilteringVisitor(chess.pgn.BaseVisitor):
    def __init__(self, game_filter):
        self.game_filter = game_filter
        self.headers = None
        self.moves = None
        self.rejected = None
        self.saw_game = False
        self.counts = {}

    def begin_game(self):
        self.saw_game = True
        self.headers = {}
        self.moves = []
        self.rejected = None

    def visit_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        self.rejected = self.game_filter.rejects(self.headers)
        if self.rejected is not None:
            self.counts[self.rejected] = self.counts.get(self.rejected, 0) + 1
            return chess.pgn.SKIP
        return None

    def visit_move(self, board, move):
        self.moves.append(move.uci())

    def handle_error(self, error):
        self.rejected = "parse_error"
        self.counts["parse_error"] = self.counts.get("parse_error", 0) + 1

    def result(self):
        if self.rejected is not None or self.headers is None:
            return None
        if len(self.moves) < self.game_filter.min_ply:
            self.counts["too_short"] = self.counts.get("too_short", 0) + 1
            return None
        return GameRecord(
            white_elo=parse_elo(self.headers.get("WhiteElo")),
            black_elo=parse_elo(self.headers.get("BlackElo")),
            result=self.headers["Result"],
            time_control=self.headers.get("TimeControl", "-"),
            category=classify_time_control(self.headers.get("TimeControl")),
            eco=self.headers.get("ECO", ""),
            moves=self.moves,
        )


def iter_games(handle, game_filter, limit=None, skip=0, on_scanned=None):
    visitor = FilteringVisitor(game_filter)

    def factory():
        return visitor

    scanned = 0
    accepted = 0
    while True:
        visitor.saw_game = False
        record = chess.pgn.read_game(handle, Visitor=factory)
        if not visitor.saw_game:
            break
        scanned += 1
        if on_scanned is not None:
            on_scanned(scanned, accepted, visitor.counts)
        if scanned <= skip:
            continue
        if record is not None:
            accepted += 1
            yield record
            if limit is not None and accepted >= limit:
                break
