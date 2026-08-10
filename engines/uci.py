import subprocess
import queue
import chess
import dataclasses
import threading

DEAD = object()


@dataclasses.dataclass
class AnalysisResult:
    wdl: tuple[int, int, int] | None
    score_cp: int | None
    mate_in: int | None
    bestmove: chess.Move
    depth: int | None


class EngineError(Exception):
    pass


class EngineTimeout(EngineError):
    pass


class EngineDead(EngineError):
    pass


class Engine:
    def __init__(self, path, options, timeout=10.0, debug=False):
        self.proc = subprocess.Popen(
            args=path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            stderr=subprocess.DEVNULL,
        )
        self.timeout = timeout
        self.debug = debug

        assert self.proc.stdout is not None
        assert self.proc.stdin is not None
        self.stdout = self.proc.stdout
        self.stdin = self.proc.stdin

        self.queue = queue.Queue()
        self.alive = True
        self.closed = False
        threading.Thread(target=self._reader, daemon=True).start()
        self._handshake()
        for name, value in options.items():
            self._send(f"setoption name {name} value {value}")
        self._sync()

    def _reader(self):
        for line in self.stdout:
            line = line.strip()
            self.queue.put(line)
            if self.debug:
                print(line)
        self.queue.put(DEAD)

    def _send(self, command):
        self.stdin.write(command + "\n")
        self.stdin.flush()

    def _readline(self):
        try:
            item = self.queue.get(timeout=self.timeout)
        except queue.Empty as e:
            self.alive = False
            raise EngineTimeout(f"no response within {self.timeout}s") from e
        if item is DEAD:
            self.alive = False
            raise EngineDead(f"engine exited with {self.proc.poll()}")

        return item

    def _read_until(self, sentinel_prefix):
        lines = []
        while True:
            line = self._readline()
            lines.append(line)
            if line.startswith(sentinel_prefix):
                return lines

    def _handshake(self):
        self._send("uci")
        self._read_until("uciok")

    def _sync(self):
        self._send("isready")
        self._read_until("readyok")

    def analyze(self, board, depth=None, movetime=None):
        if (depth is None) == (movetime is None):
            raise ValueError("naming both depth & movetime in uci.analyze")

        self._send("position fen " + board.fen())
        self._sync()
        self._send(f"go movetime {movetime}" if depth is None else f"go depth {depth}")

        last_info = None
        while True:
            line = self._readline()
            if line.startswith("info ") and " pv " in line:
                last_info = line
            if line.startswith("bestmove"):
                bestmove_line = line
                break

        if last_info is None:
            raise EngineError("no info lines")
        return self._build_result(last_info, bestmove_line, board)

    def _build_result(self, last_info, bestmove_line, board):
        info = self._parse_info(last_info)
        tokens = bestmove_line.split()
        if len(tokens) >= 2 and tokens[1] != "(none)":
            bestmove = chess.Move.from_uci(tokens[1])
            if bestmove not in board.legal_moves:
                raise EngineError(f"bestmove false {board.fen()} - {bestmove}")
        else:
            raise EngineError("no bestmove")

        return AnalysisResult(info[0], info[1], info[2], bestmove, info[3])

    def _parse_info(self, line):
        tokens = line.split()
        i = 0
        wdl = None
        depth = None
        score_cp = None
        mate_in = None
        try:
            while i < len(tokens):
                match tokens[i]:
                    case "wdl":
                        wdl = (
                            int(tokens[i + 1]),
                            int(tokens[i + 2]),
                            int(tokens[i + 3]),
                        )
                        i += 4
                    case "depth":
                        depth = int(tokens[i + 1])
                        i += 2
                    case "score":
                        if tokens[i + 1] == "cp":
                            score_cp = int(tokens[i + 2])
                        elif tokens[i + 1] == "mate":
                            mate_in = int(tokens[i + 2])
                        i += 3
                    case "pv" | "string":
                        break
                    case _:
                        i += 1

        except (IndexError, ValueError) as e:
            raise EngineError("parse info err") from e

        return (wdl, score_cp, mate_in, depth)

    def close(self):
        if self.closed:
            return
        try:
            self._send("quit")
        except BrokenPipeError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.alive = False
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
