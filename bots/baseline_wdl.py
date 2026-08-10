import chess


class BaselineWDLBot:
    def __init__(self, engine, depth=None, movetime=None):
        self.engine = engine
        self.depth = depth
        self.movetime = movetime

    def select_move(self, board):
        moves = list(board.legal_moves)
        largest_d = -1
        best_move = None
        for move in moves:
            board.push(move)
            d = self.engine.analyze(
                board, depth=self.depth, movetime=self.movetime
            ).wdl[1]
            if d > largest_d:
                best_move = move
                largest_d = d
            board.pop()

        return best_move
