import chess

from board.fast_board import FastBoard

MAX_PLIES = 300


def is_finished(board):
    if board.is_game_over():
        return True
    if board.halfmove_clock >= 100:
        return True
    return board.is_repetition_fast(3)


def game_result(board):
    result = board.result()
    if result != "*":
        return result
    if board.halfmove_clock >= 100 or board.is_repetition_fast(3):
        return "1/2-1/2"
    return "*"


def classify_termination(board, max_plies=MAX_PLIES):
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient_material"
    if board.is_fivefold_repetition():
        return "fivefold_repetition"
    if board.is_seventyfive_moves():
        return "seventyfive_moves"
    if board.is_repetition(3):
        return "threefold_repetition"
    if board.halfmove_clock >= 100:
        return "fifty_move_rule"
    if len(board.move_stack) >= max_plies:
        return "ply_cap"
    return "unknown"


class GameRunner:
    def __init__(
        self,
        philidor,
        opponent,
        philidor_is_white=True,
        opening=None,
        max_plies=MAX_PLIES,
    ):
        self.philidor = philidor
        self.opponent = opponent
        self.philidor_is_white = philidor_is_white
        self.max_plies = max_plies
        self.opening = opening
        self.board = FastBoard()
        if opening is not None:
            opening.apply(self.board)
        self.opening_plies = len(self.board.move_stack)

    def player_to_move(self):
        if (self.board.turn == chess.WHITE) == self.philidor_is_white:
            return self.philidor
        return self.opponent

    def play_turn(self):
        move = self.player_to_move().select_move(self.board)
        if move not in self.board.legal_moves:
            raise chess.IllegalMoveError(
                f"illegal move {move} for position {self.board.fen()}"
            )
        self.board.push(move)

    def loop(self):
        while (
            not is_finished(self.board)
            and len(self.board.move_stack) < self.max_plies
        ):
            self.play_turn()
        return game_result(self.board)

    def termination(self):
        return classify_termination(self.board, self.max_plies)


class EngineWrapper:
    def __init__(self, engine, depth=None, movetime=None, nodes=None):
        self.engine = engine
        self.depth = depth
        self.movetime = movetime
        self.nodes = nodes

    def select_move(self, board):
        return self.engine.analyze(
            board, depth=self.depth, movetime=self.movetime, nodes=self.nodes
        ).bestmove
