import chess, chess.polyglot


class FastBoard(chess.Board):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._hashes = [chess.polyglot.zobrist_hash(self)]

    def push(self, move):
        super().push(move)
        self._hashes.append(chess.polyglot.zobrist_hash(self))

    def pop(self):
        self._hashes.pop()
        return super().pop()

    def is_repetition_fast(self, count=3):
        h, seen = self._hashes[-1], 0
        lo = max(-1, len(self._hashes) - self.halfmove_clock - 2)
        for i in range(len(self._hashes) - 1, lo, -2):
            if self._hashes[i] == h:
                seen += 1
                if seen >= count:
                    return True
        return False
