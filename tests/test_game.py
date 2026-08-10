import pytest
import shutil
import time
from arena.game import EngineWrapper, GameRunner
from board.fast_board import FastBoard
from engines.uci import Engine
from bots.baseline_wdl import BaselineWDLBot


def test_game():
    start = time.perf_counter()
    with Engine(shutil.which("stockfish"), {"UCI_ShowWDL": "true"}) as e:
        plyr1 = BaselineWDLBot(e, movetime=50)
        plyr2 = EngineWrapper(e, movetime=50)
        g = GameRunner(plyr1, plyr2)
        print(g.loop())
    end = time.perf_counter()
    elapsed = end - start
    print(f"{elapsed:.4f}")


test_game()
