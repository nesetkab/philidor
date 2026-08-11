import chess.pgn


def write_game(board, result, path):
    game = chess.pgn.Game.from_board(board)
    game.headers["Result"] = result
    with open(path, "a") as file:
        print(game, file=file, end="\n\n")
