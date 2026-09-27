import collections
import dataclasses
import math
import pathlib
import statistics

import chess.pgn

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAMES_DIR = ROOT / "games"
REPORTS_DIR = ROOT / "reports"
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


def intervals_overlap(first, second):
    return first[0] <= second[1] and second[0] <= first[1]


def shuffle_count(summary):
    return summary.terminations["fifty_move_rule"] + summary.terminations["ply_cap"]


def findings(summaries, labels):
    lines = []
    if not summaries:
        return lines
    games = sum(summary.total for summary in summaries)
    wins = sum(summary.counts["win"] for summary in summaries)
    lowest = min(summaries, key=lambda summary: summary.draw_rate)
    highest = max(summaries, key=lambda summary: summary.draw_rate)
    lines.append(f"- The bot won {wins} of {games} games.")
    lines.append(
        f"- Lowest draw rate is level {lowest.number}, "
        f"{labels.get(lowest.number, lowest.name)}, at {_percent(lowest.draw_rate)}."
    )
    lines.append(
        f"- Highest draw rate is level {highest.number}, "
        f"{labels.get(highest.number, highest.name)}, at {_percent(highest.draw_rate)}."
    )
    if lowest is not highest:
        if intervals_overlap(lowest.interval, highest.interval):
            lines.append(
                "- Those two Wilson intervals overlap, so this sample does not "
                "separate them."
            )
        else:
            lines.append(
                "- Those two Wilson intervals do not overlap, so the gap is "
                "larger than sampling noise at this sample size."
            )
    ordered = sorted(summaries, key=lambda summary: summary.number)
    ends = (ordered[0].number, ordered[-1].number)
    if len(ordered) >= 3 and highest.number not in ends:
        lines.append(
            f"- The peak is an interior level, so both the weakest and the "
            f"strongest opponent on this ladder draw less often than level "
            f"{highest.number}. The objective is hard at both ends, not simply "
            f"harder as the opponent gets stronger."
        )
    worst = max(summaries, key=shuffle_count)
    lines.append(
        f"- Games ending by the fifty-move rule or the ply cap, which is the "
        f"shuffling signature, peak at level {worst.number} with "
        f"{shuffle_count(worst)} of {worst.total}."
    )
    return lines


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
    lines.append("## Method")
    lines.append("")
    lines.append(
        "- Openings come from `data/balanced_openings.tsv`, the 1167 ECO lines of "
        "6 to 12 plies that Stockfish scores within 50 centipawns at depth 12."
    )
    lines.append(
        "- Every opening is played twice, once with Philidor as white and once as "
        "black, so colour advantage cannot skew a level."
    )
    lines.append(
        "- A draw is adjudicated only when a threefold repetition or the "
        "fifty-move rule has actually been reached. python-chess reports a "
        "claimable draw one move early, which would score a position as drawn "
        "even when the side to move is winning and would never repeat."
    )
    lines.append(
        "- Games are capped at 300 plies. A capped game is recorded as unfinished "
        "and stays in the denominator, so it counts against the draw rate rather "
        "than being dropped."
    )
    lines.append(
        "- Win and loss are read from the Philidor side, not from white."
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
    lines.append("## Findings")
    lines.append("")
    lines.extend(findings(summaries, labels))
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
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```")
    lines.append("python -m arena.book")
    lines.append("python -m arena.ladder --games 100 --workers 6 --seed 0 --depth 10")
    lines.append("python -m eval.report")
    lines.append("```")
    lines.append("")
    lines.append(
        "The first command regenerates the balanced book and is only needed if "
        "`data/balanced_openings.tsv` is missing."
    )
    lines.append("")
    return "\n".join(lines)


def main():
    import argparse

    from arena.ladder import LEVELS, opponent_label

    parser = argparse.ArgumentParser(description="Report Philidor baseline draw rates")
    parser.add_argument("--out", default=str(REPORTS_DIR / "phase1.md"))
    args = parser.parse_args()

    summaries = collect(LEVELS)
    if not summaries:
        print(f"no PGN files found in {GAMES_DIR}")
        return
    labels = {level.number: opponent_label(level) for level in LEVELS}
    text = render(summaries, labels)
    print(text)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
