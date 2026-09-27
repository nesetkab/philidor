# Philidor phase one: baseline draw rates

Bot: `bots/baseline_wdl.py`. For every legal move it queries Stockfish WDL one ply ahead and plays the move with the highest draw probability. No search, no learning.

## Method

- Openings come from `data/balanced_openings.tsv`, the 1167 ECO lines of 6 to 12 plies that Stockfish scores within 50 centipawns at depth 12.
- Every opening is played twice, once with Philidor as white and once as black, so colour advantage cannot skew a level.
- A draw is adjudicated only when a threefold repetition or the fifty-move rule has actually been reached. python-chess reports a claimable draw one move early, which would score a position as drawn even when the side to move is winning and would never repeat.
- Games are capped at 300 plies. A capped game is recorded as unfinished and stays in the denominator, so it counts against the draw rate rather than being dropped.
- Win and loss are read from the Philidor side, not from white.

## Results

| Level | Opponent | N | Draw | Win | Loss | Unfinished | Draw rate | 95% Wilson CI |
|---|---|---|---|---|---|---|---|---|
| 1 | Maia 1100 (nodes=1) | 100 | 48 | 0 | 52 | 0 | 48.0% | 38.5% to 57.7% |
| 2 | Maia 1500 (nodes=1) | 100 | 64 | 0 | 36 | 0 | 64.0% | 54.2% to 72.7% |
| 3 | Maia 1900 (nodes=1) | 100 | 62 | 0 | 38 | 0 | 62.0% | 52.2% to 70.9% |
| 4 | Stockfish (depth=8) | 100 | 89 | 0 | 10 | 1 | 89.0% | 81.4% to 93.7% |
| 5 | Stockfish (depth=20) | 100 | 20 | 0 | 80 | 0 | 20.0% | 13.3% to 28.9% |

## Findings

- The bot won 0 of 500 games.
- Lowest draw rate is level 5, Stockfish (depth=20), at 20.0%.
- Highest draw rate is level 4, Stockfish (depth=8), at 89.0%.
- Those two Wilson intervals do not overlap, so the gap is larger than sampling noise at this sample size.
- The peak is an interior level, so both the weakest and the strongest opponent on this ladder draw less often than level 4. The objective is hard at both ends, not simply harder as the opponent gets stronger.
- Games ending by the fifty-move rule or the ply cap, which is the shuffling signature, peak at level 4 with 10 of 100.

## Draw rate by colour

| Level | As white | As black |
|---|---|---|
| 1 | 52.0% | 44.0% |
| 2 | 60.0% | 68.0% |
| 3 | 56.0% | 68.0% |
| 4 | 84.0% | 94.0% |
| 5 | 24.0% | 16.0% |

## Game length and terminations

| Level | Median plies | Median final halfmove clock | Terminations |
|---|---|---|---|
| 1 | 90 | 6 | checkmate 52, threefold_repetition 37, insufficient_material 7, stalemate 4 |
| 2 | 108 | 8 | threefold_repetition 51, checkmate 36, stalemate 7, insufficient_material 6 |
| 3 | 92 | 8 | threefold_repetition 51, checkmate 38, insufficient_material 7, stalemate 4 |
| 4 | 122 | 11 | threefold_repetition 65, insufficient_material 14, checkmate 10, fifty_move_rule 9, ply_cap 1, stalemate 1 |
| 5 | 82 | 2 | checkmate 80, threefold_repetition 17, insufficient_material 3 |

## Engines

| Level | Philidor engine | Philidor depth | Opponent engine |
|---|---|---|---|
| 1 | Stockfish 18 | 10 | Lc0 v0.32.1+git.dirty |
| 2 | Stockfish 18 | 10 | Lc0 v0.32.1+git.dirty |
| 3 | Stockfish 18 | 10 | Lc0 v0.32.1+git.dirty |
| 4 | Stockfish 18 | 10 | Stockfish 18 |
| 5 | Stockfish 18 | 10 | Stockfish 18 |

## Reproduce

```
python -m arena.book
python -m arena.ladder --games 100 --workers 6 --seed 0 --depth 10
python -m eval.report
```

The first command regenerates the balanced book and is only needed if `data/balanced_openings.tsv` is missing.

