import chess.pgn

from arena.pgn import write_game
from board.fast_board import FastBoard
from eval import validate

SHUFFLE = ("Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1", "Ng8")


def _threefold_board():
    board = FastBoard()
    for san in SHUFFLE:
        board.push_san(san)
    return board


def _read_one(path):
    with open(path) as handle:
        return chess.pgn.read_game(handle)


def test_a_consistent_game_has_no_problems(tmp_path):
    board = _threefold_board()
    path = tmp_path / "level1.pgn"
    write_game(
        board,
        "1/2-1/2",
        path,
        headers={
            "TotalPlies": len(board.move_stack),
            "Termination": "threefold_repetition",
        },
    )
    count, problems = validate.check_file(path)
    assert count == 1
    assert problems == []


def test_a_wrong_result_is_reported(tmp_path):
    board = _threefold_board()
    path = tmp_path / "level1.pgn"
    write_game(board, "1-0", path, headers={"TotalPlies": len(board.move_stack)})
    count, problems = validate.check_file(path)
    assert count == 1
    assert any("Result 1-0" in problem for problem in problems)


def test_a_wrong_ply_count_is_reported(tmp_path):
    board = _threefold_board()
    path = tmp_path / "level1.pgn"
    write_game(board, "1/2-1/2", path, headers={"TotalPlies": 99})
    _, problems = validate.check_file(path)
    assert any("TotalPlies 99" in problem for problem in problems)


def test_a_wrong_termination_is_reported(tmp_path):
    board = _threefold_board()
    path = tmp_path / "level1.pgn"
    write_game(
        board,
        "1/2-1/2",
        path,
        headers={
            "TotalPlies": len(board.move_stack),
            "Termination": "fifty_move_rule",
        },
    )
    _, problems = validate.check_file(path)
    assert any("Termination fifty_move_rule" in problem for problem in problems)


def test_every_game_in_a_multi_game_file_is_checked(tmp_path):
    board = _threefold_board()
    path = tmp_path / "level1.pgn"
    for _ in range(3):
        write_game(
            board,
            "1/2-1/2",
            path,
            headers={
                "TotalPlies": len(board.move_stack),
                "Termination": "threefold_repetition",
            },
        )
    count, problems = validate.check_file(path)
    assert count == 3
    assert problems == []
