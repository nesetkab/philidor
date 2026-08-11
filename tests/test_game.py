import pytest
import shutil
import time
from arena.game import EngineWrapper, GameRunner
from arena.pgn import write_game
from board.fast_board import FastBoard
from engines.uci import Engine
from bots.baseline_wdl import BaselineWDLBot


def test_game():
    with Engine(shutil.which("stockfish"), {"UCI_ShowWDL": "true"}) as e:
        plyr1 = BaselineWDLBot(e, movetime=50)
        plyr2 = EngineWrapper(e, movetime=50)
        g = GameRunner(plyr1, plyr2)
        result = g.loop()
        assert result is not None
        write_game(g.board, result, "pgn.txt")
