import io
import json

from lichess.build import build, main
from lichess.filters import GameFilter

from tests.test_lichess_filters import game, make_pgn


def _handle(count=6, **overrides):
    games = [game(gid=f"g{i}", **overrides) for i in range(count)]
    return io.StringIO(make_pgn(games))


def test_build_writes_shards_and_a_manifest(tmp_path):
    manifest = build(
        _handle(6), GameFilter(), tmp_path, shard_size=20, progress_every=0, log=lambda *a, **k: None
    )
    assert manifest["positions"] == 60
    assert sum(shard["positions"] for shard in manifest["shards"]) == 60
    assert manifest["config"]["games_scanned"] == 6
    assert manifest["config"]["games_accepted"] == 6
    assert (tmp_path / "manifest.json").exists()


def test_build_records_the_filter_in_the_manifest(tmp_path):
    spec = GameFilter(min_elo=1400, max_elo=1600, time_controls=("rapid",))
    manifest = build(
        _handle(2), spec, tmp_path, progress_every=0, log=lambda *a, **k: None
    )
    assert manifest["config"]["min_elo"] == 1400
    assert manifest["config"]["max_elo"] == 1600
    assert manifest["config"]["time_controls"] == ["rapid"]


def test_build_records_rejection_counts(tmp_path):
    handle = io.StringIO(
        make_pgn([game(gid="a", white=900, black=900), game(gid="b")])
    )
    spec = GameFilter(min_elo=1400, max_elo=1600)
    manifest = build(
        handle, spec, tmp_path, progress_every=0, log=lambda *a, **k: None
    )
    assert manifest["filter_counts"]["elo_out_of_band"] == 1
    assert manifest["config"]["games_accepted"] == 1


def test_build_honours_a_position_limit(tmp_path):
    manifest = build(
        _handle(6),
        GameFilter(),
        tmp_path,
        shard_size=1000,
        limit_positions=25,
        progress_every=0,
        log=lambda *a, **k: None,
    )
    assert manifest["positions"] == 30
    assert manifest["config"]["games_accepted"] == 3


def test_build_honours_a_game_limit(tmp_path):
    manifest = build(
        _handle(6),
        GameFilter(),
        tmp_path,
        limit_games=2,
        progress_every=0,
        log=lambda *a, **k: None,
    )
    assert manifest["config"]["games_accepted"] == 2
    assert manifest["positions"] == 20


def test_build_skips_games_for_a_logical_resume(tmp_path):
    manifest = build(
        _handle(6),
        GameFilter(),
        tmp_path,
        skip_games=4,
        progress_every=0,
        log=lambda *a, **k: None,
    )
    assert manifest["config"]["games_accepted"] == 2
    assert manifest["config"]["skip_games"] == 4


def test_cli_rejects_an_unknown_time_control(tmp_path):
    pgn = tmp_path / "games.pgn"
    pgn.write_text(make_pgn([game()]))
    try:
        main(["--path", str(pgn), "--out", str(tmp_path / "out"), "--time-controls", "hyperbullet"])
    except SystemExit as error:
        assert "unknown time controls" in str(error)
    else:
        raise AssertionError("expected a SystemExit")


def test_cli_builds_from_a_local_file(tmp_path, capsys):
    pgn = tmp_path / "games.pgn"
    pgn.write_text(make_pgn([game(gid=f"g{i}") for i in range(3)]))
    out = tmp_path / "out"
    assert main(["--path", str(pgn), "--out", str(out), "--min-elo", "1400", "--max-elo", "1600"]) == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["positions"] == 30
    assert manifest["config"]["games_accepted"] == 3
