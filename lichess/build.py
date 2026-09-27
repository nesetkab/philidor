import argparse
import dataclasses
import json
import pathlib
import time

from lichess import source
from lichess.encode import ShardWriter, encode_game
from lichess.filters import CATEGORIES, GameFilter, iter_games

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "training"


def build(
    handle,
    game_filter,
    out_dir,
    shard_size=100_000,
    limit_games=None,
    limit_positions=None,
    skip_games=0,
    progress_every=20_000,
    log=print,
):
    writer = ShardWriter(out_dir, shard_size=shard_size)
    started = time.perf_counter()
    state = {"scanned": 0, "accepted": 0, "counts": {}}

    def on_scanned(scanned, accepted, counts):
        state["scanned"] = scanned
        state["counts"] = dict(counts)
        if progress_every and scanned % progress_every == 0:
            elapsed = time.perf_counter() - started
            log(
                f"scanned {scanned} accepted {accepted} positions {writer.total} "
                f"in {elapsed:.0f}s",
                flush=True,
            )

    for record in iter_games(
        handle,
        game_filter,
        limit=limit_games,
        skip=skip_games,
        on_scanned=on_scanned,
    ):
        state["accepted"] += 1
        writer.add(encode_game(record))
        if limit_positions is not None and writer.total >= limit_positions:
            break

    config = {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in dataclasses.asdict(game_filter).items()
    }
    config["shard_size"] = shard_size
    config["skip_games"] = skip_games
    config["games_scanned"] = state["scanned"]
    config["games_accepted"] = state["accepted"]
    config["seconds"] = round(time.perf_counter() - started, 1)
    manifest = writer.close(config=config, counts=state["counts"])
    log(
        f"done: scanned {state['scanned']} accepted {state['accepted']} "
        f"positions {manifest['positions']} shards {len(manifest['shards'])}",
        flush=True,
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build training shards from a Lichess monthly dump"
    )
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--path", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--min-elo", type=int, default=1000)
    parser.add_argument("--max-elo", type=int, default=1200)
    parser.add_argument("--time-controls", default="blitz,rapid,classical")
    parser.add_argument("--min-ply", type=int, default=10)
    parser.add_argument("--either-player", action="store_true")
    parser.add_argument("--shard-size", type=int, default=100_000)
    parser.add_argument("--limit-games", type=int, default=None)
    parser.add_argument("--limit-positions", type=int, default=None)
    parser.add_argument("--skip-games", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=20_000)
    args = parser.parse_args(argv)

    controls = tuple(
        part.strip() for part in args.time_controls.split(",") if part.strip()
    )
    unknown = [name for name in controls if name not in CATEGORIES]
    if unknown:
        raise SystemExit(f"unknown time controls {unknown}, pick from {CATEGORIES}")

    game_filter = GameFilter(
        min_elo=args.min_elo,
        max_elo=args.max_elo,
        time_controls=controls,
        min_ply=args.min_ply,
        both_players_in_band=not args.either_player,
    )
    handle = source.open_month(
        year=args.year, month=args.month, path=args.path, url=args.url
    )
    try:
        manifest = build(
            handle,
            game_filter,
            args.out,
            shard_size=args.shard_size,
            limit_games=args.limit_games,
            limit_positions=args.limit_positions,
            skip_games=args.skip_games,
            progress_every=args.progress_every,
        )
    finally:
        handle.close()
    print(json.dumps(manifest["config"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
