import random

import chess
import numpy as np
import pytest

from lichess import encode
from lichess.filters import GameRecord


def _roundtrip(board):
    fields, flipped = encode.encode_board(board)
    restored = encode.decode_board(
        fields["bitboards"],
        fields["castling"],
        fields["ep_file"],
        fields["halfmove"],
    )
    return restored, flipped


def test_start_position_round_trips():
    board = chess.Board()
    restored, flipped = _roundtrip(board)
    assert flipped is False
    assert restored.board_fen() == board.board_fen()
    assert restored.castling_rights == board.castling_rights


def test_black_to_move_is_oriented_and_round_trips():
    board = chess.Board()
    board.push_san("e4")
    restored, flipped = _roundtrip(board)
    assert flipped is True
    assert restored.board_fen() == board.mirror().board_fen()


def test_en_passant_file_survives_encoding():
    board = chess.Board()
    for san in ("e4", "a6", "e5", "d5"):
        board.push_san(san)
    assert board.ep_square is not None
    restored, flipped = _roundtrip(board)
    expected = board if not flipped else board.mirror()
    assert restored.ep_square == expected.ep_square


def test_halfmove_clock_survives_encoding():
    board = chess.Board("8/8/4k3/8/8/4K3/8/R7 w - - 87 60")
    restored, _ = _roundtrip(board)
    assert restored.halfmove_clock == 87


def test_halfmove_clock_is_clamped_to_a_byte():
    board = chess.Board("8/8/4k3/8/8/4K3/8/R7 w - - 87 60")
    board.halfmove_clock = 900
    fields, _ = encode.encode_board(board)
    assert int(fields["halfmove"]) == 255


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_random_games_round_trip_at_every_ply(seed):
    rng = random.Random(seed)
    board = chess.Board()
    for _ in range(120):
        if board.is_game_over():
            break
        restored, flipped = _roundtrip(board)
        expected = board.mirror() if flipped else board
        assert restored.board_fen() == expected.board_fen()
        assert restored.castling_rights == expected.castling_rights
        assert restored.ep_square == expected.ep_square
        board.push(rng.choice(list(board.legal_moves)))


@pytest.mark.parametrize("seed", [7, 8, 9])
def test_moves_round_trip_through_orientation(seed):
    rng = random.Random(seed)
    board = chess.Board()
    for _ in range(80):
        if board.is_game_over():
            break
        move = rng.choice(list(board.legal_moves))
        flipped = board.turn == chess.BLACK
        from_to, promotion = encode.encode_move(move, flipped)
        decoded = encode.decode_move(from_to, promotion)
        expected = chess.Move(
            encode.orient_square(move.from_square, flipped),
            encode.orient_square(move.to_square, flipped),
            promotion=move.promotion,
        )
        assert decoded == expected
        board.push(move)


def test_promotion_round_trips():
    board = chess.Board("8/P7/8/8/8/8/8/K6k w - - 0 1")
    move = chess.Move.from_uci("a7a8q")
    from_to, promotion = encode.encode_move(move, False)
    assert encode.decode_move(from_to, promotion) == move


def test_value_is_from_the_side_to_move():
    assert encode.value_for("1-0", chess.WHITE) == encode.RESULT_WIN
    assert encode.value_for("1-0", chess.BLACK) == encode.RESULT_LOSS
    assert encode.value_for("0-1", chess.WHITE) == encode.RESULT_LOSS
    assert encode.value_for("0-1", chess.BLACK) == encode.RESULT_WIN
    assert encode.value_for("1/2-1/2", chess.WHITE) == encode.RESULT_DRAW
    assert encode.value_for("1/2-1/2", chess.BLACK) == encode.RESULT_DRAW


def _record(result="1-0"):
    board = chess.Board()
    moves = []
    for san in ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6"):
        move = board.parse_san(san)
        moves.append(move.uci())
        board.push(move)
    return GameRecord(
        white_elo=1520,
        black_elo=1480,
        result=result,
        time_control="600+0",
        category="blitz",
        eco="C70",
        moves=moves,
    )


