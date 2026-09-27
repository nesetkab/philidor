import shutil

import chess.pgn
import pytest

from arena import ladder

STOCKFISH = shutil.which("stockfish")
requires_stockfish = pytest.mark.skipif(
    STOCKFISH is None, reason="stockfish not installed"
)


def test_five_levels_match_the_plan():
    assert [level.number for level in ladder.LEVELS] == [1, 2, 3, 4, 5]
    assert [level.kind for level in ladder.LEVELS] == [
        "maia",
        "maia",
        "maia",
        "stockfish",
        "stockfish",
    ]


def test_level_by_number_rejects_unknown_levels():
    assert ladder.level_by_number(3).name == "maia1900"
    with pytest.raises(ValueError):
        ladder.level_by_number(9)


def test_opponent_labels_describe_the_settings():
    assert ladder.opponent_label(ladder.level_by_number(1)) == "Maia 1100 (nodes=1)"
    assert (
        ladder.opponent_label(ladder.level_by_number(5)) == "Stockfish (depth=20)"
    )


def test_specs_pair_each_opening_with_both_colours():
    specs = ladder.build_specs(ladder.level_by_number(1), games=6, seed=0)
    assert len(specs) == 6
    for first, second in zip(specs[::2], specs[1::2]):
        assert first.opening == second.opening
        assert first.philidor_is_white is True
        assert second.philidor_is_white is False


def test_specs_have_unique_seeds():
    specs = ladder.build_specs(ladder.level_by_number(1), games=20, seed=0)
    assert len({spec.seed for spec in specs}) == len(specs)


def test_specs_are_reproducible_and_differ_between_levels():
    first = ladder.build_specs(ladder.level_by_number(1), games=10, seed=7)
    again = ladder.build_specs(ladder.level_by_number(1), games=10, seed=7)
    other = ladder.build_specs(ladder.level_by_number(2), games=10, seed=7)
    assert [spec.opening.pgn for spec in first] == [spec.opening.pgn for spec in again]
    assert [spec.opening.pgn for spec in first] != [spec.opening.pgn for spec in other]


def test_odd_game_counts_round_up_to_whole_pairs():
    specs = ladder.build_specs(ladder.level_by_number(1), games=5, seed=0)
    assert len(specs) == 6


def test_maia_weights_reject_an_unknown_rating():
    with pytest.raises(FileNotFoundError):
        ladder.maia_weights(1234)


@requires_stockfish
def test_run_level_writes_a_readable_pgn(tmp_path, monkeypatch):
    monkeypatch.setattr(ladder, "GAMES_DIR", tmp_path)
    level = ladder.level_by_number(4)
    total, failures = ladder.run_level(
        level, games=2, workers=2, seed=0, depth=4, max_plies=10
    )
    assert total == 2
    assert failures == []
    with open(level.pgn_path) as handle:
        games = []
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            games.append(game)
    assert len(games) == 2
    assert {game.headers["PhilidorColor"] for game in games} == {"white", "black"}
    for game in games:
        assert game.headers["PhilidorLevel"] == "4"
        assert game.headers["Opponent"] == "stockfish_d8"
        assert game.headers["Termination"]
        assert int(game.headers["TotalPlies"]) <= 10
        assert game.headers["ECO"]
