import random
import shutil

import chess.pgn
import pytest

from arena import book
from arena.game import (
    EngineWrapper,
    GameRunner,
    classify_termination,
    game_result,
    is_finished,
)
from arena.pgn import write_game
from board.fast_board import FastBoard
from bots.baseline_wdl import BaselineWDLBot
from engines.uci import Engine

STOCKFISH = shutil.which("stockfish")
requires_stockfish = pytest.mark.skipif(
    STOCKFISH is None, reason="stockfish not installed"
)


class FirstMoveBot:
    def select_move(self, board):
        return sorted(board.legal_moves, key=lambda move: move.uci())[0]


def test_opening_is_applied_before_play():
    opening = book.random_opening(random.Random(5))
    runner = GameRunner(FirstMoveBot(), FirstMoveBot(), opening=opening)
    assert runner.opening_plies == len(opening.moves)
    assert len(runner.board.move_stack) == len(opening.moves)


def test_ply_cap_stops_the_game():
    runner = GameRunner(FirstMoveBot(), FirstMoveBot(), max_plies=12)
    result = runner.loop()
    assert len(runner.board.move_stack) <= 12
    assert result in ("1-0", "0-1", "1/2-1/2", "*")


def test_philidor_colour_selects_the_right_player():
    white_runner = GameRunner("philidor", "opponent", philidor_is_white=True)
    assert white_runner.player_to_move() == "philidor"
    black_runner = GameRunner("philidor", "opponent", philidor_is_white=False)
    assert black_runner.player_to_move() == "opponent"


def test_classify_termination_detects_stalemate():
    board = FastBoard("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert board.is_stalemate()
    assert classify_termination(board) == "stalemate"


def test_classify_termination_detects_ply_cap():
    board = FastBoard()
    board.push_san("e4")
    assert classify_termination(board, max_plies=1) == "ply_cap"


SHUFFLE = ("Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1", "Ng8")


def test_threefold_finishes_only_on_the_third_occurrence():
    board = FastBoard()
    for san in SHUFFLE[:-1]:
        board.push_san(san)
        assert not is_finished(board)
    board.push_san(SHUFFLE[-1])
    assert is_finished(board)
    assert game_result(board) == "1/2-1/2"
    assert classify_termination(board) == "threefold_repetition"


def test_a_claimable_repetition_one_move_away_is_not_finished():
    board = FastBoard()
    for san in SHUFFLE[:-1]:
        board.push_san(san)
    assert board.can_claim_threefold_repetition()
    assert not is_finished(board)
    assert game_result(board) == "*"


def test_fifty_move_rule_finishes_the_game():
    board = FastBoard("8/8/4k3/8/8/4K3/8/R7 w - - 100 80")
    assert not board.is_insufficient_material()
    assert is_finished(board)
    assert game_result(board) == "1/2-1/2"
    assert classify_termination(board) == "fifty_move_rule"


def test_checkmate_finishes_with_a_decisive_result():
    board = FastBoard()
    for san in ("f3", "e5", "g4", "Qh4#"):
        board.push_san(san)
    assert is_finished(board)
    assert game_result(board) == "0-1"
    assert classify_termination(board) == "checkmate"


def test_write_game_round_trips_headers(tmp_path):
    board = FastBoard()
    for san in ("e4", "e5", "Nf3", "Nc6"):
        board.push_san(san)
    path = tmp_path / "games.pgn"
    write_game(board, "1/2-1/2", path, headers={"PhilidorColor": "white", "ECO": "C44"})
    write_game(board, "1-0", path, headers={"PhilidorColor": "black", "ECO": "C44"})
    with open(path) as handle:
        first = chess.pgn.read_game(handle)
        second = chess.pgn.read_game(handle)
        assert chess.pgn.read_game(handle) is None
    assert first.headers["Result"] == "1/2-1/2"
    assert first.headers["PhilidorColor"] == "white"
    assert second.headers["Result"] == "1-0"
    assert len(list(first.mainline_moves())) == 4


@requires_stockfish
def test_short_game_between_bot_and_engine(tmp_path):
    with Engine(STOCKFISH, {"UCI_ShowWDL": "true"}) as engine:
        bot = BaselineWDLBot(engine, depth=4, rng=random.Random(0))
        opponent = EngineWrapper(engine, depth=4)
        runner = GameRunner(bot, opponent, max_plies=8)
        result = runner.loop()
    assert result in ("1-0", "0-1", "1/2-1/2", "*")
    assert len(runner.board.move_stack) == 8
    write_game(runner.board, result, tmp_path / "out.pgn")


@requires_stockfish
def test_bot_takes_an_available_stalemate():
    board = FastBoard("7k/5Q2/8/8/8/8/8/6K1 w - - 0 1")
    with Engine(STOCKFISH, {"UCI_ShowWDL": "true"}) as engine:
        bot = BaselineWDLBot(engine, depth=4, rng=random.Random(0))
        move = bot.select_move(board)
    board.push(move)
    assert board.is_stalemate()


@requires_stockfish
def test_bot_avoids_delivering_checkmate():
    board = FastBoard("7k/5Q2/8/8/8/8/8/R5K1 w - - 0 1")
    with Engine(STOCKFISH, {"UCI_ShowWDL": "true"}) as engine:
        bot = BaselineWDLBot(engine, depth=4, rng=random.Random(0))
        move = bot.select_move(board)
    board.push(move)
    assert not board.is_checkmate()
