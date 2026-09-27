import collections
import dataclasses
import math
import pathlib
import statistics

import chess.pgn

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAMES_DIR = ROOT / "games"
Z_95 = 1.959963984540054


def wilson_interval(successes, total, z=Z_95):
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return ((centre - spread) / denominator, (centre + spread) / denominator)


def read_games(path):
    with open(path) as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                return
            yield game


def outcome(game):
    result = game.headers.get("Result", "*")
    colour = game.headers.get("PhilidorColor", "")
    if result == "*":
        return "unfinished"
    if result == "1/2-1/2":
        return "draw"
    if (result == "1-0") == (colour == "white"):
        return "win"
    return "loss"


def _as_int(game, key):
    try:
        return int(game.headers.get(key, ""))
    except ValueError:
        return None


@dataclasses.dataclass
class LevelSummary:
    number: int
    name: str
    total: int
    counts: collections.Counter
    terminations: collections.Counter
    by_colour: dict
    plies: list
    halfmove_clocks: list
    setups: collections.Counter

    @property
    def draw_rate(self):
        return self.counts["draw"] / self.total if self.total else 0.0

    @property
    def interval(self):
        return wilson_interval(self.counts["draw"], self.total)

    def rate(self, key):
        return self.counts[key] / self.total if self.total else 0.0

    def colour_rate(self, colour):
        played = self.by_colour[colour]["total"]
        if not played:
            return None
        return self.by_colour[colour]["draw"] / played


def summarise(path, number, name):
    counts = collections.Counter()
    terminations = collections.Counter()
    by_colour = {
        "white": collections.Counter({"total": 0, "draw": 0}),
        "black": collections.Counter({"total": 0, "draw": 0}),
    }
    plies = []
    clocks = []
    setups = collections.Counter()
    for game in read_games(path):
        kind = outcome(game)
        counts[kind] += 1
        setups[
            (
                game.headers.get("PhilidorEngine", "unknown"),
                game.headers.get("OpponentEngine", "unknown"),
                game.headers.get("PhilidorDepth", "?"),
            )
        ] += 1
        terminations[game.headers.get("Termination", "unknown")] += 1
        colour = game.headers.get("PhilidorColor", "")
        if colour in by_colour:
            by_colour[colour]["total"] += 1
            if kind == "draw":
                by_colour[colour]["draw"] += 1
        total_plies = _as_int(game, "TotalPlies")
        if total_plies is not None:
            plies.append(total_plies)
        clock = _as_int(game, "FinalHalfmoveClock")
        if clock is not None:
            clocks.append(clock)
    return LevelSummary(
        number=number,
        name=name,
        total=sum(counts.values()),
        counts=counts,
        terminations=terminations,
        by_colour=by_colour,
        plies=plies,
        halfmove_clocks=clocks,
        setups=setups,
    )


def collect(levels):
    summaries = []
    for level in levels:
        if not level.pgn_path.exists():
            continue
        summaries.append(summarise(level.pgn_path, level.number, level.name))
    return summaries


def _percent(value):
    return f"{value * 100:.1f}%"


def _median(values):
    return f"{statistics.median(values):.0f}" if values else "-"


def render(summaries, labels):
    lines = []
    lines.append("# Philidor phase one: baseline draw rates")
    lines.append("")
    lines.append(
        "Bot: `bots/baseline_wdl.py`. For every legal move it queries Stockfish "
        "WDL one ply ahead and plays the move with the highest draw probability. "
        "No search, no learning."
    )
    lines.append("")
    lines.append(
        "Draw rate denominators include every game played, so unfinished games "
        "at the ply cap count against the rate rather than being dropped."
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Level | Opponent | N | Draw | Win | Loss | Unfinished | Draw rate | 95% Wilson CI |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for summary in summaries:
        low, high = summary.interval
        lines.append(
            f"| {summary.number} "
            f"| {labels.get(summary.number, summary.name)} "
            f"| {summary.total} "
            f"| {summary.counts['draw']} "
            f"| {summary.counts['win']} "
            f"| {summary.counts['loss']} "
            f"| {summary.counts['unfinished']} "
            f"| {_percent(summary.draw_rate)} "
            f"| {_percent(low)} to {_percent(high)} |"
        )
    lines.append("")
    lines.append("## Draw rate by colour")
    lines.append("")
    lines.append("| Level | As white | As black |")
    lines.append("|---|---|---|")
    for summary in summaries:
        white = summary.colour_rate("white")
        black = summary.colour_rate("black")
        lines.append(
            f"| {summary.number} "
            f"| {_percent(white) if white is not None else '-'} "
            f"| {_percent(black) if black is not None else '-'} |"
        )
    lines.append("")
    lines.append("## Game length and terminations")
    lines.append("")
    lines.append("| Level | Median plies | Median final halfmove clock | Terminations |")
    lines.append("|---|---|---|---|")
    for summary in summaries:
        breakdown = ", ".join(
            f"{name} {count}" for name, count in summary.terminations.most_common()
        )
        lines.append(
            f"| {summary.number} "
            f"| {_median(summary.plies)} "
            f"| {_median(summary.halfmove_clocks)} "
            f"| {breakdown or '-'} |"
        )
    lines.append("")
    lines.append("## Engines")
    lines.append("")
    lines.append("| Level | Philidor engine | Philidor depth | Opponent engine |")
    lines.append("|---|---|---|---|")
    for summary in summaries:
        if not summary.setups:
            continue
        philidor, opponent, depth = summary.setups.most_common(1)[0][0]
        lines.append(
            f"| {summary.number} | {philidor} | {depth} | {opponent} |"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    import argparse

    from arena.ladder import LEVELS, opponent_label

    parser = argparse.ArgumentParser(description="Report Philidor baseline draw rates")
    parser.add_argument("--out", default=str(GAMES_DIR / "report.md"))
    args = parser.parse_args()

    summaries = collect(LEVELS)
    if not summaries:
        print(f"no PGN files found in {GAMES_DIR}")
        return
    labels = {level.number: opponent_label(level) for level in LEVELS}
    text = render(summaries, labels)
    print(text)
    pathlib.Path(args.out).write_text(text + "\n")
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
