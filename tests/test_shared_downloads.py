"""Regression coverage for premature EOF and invalid upstream packages."""

import http.client
import io
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import shared_downloads as downloads


def make_ypk(members=downloads.YPK_MEMBERS):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in members:
            archive.writestr(name, b"test payload")
    return buffer.getvalue()


class Response(io.BytesIO):
    def __init__(self, body, *, length="auto", status=200):
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Type": "application/octet-stream"}
        if length is not None:
            self.headers["Content-Length"] = str(len(body) if length == "auto" else length)

    def geturl(self):
        return "https://cdncf.moecube.com/ygopro-super-pre/archive/current.ypk"


class BrokenResponse(Response):
    def read(self, size=-1):
        if self.tell():
            raise http.client.IncompleteRead(b"partial", 100)
        return super().read(20)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.target = self.root / "package.ypk"
        self.messages = []
        self.sleep = patch.object(downloads.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def run_download(self, responses, target=None):
        with patch.object(downloads.urllib.request, "urlopen", side_effect=responses) as opened:
            downloads.download_file(
                downloads.YPK_URL_DEFAULT,
                target or self.target,
                user_agent="TransSuperpre-Test/1.0",
                log_fn=self.messages.append,
            )
        return opened

    def assert_no_partial_files(self):
        self.assertEqual(list(self.root.rglob("*.part")), [])

    def test_complete_archive_follows_redirect_and_publishes(self):
        data = make_ypk()
        opened = self.run_download([Response(data)])
        self.assertEqual(self.target.read_bytes(), data)
        self.assertEqual(opened.call_count, 1)
        self.assertTrue(any("redirected to https://cdncf.moecube.com" in m for m in self.messages))
        self.sleep.assert_not_called()
        self.assert_no_partial_files()

    def test_silent_short_read_is_retried_before_success(self):
        data = make_ypk()
        opened = self.run_download([Response(data[:30], length=len(data)), Response(data)])
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(self.target.read_bytes(), data)
        self.assertTrue(any(f"received 30 of {len(data):,} bytes" in m for m in self.messages))
        self.assertEqual(sum(m.startswith("Downloaded ") for m in self.messages), 1)
        self.assert_no_partial_files()

    def test_exhausted_retries_preserve_previous_file(self):
        self.target.write_bytes(b"previous package")
        with self.assertRaisesRegex(downloads.DownloadError, "after 3 attempts"):
            self.run_download([Response(b"short", length=999) for _ in range(3)])
        self.assertEqual(self.target.read_bytes(), b"previous package")
        self.assertFalse(any(m.startswith("Downloaded ") for m in self.messages))
        self.assertEqual(self.sleep.call_count, 2)
        self.assert_no_partial_files()

    def test_invalid_archives_are_rejected_even_without_length(self):
        corrupt_crc = make_ypk().replace(b"test payload", b"bad! payload", 1)
        for data in (b"<html>upstream error</html>", make_ypk()[:-22], make_ypk(["test-release.cdb"]), corrupt_crc):
            with self.subTest(data=data[:32]):
                with self.assertRaises(downloads.DownloadError):
                    self.run_download([Response(data, length=None) for _ in range(3)])
                self.assertFalse(self.target.exists())
                self.assert_no_partial_files()

    def test_invalid_archive_can_recover_on_retry(self):
        data = make_ypk()
        self.run_download([Response(b"not a zip"), Response(data)])
        self.assertEqual(self.target.read_bytes(), data)

    def test_valid_archive_without_content_length(self):
        data = make_ypk()
        self.run_download([Response(data, length=None)])
        self.assertEqual(self.target.read_bytes(), data)

    def test_partial_http_response_is_rejected(self):
        # A valid but partial HTTP response must not be mistaken for the full file.
        with self.assertRaisesRegex(downloads.DownloadError, "HTTP 206"):
            self.run_download([Response(make_ypk(), status=206) for _ in range(3)])
        self.assertFalse(self.target.exists())
        self.assert_no_partial_files()

    def test_interrupted_body_is_retried_and_cleaned_up(self):
        data = make_ypk()
        self.run_download([BrokenResponse(data), Response(data)])
        self.assertEqual(self.target.read_bytes(), data)
        self.assert_no_partial_files()

    def test_network_errors_are_retried(self):
        data = make_ypk()
        self.run_download([urllib.error.URLError("connection lost"), TimeoutError("timed out"), Response(data)])
        self.assertEqual(self.target.read_bytes(), data)

    def test_database_download_also_checks_length(self):
        target = self.root / "nested" / "cards.cdb"
        data = b"SQLite format 3\x00database contents"
        self.run_download([Response(data[:5], length=len(data)), Response(data)], target=target)
        self.assertEqual(target.read_bytes(), data)
        self.assert_no_partial_files()

    def test_empty_download_is_rejected(self):
        with self.assertRaisesRegex(downloads.DownloadError, "empty"):
            self.run_download([Response(b"") for _ in range(3)], target=self.root / "cards.cdb")
        self.assertFalse((self.root / "cards.cdb").exists())
        self.assert_no_partial_files()

    def test_all_language_helpers_use_shared_downloads(self):
        import autopr_zh_tw
        import es_autopr
        import ocg_autopr
        import tcg_autopr

        tcg_autopr.configure("en")
        ocg_autopr.configure("jp")
        for module in (tcg_autopr, ocg_autopr, es_autopr, autopr_zh_tw):
            with self.subTest(module=module.__name__):
                data = make_ypk()
                with patch.object(downloads.urllib.request, "urlopen", return_value=Response(data)):
                    with patch.object(module, "log"):
                        module.download_file("https://example.com/custom.ypk", self.target)
                self.assertEqual(self.target.read_bytes(), data)

    def test_language_helpers_report_download_failure_without_zip_traceback(self):
        import autopr_zh_tw
        import es_autopr
        import ocg_autopr
        import tcg_autopr

        tcg_autopr.configure("en")
        ocg_autopr.configure("jp")
        for module in (tcg_autopr, ocg_autopr, es_autopr, autopr_zh_tw):
            with self.subTest(module=module.__name__):
                with patch.object(module, "download_verified_file", side_effect=downloads.DownloadError("incomplete transfer")):
                    with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                        with self.assertRaises(SystemExit) as exit_error:
                            module.download_file("https://example.com/custom.ypk", self.target)
                self.assertEqual(exit_error.exception.code, 1)
                self.assertIn("incomplete transfer", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
