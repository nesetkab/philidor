import random

DRAW_CERTAIN = 1000
DRAW_IMPOSSIBLE = -1


class BaselineWDLBot:
    def __init__(self, engine, depth=None, movetime=None, nodes=None, rng=None):
        self.engine = engine
        self.depth = depth
        self.movetime = movetime
        self.nodes = nodes
        self.rng = rng if rng is not None else random.Random()

    def _draw_score(self, board):
        if board.is_checkmate():
            return DRAW_IMPOSSIBLE
        if board.is_stalemate() or board.is_insufficient_material():
            return DRAW_CERTAIN
        if board.halfmove_clock >= 100 or board.is_repetition_fast(3):
            return DRAW_CERTAIN
        result = self.engine.analyze(
            board, depth=self.depth, movetime=self.movetime, nodes=self.nodes
        )
        if result.wdl is None:
            raise ValueError("engine reported no WDL, enable UCI_ShowWDL")
        return result.wdl[1]

    def select_move(self, board):
        best_score = None
        best_moves = []
        for move in list(board.legal_moves):
            board.push(move)
            try:
                score = self._draw_score(board)
            finally:
                board.pop()
            if best_score is None or score > best_score:
                best_score = score
                best_moves = [move]
            elif score == best_score:
                best_moves.append(move)
        if not best_moves:
            raise ValueError(f"no legal moves in {board.fen()}")
        return self.rng.choice(best_moves)
