import json
import pathlib

import chess
import numpy as np

PIECE_ORDER = (
    chess.PAWN,
    chess.KNIGHT,
    chess.BISHOP,
    chess.ROOK,
    chess.QUEEN,
    chess.KING,
)
PLANES = 18
PROMOTION_ORDER = (None, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
RESULT_LOSS, RESULT_DRAW, RESULT_WIN = 0, 1, 2

FIELDS = {
    "bitboards": ("uint64", (12,)),
    "castling": ("uint8", ()),
    "ep_file": ("int8", ()),
    "halfmove": ("uint8", ()),
    "from_to": ("uint16", ()),
    "promotion": ("uint8", ()),
    "value": ("uint8", ()),
    "own_elo": ("uint16", ()),
    "opp_elo": ("uint16", ()),
    "ply": ("uint16", ()),
}


def orient(board):
    return board if board.turn == chess.WHITE else board.mirror()


def orient_square(square, flipped):
    return chess.square_mirror(square) if flipped else square


def encode_board(board):
    flipped = board.turn == chess.BLACK
    view = orient(board)
    bitboards = np.zeros(12, dtype=np.uint64)
    for index, piece in enumerate(PIECE_ORDER):
        bitboards[index] = np.uint64(int(view.pieces_mask(piece, chess.WHITE)))
        bitboards[index + 6] = np.uint64(int(view.pieces_mask(piece, chess.BLACK)))
    castling = (
        int(bool(view.castling_rights & chess.BB_H1))
        | int(bool(view.castling_rights & chess.BB_A1)) << 1
        | int(bool(view.castling_rights & chess.BB_H8)) << 2
        | int(bool(view.castling_rights & chess.BB_A8)) << 3
    )
    ep_file = -1
    if view.ep_square is not None:
        ep_file = chess.square_file(view.ep_square)
    return {
        "bitboards": bitboards,
        "castling": np.uint8(castling),
        "ep_file": np.int8(ep_file),
        "halfmove": np.uint8(min(board.halfmove_clock, 255)),
    }, flipped


def encode_move(move, flipped):
    source = orient_square(move.from_square, flipped)
    target = orient_square(move.to_square, flipped)
    promotion = 0
    if move.promotion is not None:
        promotion = PROMOTION_ORDER.index(move.promotion)
    return np.uint16(source * 64 + target), np.uint8(promotion)


def decode_move(from_to, promotion):
    source = int(from_to) // 64
    target = int(from_to) % 64
    piece = PROMOTION_ORDER[int(promotion)]
    return chess.Move(source, target, promotion=piece)


def decode_board(bitboards, castling, ep_file, halfmove):
    board = chess.Board(None)
    board.turn = chess.WHITE
    for index, piece in enumerate(PIECE_ORDER):
        for square in chess.scan_forward(int(bitboards[index])):
            board.set_piece_at(square, chess.Piece(piece, chess.WHITE))
        for square in chess.scan_forward(int(bitboards[index + 6])):
            board.set_piece_at(square, chess.Piece(piece, chess.BLACK))
    rights = chess.BB_EMPTY
    castling = int(castling)
    if castling & 1:
        rights |= chess.BB_H1
    if castling & 2:
        rights |= chess.BB_A1
    if castling & 4:
        rights |= chess.BB_H8
    if castling & 8:
        rights |= chess.BB_A8
    board.castling_rights = rights
    if int(ep_file) >= 0:
        board.ep_square = chess.square(int(ep_file), 5)
    board.halfmove_clock = int(halfmove)
    return board


def value_for(result, colour):
    if result == "1/2-1/2":
        return RESULT_DRAW
    white_won = result == "1-0"
    if white_won == (colour == chess.WHITE):
        return RESULT_WIN
    return RESULT_LOSS


def encode_game(record, board_factory=chess.Board):
    board = board_factory()
    rows = []
    for ply, uci in enumerate(record.moves):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            break
        fields, flipped = encode_board(board)
        from_to, promotion = encode_move(move, flipped)
        own_elo = record.white_elo if board.turn == chess.WHITE else record.black_elo
        opp_elo = record.black_elo if board.turn == chess.WHITE else record.white_elo
        fields.update(
            {
                "from_to": from_to,
                "promotion": promotion,
                "value": np.uint8(value_for(record.result, board.turn)),
                "own_elo": np.uint16(min(own_elo, 65535)),
                "opp_elo": np.uint16(min(opp_elo, 65535)),
                "ply": np.uint16(min(ply, 65535)),
            }
        )
        rows.append(fields)
        board.push(move)
    return rows


def to_planes(bitboards, castling, ep_file, halfmove):
    planes = np.zeros((PLANES, 8, 8), dtype=np.float32)
    for index in range(12):
        bits = np.unpackbits(
            np.array([int(bitboards[index])], dtype=">u8").view(np.uint8)
        )
        planes[index] = bits[::-1].reshape(8, 8)
    for bit in range(4):
        if int(castling) >> bit & 1:
            planes[12 + bit] = 1.0
    if int(ep_file) >= 0:
        planes[16, :, int(ep_file)] = 1.0
    planes[17] = min(int(halfmove), 100) / 100.0
    return planes


class ShardWriter:
    def __init__(self, directory, shard_size=100_000, prefix="shard"):
        self.directory = pathlib.Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.shard_size = shard_size
        self.prefix = prefix
        self.rows = []
        self.shards = []
        self.total = 0

    def add(self, rows):
        self.rows.extend(rows)
        self.total += len(rows)
        while len(self.rows) >= self.shard_size:
            self._flush(self.rows[: self.shard_size])
            self.rows = self.rows[self.shard_size :]

    def _flush(self, rows):
        if not rows:
            return
        arrays = {}
        for name, (dtype, shape) in FIELDS.items():
            stacked = np.stack([row[name] for row in rows]).astype(dtype)
            arrays[name] = stacked
        path = self.directory / f"{self.prefix}_{len(self.shards):05d}.npz"
        np.savez_compressed(path, **arrays)
        self.shards.append({"path": path.name, "positions": len(rows)})

    def close(self, config=None, counts=None):
        self._flush(self.rows)
        self.rows = []
        manifest = {
            "positions": self.total,
            "shards": self.shards,
            "fields": {name: dtype for name, (dtype, _) in FIELDS.items()},
            "planes": PLANES,
            "config": config or {},
            "filter_counts": counts or {},
        }
        path = self.directory / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest


def load_shard(path):
    with np.load(path) as data:
        return {name: data[name] for name in data.files}
