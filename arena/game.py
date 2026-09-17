from chess import IllegalMoveError
import chess
from board.fast_board import FastBoard


class GameRunner:
    def __init__(self, philidor, engine, philidor_is_white=True):
        if philidor_is_white:
            self.white = philidor
            self.black = engine
        else:
            self.white = engine
            self.black = philidor
        self.board = FastBoard()

    def play_turn(self):
        if self.board.turn == chess.WHITE:
            move = self.white.select_move(self.board)
        else:
            move = self.black.select_move(self.board)
        if move not in self.board.legal_moves:
            raise IllegalMoveError(
                f"happend in arena. move: {move} - fen: {self.board.fen()}"
            )
        self.board.push(move)
        print(move)

    def loop(self):
        while (
            not self.board.is_game_over(claim_draw=True)
            and len(self.board.move_stack) < 300
        ):
            self.play_turn()
        print(f"moves {len(self.board.move_stack)}")
        return self.board.result(claim_draw=True)


class EngineWrapper:
    def __init__(self, engine, depth=None, movetime=None):
        self.engine = engine
        self.depth = depth
        self.movetime = movetime

    def select_move(self, board):
        return self.engine.analyze(
            board, depth=self.depth, movetime=self.movetime
        ).bestmove
