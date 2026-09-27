import pathlib

import chess.pgn

from arena.game import MAX_PLIES, classify_termination, game_result
from board.fast_board import FastBoard

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAMES_DIR = ROOT / "games"


def check_game(game, index):
    problems = []
    if game.errors:
        problems.append(f"game {index}: parser errors {game.errors}")
        return problems
    board = FastBoard()
    moves = list(game.mainline_moves())
    for move in moves:
        if move not in board.legal_moves:
            problems.append(f"game {index}: illegal move {move} at {board.fen()}")
            return problems
        board.push(move)
    recorded_plies = game.headers.get("TotalPlies")
    if recorded_plies is not None and int(recorded_plies) != len(moves):
        problems.append(
            f"game {index}: TotalPlies {recorded_plies} but {len(moves)} moves"
        )
    result = game.headers.get("Result", "*")
    expected = game_result(board)
    if result != expected:
        problems.append(f"game {index}: Result {result} but replay gives {expected}")
    termination = game.headers.get("Termination")
    if termination is not None:
        expected_termination = classify_termination(board, MAX_PLIES)
        if termination != expected_termination:
            problems.append(
                f"game {index}: Termination {termination} but replay gives "
                f"{expected_termination}"
            )
    return problems


def check_file(path):
    problems = []
    count = 0
    with open(path) as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            count += 1
            problems.extend(check_game(game, count))
    return count, problems


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate Philidor PGN output")
    parser.add_argument("paths", nargs="*", default=None)
    args = parser.parse_args()

    paths = [pathlib.Path(p) for p in args.paths] or sorted(GAMES_DIR.glob("*.pgn"))
    if not paths:
        print(f"no PGN files found in {GAMES_DIR}")
        return 1
    total = 0
    failed = 0
    for path in paths:
        count, problems = check_file(path)
        total += count
        failed += len(problems)
        status = "ok" if not problems else f"{len(problems)} problems"
        print(f"{path.name}: {count} games, {status}")
        for problem in problems:
            print(f"  {problem}")
    print(f"{total} games checked, {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
