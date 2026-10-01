#!/usr/bin/env python3
"""Verified downloads shared by the local and cloud AutoPR helpers."""

from __future__ import annotations

import http.client
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path

YPK_URL_DEFAULT = "https://cdntx2.moecube.com/ygopro-super-pre/archive/ygopro-super-pre.ypk"
JSON_URL_DEFAULT = "https://cdntx2.moecube.com/ygopro-super-pre/data/test-release.json"
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT = 60
YPK_MEMBERS = ("test-release.cdb", "test-strings.conf", "test-update.cdb")


class DownloadError(RuntimeError):
    """The upstream response could not be downloaded or validated."""


def validate_ypk(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            missing = set(YPK_MEMBERS) - set(archive.namelist())
            if missing:
                raise DownloadError(f"YPK is missing required files: {', '.join(sorted(missing))}")
            bad_member = archive.testzip()
            if bad_member is not None:
                raise DownloadError(f"YPK checksum failed for {bad_member}")
    except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error) as exc:
        raise DownloadError(f"Invalid YPK archive: {exc}") from exc


def download_file(
    url: str,
    target: Path,
    *,
    user_agent: str,
    log_fn: Callable[[str], None],
) -> None:
    """Retry incomplete transfers; publish the target only after validation."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        log_fn(f"Downloading {url} (attempt {attempt}/{DOWNLOAD_ATTEMPTS})")
        partial: Path | None = None
        final_url = url
        try:
            request = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                final_url = response.geturl()
                if final_url != url:
                    log_fn(f"Download redirected to {final_url}")
                if response.status not in (None, 200):
                    raise DownloadError(f"Expected a complete response, got HTTP {response.status}")
                content_type = response.headers.get("Content-Type", "unknown")
                length = response.headers.get("Content-Length")
                if length is not None and not length.isdigit():
                    raise DownloadError(f"Invalid Content-Length: {length!r}")
                expected = int(length) if length is not None else None
                received = 0
                with tempfile.NamedTemporaryFile(
                    dir=target.parent, prefix=f".{target.name}.", suffix=".part", delete=False
                ) as output:
                    partial = Path(output.name)
                    while chunk := response.read(256 * 1024):
                        output.write(chunk)
                        received += len(chunk)
                # Sized HTTP reads can silently reach EOF before Content-Length.
                if expected is not None and received != expected:
                    raise DownloadError(
                        f"Incomplete download: received {received:,} of {expected:,} bytes "
                        f"(Content-Type: {content_type})"
                    )
                if received == 0:
                    raise DownloadError("Downloaded file is empty")
            if target.suffix.lower() == ".ypk":
                validate_ypk(partial)
            partial.replace(target)
            log_fn(f"Downloaded {target} ({received:,} bytes, validated)")
            return
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            ConnectionError,
            DownloadError,
        ) as exc:
            message = f"Download failed from {final_url}: {exc}"
            log_fn(message)
            if attempt == DOWNLOAD_ATTEMPTS:
                raise DownloadError(
                    f"Unable to download {url} after {DOWNLOAD_ATTEMPTS} attempts. {message}"
                ) from exc
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)
        time.sleep(attempt)
