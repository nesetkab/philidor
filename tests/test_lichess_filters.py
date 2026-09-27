import io

import pytest

from lichess import filters

GAME_TEMPLATE = """[Event "Rated {category} game"]
[Site "https://lichess.org/{gid}"]
[White "alice"]
[Black "bob"]
[Result "{result}"]
[WhiteElo "{white}"]
[BlackElo "{black}"]
[TimeControl "{tc}"]
[Termination "{termination}"]
[ECO "C70"]

{moves} {result}

"""


def make_pgn(games):
    return "".join(GAME_TEMPLATE.format(**game) for game in games)


def game(
    gid="a1",
    white=1500,
    black=1500,
    tc="600+0",
    result="1-0",
    termination="Normal",
    category="Blitz",
    moves="1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7",
):
    return dict(
        gid=gid,
        white=white,
        black=black,
        tc=tc,
        result=result,
        termination=termination,
        category=category,
        moves=moves,
    )


@pytest.mark.parametrize(
    "time_control,expected",
    [
        ("15+0", "ultrabullet"),
        ("60+0", "bullet"),
        ("120+1", "bullet"),
        ("300+0", "blitz"),
        ("180+3", "blitz"),
        ("600+0", "rapid"),
        ("900+0", "rapid"),
        ("1800+0", "classical"),
        ("600+30", "classical"),
        ("-", "correspondence"),
        ("", "correspondence"),
        ("garbage", "correspondence"),
    ],
)
def test_time_control_classification(time_control, expected):
    assert filters.classify_time_control(time_control) == expected


def test_estimated_seconds_includes_the_increment():
    assert filters.estimated_seconds("300+5") == 300 + 200
    assert filters.estimated_seconds("300") == 300
    assert filters.estimated_seconds("-") is None


def test_filter_accepts_a_matching_game():
    handle = io.StringIO(make_pgn([game()]))
    got = list(filters.iter_games(handle, filters.GameFilter()))
    assert len(got) == 1
    assert got[0].white_elo == 1500
    assert got[0].category == "rapid"
    assert len(got[0].moves) == 10


def test_filter_rejects_elo_outside_the_band():
    handle = io.StringIO(make_pgn([game(white=1100, black=1500)]))
    spec = filters.GameFilter(min_elo=1400, max_elo=1600)
    assert list(filters.iter_games(handle, spec)) == []


def test_filter_can_require_only_one_player_in_band():
    handle = io.StringIO(make_pgn([game(white=1100, black=1500)]))
    spec = filters.GameFilter(
        min_elo=1400, max_elo=1600, both_players_in_band=False
    )
    assert len(list(filters.iter_games(handle, spec))) == 1


def test_filter_rejects_unwanted_time_controls():
    handle = io.StringIO(make_pgn([game(tc="60+0")]))
    spec = filters.GameFilter(time_controls=("blitz",))
    assert list(filters.iter_games(handle, spec)) == []


def test_filter_rejects_missing_elo():
    text = make_pgn([game()]).replace('[WhiteElo "1500"]\n', "")
    handle = io.StringIO(text)
    assert list(filters.iter_games(handle, filters.GameFilter())) == []


def test_filter_rejects_abandoned_games():
    handle = io.StringIO(make_pgn([game(termination="Abandoned")]))
    assert list(filters.iter_games(handle, filters.GameFilter())) == []


def test_filter_rejects_short_games():
    handle = io.StringIO(make_pgn([game(moves="1. e4 e5")]))
    spec = filters.GameFilter(min_ply=10)
    assert list(filters.iter_games(handle, spec)) == []


def test_filter_records_rejection_reasons():
    games = [
        game(gid="a", white=900, black=900),
        game(gid="b", tc="60+0"),
        game(gid="c", termination="Abandoned"),
        game(gid="d"),
    ]
    handle = io.StringIO(make_pgn(games))
    spec = filters.GameFilter(min_elo=1400, max_elo=1600, time_controls=("rapid",))
    seen = {}
    got = list(filters.iter_games(handle, spec, on_scanned=lambda s, a, c: seen.update(c)))
    assert len(got) == 1
    assert seen["elo_out_of_band"] == 1
    assert seen["time_control"] == 1
    assert seen["termination"] == 1


def test_filter_reads_every_game_in_a_multi_game_stream():
    games = [game(gid=f"g{i}") for i in range(5)]
    handle = io.StringIO(make_pgn(games))
    assert len(list(filters.iter_games(handle, filters.GameFilter()))) == 5


def test_limit_stops_early():
    games = [game(gid=f"g{i}") for i in range(5)]
    handle = io.StringIO(make_pgn(games))
    assert len(list(filters.iter_games(handle, filters.GameFilter(), limit=2))) == 2


def test_skip_supports_logical_resume():
    games = [game(gid=f"g{i}") for i in range(5)]
    handle = io.StringIO(make_pgn(games))
    got = list(filters.iter_games(handle, filters.GameFilter(), skip=3))
    assert len(got) == 2


def test_an_empty_stream_yields_nothing():
    handle = io.StringIO("")
    assert list(filters.iter_games(handle, filters.GameFilter())) == []