def test_encode_game_emits_one_row_per_move():
    rows = encode.encode_game(_record())
    assert len(rows) == 6
    assert int(rows[0]["ply"]) == 0
    assert int(rows[5]["ply"]) == 5


def test_encode_game_alternates_the_elo_perspective():
    rows = encode.encode_game(_record())
    assert int(rows[0]["own_elo"]) == 1520
    assert int(rows[0]["opp_elo"]) == 1480
    assert int(rows[1]["own_elo"]) == 1480
    assert int(rows[1]["opp_elo"]) == 1520


def test_encode_game_alternates_the_value_perspective():
    rows = encode.encode_game(_record(result="1-0"))
    assert int(rows[0]["value"]) == encode.RESULT_WIN
    assert int(rows[1]["value"]) == encode.RESULT_LOSS


def test_encode_game_stops_at_an_illegal_move():
    record = _record()
    record.moves[3] = "a1a8"
    rows = encode.encode_game(record)
    assert len(rows) == 3


def test_planes_have_the_documented_shape_and_content():
    board = chess.Board()
    fields, _ = encode.encode_board(board)
    planes = encode.to_planes(
        fields["bitboards"],
        fields["castling"],
        fields["ep_file"],
        fields["halfmove"],
    )
    assert planes.shape == (encode.PLANES, 8, 8)
    assert planes[0].sum() == 8
    assert planes[6].sum() == 8
    assert planes[5].sum() == 1
    assert planes[12].sum() == 64
    assert planes[17].max() == 0.0


def test_planes_put_own_pawns_on_the_second_rank():
    board = chess.Board()
    fields, _ = encode.encode_board(board)
    planes = encode.to_planes(
        fields["bitboards"],
        fields["castling"],
        fields["ep_file"],
        fields["halfmove"],
    )
    assert planes[0, 1].sum() == 8
    assert planes[6, 6].sum() == 8


def test_shard_writer_splits_and_writes_a_manifest(tmp_path):
    writer = encode.ShardWriter(tmp_path, shard_size=4)
    writer.add(encode.encode_game(_record()))
    writer.add(encode.encode_game(_record()))
    manifest = writer.close(config={"min_elo": 1400}, counts={"elo_out_of_band": 3})
    assert manifest["positions"] == 12
    assert [shard["positions"] for shard in manifest["shards"]] == [4, 4, 4]
    assert manifest["config"]["min_elo"] == 1400
    assert manifest["filter_counts"]["elo_out_of_band"] == 3
    assert (tmp_path / "manifest.json").exists()


def test_shard_contents_reload_with_the_declared_dtypes(tmp_path):
    writer = encode.ShardWriter(tmp_path, shard_size=100)
    writer.add(encode.encode_game(_record()))
    manifest = writer.close()
    shard = encode.load_shard(tmp_path / manifest["shards"][0]["path"])
    assert shard["bitboards"].shape == (6, 12)
    assert shard["bitboards"].dtype == np.uint64
    assert shard["value"].dtype == np.uint8
    assert shard["own_elo"].tolist() == [1520, 1480, 1520, 1480, 1520, 1480]


def test_a_reloaded_shard_row_reconstructs_its_position(tmp_path):
    record = _record()
    writer = encode.ShardWriter(tmp_path, shard_size=100)
    writer.add(encode.encode_game(record))
    manifest = writer.close()
    shard = encode.load_shard(tmp_path / manifest["shards"][0]["path"])
    board = chess.Board()
    for index, uci in enumerate(record.moves):
        restored = encode.decode_board(
            shard["bitboards"][index],
            shard["castling"][index],
            shard["ep_file"][index],
            shard["halfmove"][index],
        )
        expected = board.mirror() if board.turn == chess.BLACK else board
        assert restored.board_fen() == expected.board_fen()
        board.push(chess.Move.from_uci(uci))
