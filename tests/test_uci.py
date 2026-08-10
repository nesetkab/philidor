import pytest
import chess
from engines.uci import Engine
import shutil

path = shutil.which("stockfish")


@pytest.mark.skipif(path is None, reason="stockfish not installed !")
def test_analyze_startpos():
    with Engine(path, {"UCI_ShowWDL": "true"}) as e:
        board = chess.Board()
        result = e.analyze(board, depth=10)
        assert result.wdl is not None
        assert sum(result.wdl) == 1000
        assert result.bestmove in board.legal_moves


@pytest.mark.skipif(path is None, reason="stockfish not installed !")
def test_wdl_perspective():
    FEN_W = "4k3/8/8/8/8/8/Q7/4K3 w - - 0 1"
    FEN_B = "4k3/8/8/8/8/8/Q7/4K3 b - - 0 1"
    with Engine(path, {"UCI_ShowWDL": "true"}) as e:
        w = e.analyze(chess.Board(FEN_W), depth=16).wdl
        b = e.analyze(chess.Board(FEN_B), depth=16).wdl
        assert w is not None
        assert b is not None
        assert w[0] > b[0] and b[2] > w[2]
