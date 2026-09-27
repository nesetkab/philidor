import io
import pathlib
import urllib.request

import zstandard

BASE_URL = "https://database.lichess.org/standard"
USER_AGENT = "philidor-research/0.1"
MAX_WINDOW = 2**31


def month_filename(year, month):
    return f"lichess_db_standard_rated_{year:04d}-{month:02d}.pgn.zst"


def month_url(year, month):
    return f"{BASE_URL}/{month_filename(year, month)}"


def _wrap(binary):
    decompressor = zstandard.ZstdDecompressor(max_window_size=MAX_WINDOW)
    reader = decompressor.stream_reader(binary)
    return io.TextIOWrapper(reader, encoding="utf-8", errors="replace")


def open_local(path):
    handle = open(path, "rb")
    if str(path).endswith(".zst"):
        return _wrap(handle)
    return io.TextIOWrapper(handle, encoding="utf-8", errors="replace")


def open_remote(url, timeout=60.0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    response = urllib.request.urlopen(request, timeout=timeout)
    return _wrap(response)


def open_month(year=None, month=None, path=None, url=None, timeout=60.0):
    if path is not None:
        return open_local(path)
    if url is None:
        if year is None or month is None:
            raise ValueError("give a path, a url, or both year and month")
        url = month_url(year, month)
    return open_remote(url, timeout=timeout)


def remote_size(url, timeout=30.0):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}, method="HEAD"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
    return int(length) if length is not None else None


def download(url, destination, timeout=60.0, chunk=1 << 20, progress=None):
    destination = pathlib.Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    have = destination.stat().st_size if destination.exists() else 0
    total = remote_size(url, timeout=timeout)
    if total is not None and have >= total:
        return destination
    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        mode = "ab" if have and response.status == 206 else "wb"
        if mode == "wb":
            have = 0
        with open(destination, mode) as handle:
            while True:
                block = response.read(chunk)
                if not block:
                    break
                handle.write(block)
                have += len(block)
                if progress is not None:
                    progress(have, total)
    return destination
