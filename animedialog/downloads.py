"""Bounded range downloads with durable per-range files and a contiguous resume file."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx


def parallel_ranges(url, part, total, progress, cancel, workers=6):
    part = Path(part)
    chunks = part.with_name(part.name + ".chunks")
    chunks.mkdir(exist_ok=True)
    offset = part.stat().st_size if part.exists() else 0
    size = 16 * 1024 * 1024
    ranges = [(a, min(a + size, total) - 1) for a in range(offset, total, size)]

    def fetch(bounds):
        a, b = bounds
        target = chunks / f"{a}-{b}"
        if target.exists() and target.stat().st_size == b - a + 1:
            return target
        separator = "&" if "?" in url else "?"
        # Distinct URLs prevent stale shared-cache responses for different ranges.
        with httpx.Client(
            follow_redirects=True, timeout=90, headers={"Accept-Encoding": "identity"}
        ) as client:
            for attempt in range(3):
                try:
                    with client.stream(
                        "GET",
                        url + separator + f"animedialog_range={a}",
                        headers={"Range": f"bytes={a}-{b}"},
                    ) as response:
                        response.raise_for_status()
                        if response.status_code != 206 or not response.headers.get(
                            "content-range", ""
                        ).startswith(f"bytes {a}-{b}/"):
                            raise ValueError("服务器未支持分段下载，请稍后重试")
                        with target.with_suffix(".tmp").open("wb") as stream:
                            for data in response.iter_bytes(1024 * 1024):
                                if cancel():
                                    raise InterruptedError("下载已暂停，可再次下载续传")
                                stream.write(data)
                    temporary = target.with_suffix(".tmp")
                    if temporary.stat().st_size != b - a + 1:
                        raise ValueError("下载分段不完整")
                    temporary.replace(target)
                    return target
                except (httpx.HTTPError, ValueError):
                    if attempt == 2:
                        raise
                    if cancel():
                        raise InterruptedError("下载已暂停，可再次下载续传")
                    time.sleep(1 + attempt)

    # Limit submitted ranges to keep unfinished storage and requests bounded.
    with ThreadPoolExecutor(max_workers=workers) as pool, part.open("ab") as stream:
        pending = {}
        submitted = 0
        for index, bounds in enumerate(ranges):
            while submitted < min(len(ranges), index + workers):
                pending[submitted] = pool.submit(fetch, ranges[submitted])
                submitted += 1
            future = pending.pop(index)
            while not future.done():
                if cancel():
                    raise InterruptedError("下载已暂停，可再次下载续传")
                progress(offset, total)
                time.sleep(0.3)
            target = future.result()
            with target.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    stream.write(block)
                    offset += len(block)
            stream.flush()
            target.unlink()
            progress(offset, total)
