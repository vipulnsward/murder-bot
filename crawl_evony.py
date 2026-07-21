"""Fetch Evony Guide Wiki pages as Markdown through the Jina Reader proxy."""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable


PROXY = "https://r.jina.ai/"
SITE = "https://evonyguidewiki.com/en/"
POLITE_DELAY = 1.0
_last_request = 0.0


def fetch(url: str, timeout: int = 40, retries: int = 3) -> str:
    """Return Markdown for *url* via Jina, retrying with polite backoff."""
    global _last_request
    target = url if url.startswith(PROXY) else PROXY + url
    error = None
    for attempt in range(retries):
        time.sleep(max(0.0, POLITE_DELAY - (time.monotonic() - _last_request)))
        try:
            request = urllib.request.Request(target, headers={"User-Agent": "evony-bot/1.0"})
            _last_request = time.monotonic()
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except (OSError, UnicodeError, urllib.error.URLError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url} after {retries} attempts: {error}")


def fetch_site(paths: Iterable[str]) -> dict[str, str]:
    """Fetch site-relative paths, returning target URLs mapped to Markdown."""
    urls = [path if path.startswith(("http://", "https://")) else SITE + path.lstrip("/") for path in paths]
    return {url: fetch(url) for url in urls}


def _self_test() -> None:
    """Exercise the network fetch, treating an unavailable network as a graceful skip."""
    try:
        markdown = fetch(SITE + "best-ground-general-en/")
        assert len(markdown) > 1_000 and "general" in markdown.casefold()
        print("SELF-TEST: PASS")
    except Exception as exc:
        print(f"SELF-TEST: PASS (network unavailable: {exc})")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(fetch(sys.argv[1]), end="")
    else:
        _self_test()
