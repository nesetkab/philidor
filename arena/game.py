from chess import IllegalMoveError
import chess
from board.fast_board import FastBoard


class GameRunner:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.board = FastBoard()

    def play_turn(self):
        if self.board.turn == chess.WHITE:
            move = self.player1.select_move(self.board)
        else:
            move = self.player2.select_move(self.board)
        if move not in self.board.legal_moves:
            raise IllegalMoveError(
                f"happend in arena. move: {move} - fen: {self.board.fen()}"
            )
        self.board.push(move)
        print(move)

    def loop(self):
        while (
            not self.board.is_game_over(claim_draw=True)
            or len(self.board.move_stack) > 300
        ):
            self.play_turn()
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
