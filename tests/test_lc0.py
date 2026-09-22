import os
import shutil

import chess
import pytest

from engines.uci import Engine

LC0 = shutil.which("lc0")
WEIGHTS = os.path.expanduser("~/lc0-weights/maia/maia-1100.pb.gz")
path = [LC0, f"--weights={WEIGHTS}", "--backend=blas"]

requires_maia = pytest.mark.skipif(
    LC0 is None or not os.path.exists(WEIGHTS),
    reason="lc0 or Maia weights not installed",
)


@requires_maia
def test_maia_returns_legal_move():
    board = chess.Board()
    with Engine(path, {}, timeout=30.0) as e:
        result = e.analyze(board, nodes=1)
    assert result.bestmove in board.legal_moves


@requires_maia
def test_maia_reports_no_wdl():
    with Engine(path, {}, timeout=30.0) as e:
        result = e.analyze(chess.Board(), nodes=1)
    assert result.wdl is None


@requires_maia
def test_maia_is_deterministic():
    board = chess.Board()
    with Engine(path, {}, timeout=30.0) as e:
        first = e.analyze(board, nodes=1).bestmove
        second = e.analyze(board, nodes=1).bestmove
    assert first == second
