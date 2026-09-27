import pytest

from arena.pgn import write_game
from board.fast_board import FastBoard
from eval import report


def test_wilson_interval_matches_known_values():
    low, high = report.wilson_interval(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-4)
    assert high == pytest.approx(0.5962, abs=1e-4)


def test_wilson_interval_handles_zero_successes():
    low, high = report.wilson_interval(0, 10)
    assert low == pytest.approx(0.0, abs=1e-9)
    assert high == pytest.approx(0.2775, abs=1e-4)


def test_wilson_interval_handles_no_games():
    assert report.wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_interval_narrows_as_games_increase():
    small = report.wilson_interval(5, 10)
    large = report.wilson_interval(500, 1000)
    assert (small[1] - small[0]) > (large[1] - large[0])


class FakeGame:
    def __init__(self, result, colour):
        self.headers = {"Result": result, "PhilidorColor": colour}


@pytest.mark.parametrize(
    "result,colour,expected",
    [
        ("1/2-1/2", "white", "draw"),
        ("1/2-1/2", "black", "draw"),
        ("1-0", "white", "win"),
        ("1-0", "black", "loss"),
        ("0-1", "white", "loss"),
        ("0-1", "black", "win"),
        ("*", "white", "unfinished"),
        ("*", "black", "unfinished"),
    ],
)
def test_outcome_is_read_from_the_philidor_side(result, colour, expected):
    assert report.outcome(FakeGame(result, colour)) == expected


def _sample_pgn(path):
    board = FastBoard()
    for san in ("e4", "e5", "Nf3", "Nc6"):
        board.push_san(san)
    rows = [
        ("1/2-1/2", "white", "threefold_repetition", 120, 40),
        ("1/2-1/2", "black", "fifty_move_rule", 200, 100),
        ("0-1", "white", "checkmate", 60, 3),
        ("1-0", "white", "checkmate", 55, 1),
        ("*", "black", "ply_cap", 300, 80),
    ]
    for result, colour, termination, plies, clock in rows:
        write_game(
            board,
            result,
            path,
            headers={
                "PhilidorColor": colour,
                "Termination": termination,
                "TotalPlies": plies,
                "FinalHalfmoveClock": clock,
            },
        )


def test_summarise_counts_every_outcome(tmp_path):
    path = tmp_path / "level1.pgn"
    _sample_pgn(path)
    summary = report.summarise(path, 1, "maia1100")
    assert summary.total == 5
    assert summary.counts["draw"] == 2
    assert summary.counts["loss"] == 1
    assert summary.counts["win"] == 1
    assert summary.counts["unfinished"] == 1
    assert summary.draw_rate == pytest.approx(0.4)
    assert summary.terminations["checkmate"] == 2


def test_summarise_splits_by_colour(tmp_path):
    path = tmp_path / "level1.pgn"
    _sample_pgn(path)
    summary = report.summarise(path, 1, "maia1100")
    assert summary.by_colour["white"]["total"] == 3
    assert summary.colour_rate("white") == pytest.approx(1 / 3)
    assert summary.colour_rate("black") == pytest.approx(0.5)


def test_summarise_collects_length_statistics(tmp_path):
    path = tmp_path / "level1.pgn"
    _sample_pgn(path)
    summary = report.summarise(path, 1, "maia1100")
    assert sorted(summary.plies) == [55, 60, 120, 200, 300]
    assert sorted(summary.halfmove_clocks) == [1, 3, 40, 80, 100]


def test_render_includes_rates_and_terminations(tmp_path):
    path = tmp_path / "level1.pgn"
    _sample_pgn(path)
    summary = report.summarise(path, 1, "maia1100")
    text = report.render([summary], {1: "Maia 1100 (nodes=1)"})
    assert "Maia 1100 (nodes=1)" in text
    assert "40.0%" in text
    assert "threefold_repetition 1" in text
    assert "Draw rate by colour" in text


def test_summarise_records_engine_provenance(tmp_path):
    board = FastBoard()
    board.push_san("e4")
    path = tmp_path / "level1.pgn"
    write_game(
        board,
        "1/2-1/2",
        path,
        headers={
            "PhilidorColor": "white",
            "PhilidorEngine": "Stockfish 18",
            "OpponentEngine": "Lc0 v0.32.1",
            "PhilidorDepth": 10,
        },
    )
    summary = report.summarise(path, 1, "maia1100")
    assert summary.setups[("Stockfish 18", "Lc0 v0.32.1", "10")] == 1
    text = report.render([summary], {1: "Maia 1100 (nodes=1)"})
    assert "## Engines" in text
    assert "Lc0 v0.32.1" in text
