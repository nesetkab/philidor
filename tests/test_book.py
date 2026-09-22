import random

import chess
import pytest

from arena import book
from board.fast_board import FastBoard


def test_all_openings_are_legal():
    for opening in book.load_all():
        board = chess.Board()
        opening.apply(board)
        assert len(board.move_stack) == len(opening.moves)


def test_band_respects_ply_bounds():
    for opening in book.load_book():
        assert book.MIN_PLY <= len(opening.moves) <= book.MAX_PLY


def test_band_is_not_empty():
    assert len(book.load_book()) > 100


def test_random_opening_is_reproducible():
    b = book.load_book()
    first = book.random_opening(random.Random(7), b)
    second = book.random_opening(random.Random(7), b)
    assert first == second


def test_apply_keeps_fast_board_hashes_in_step():
    opening = book.random_opening(random.Random(3))
    board = FastBoard()
    opening.apply(board)
    assert len(board._hashes) == len(opening.moves) + 1
    assert not board.is_repetition_fast(3)


@pytest.mark.skipif(
    not book.BALANCED_PATH.exists(), reason="balanced book not generated yet"
)
def test_balanced_book_is_a_subset():
    balanced = {o.pgn for o in book._read_tsv(book.BALANCED_PATH)}
    everything = {o.pgn for o in book.load_all()}
    assert balanced
    assert balanced <= everything
