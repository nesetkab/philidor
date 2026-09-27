import zstandard

from lichess import source


def test_month_filename_is_zero_padded():
    assert source.month_filename(2026, 8) == "lichess_db_standard_rated_2026-08.pgn.zst"
    assert source.month_filename(2013, 12) == (
        "lichess_db_standard_rated_2013-12.pgn.zst"
    )


def test_month_url_points_at_the_standard_database():
    url = source.month_url(2026, 8)
    assert url.startswith("https://database.lichess.org/standard/")
    assert url.endswith("lichess_db_standard_rated_2026-08.pgn.zst")


def test_open_local_reads_plain_text(tmp_path):
    path = tmp_path / "games.pgn"
    path.write_text('[Event "test"]\n\n1. e4 *\n')
    with source.open_local(path) as handle:
        assert "Event" in handle.read()


def test_open_local_decompresses_zstd(tmp_path):
    path = tmp_path / "games.pgn.zst"
    raw = b'[Event "test"]\n\n1. e4 *\n'
    path.write_bytes(zstandard.ZstdCompressor().compress(raw))
    with source.open_local(path) as handle:
        assert handle.read() == raw.decode()


def test_open_local_survives_invalid_utf8(tmp_path):
    path = tmp_path / "games.pgn"
    path.write_bytes(b'[White "caf\xff"]\n\n1. e4 *\n')
    with source.open_local(path) as handle:
        assert "White" in handle.read()


def test_open_month_requires_enough_information():
    try:
        source.open_month()
    except ValueError as error:
        assert "year and month" in str(error)
    else:
        raise AssertionError("expected a ValueError")
