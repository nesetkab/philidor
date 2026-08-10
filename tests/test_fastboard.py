import chess, chess.polyglot
import pytest
import random

from board.fast_board import FastBoard


def test_basic():
    b = FastBoard()
    h = len(b._hashes)
    b.push_san("e4")
    assert len(b._hashes) - h == 1
    assert b._hashes[-1] == chess.polyglot.zobrist_hash(b)


def test_repetition():
    b = FastBoard()
    moves = ["Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1", "Ng8"]
    i = 0
    for move in moves:
        b.push_san(move)
        i += 1
        if i < 8:
            assert not b.is_repetition_fast(3)
        else:
            assert b.is_repetition_fast(3)


@pytest.mark.parametrize("_", range(10))
def test_random(_):
    b = FastBoard()
    rng = random.Random(12345)
    while not b.is_game_over():
        b.push(rng.choice(list(b.legal_moves)))
        assert b.is_repetition_fast(3) == b.is_repetition(3)
