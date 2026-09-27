import chess.pgn

STANDARD_ORDER = ["Event", "Site", "Date", "Round", "White", "Black", "Result"]


def build_game(board, result, headers=None):
    game = chess.pgn.Game.from_board(board)
    game.headers["Result"] = result
    for key, value in (headers or {}).items():
        game.headers[key] = str(value)
    return game


def write_game(board, result, path, headers=None, lock=None):
    game = build_game(board, result, headers)
    text = str(game)
    if lock is None:
        _append(path, text)
    else:
        with lock:
            _append(path, text)
    return game


def _append(path, text):
    with open(path, "a") as file:
        file.write(text + "\n\n")
        file.flush()
