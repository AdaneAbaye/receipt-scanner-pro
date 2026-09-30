"""UI tests: run app.py headlessly with Streamlit's AppTest (no browser, no API calls)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # streamlit not installed
    AppTest = None

import processor as P  # noqa: E402


def _row(i, **extra):
    row = {
        "file_name": f"IMG_{i}.jpg",
        "vendor_name": f"ספק {i}",
        "date": "2026-09-09",
        "total_amount": 100.0 + i,
        "vat": 15.25,
        "vat_ils": 15.25,
        "currency": "ILS",
        "total_ils": 100.0 + i,
        "business_id": "514876321",
        "document_type": "tax_invoice",
        "document_number": str(1000 + i),
        "file_hash": f"hash-{i}",
    }
    row.update(extra)
    row["fingerprint"] = P.compute_fingerprint(
        row["vendor_name"], row["date"], row["total_amount"], row["currency"], row["document_number"]
    )
    return row


# In CI (GitHub sets CI=true) these tests must run, never silently skip.
@unittest.skipIf(AppTest is None and not os.environ.get("CI"), "streamlit is not installed")
class TestApp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = (P.DB_PATH, P.fetch_live_exchange_rates)
        P.DB_PATH = Path(self._tmp.name) / "receipts.db"
        P.fetch_live_exchange_rates = lambda: (dict(P.FALLBACK_RATES), True)

    def tearDown(self):
        P.DB_PATH, P.fetch_live_exchange_rates = self._old
        self._tmp.cleanup()

    def run_app(self):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.secrets["ANTHROPIC_API_KEY"] = "test-key"
        at.run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        return at

    def markdown_text(self, at):
        return "\n".join(m.value for m in at.markdown)

    def test_missing_key_shows_error(self):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.run()
        self.assertTrue(any("מפתח API" in e.value for e in at.error))

    def test_empty_state(self):
        at = self.run_app()
        self.assertIn("צלמו את הקבלות", self.markdown_text(at))

    def test_review_approve_and_report(self):
        for i in range(3):
            P.save_receipt(_row(i))
        at = self.run_app()
        text = self.markdown_text(at)
        self.assertIn("מסמך 1 מתוך 3", text)
        self.assertIn("הדוח לרואה החשבון", text)

        first_id = P.get_all_receipts()[0]["id"]
        at.button(key=f"approve_{first_id}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(P.get_all_receipts()[0]["approved"], 1)
        self.assertIn("מסמך 2 מתוך 3", self.markdown_text(at))

    def test_clear_needs_confirmation(self):
        P.save_receipt(_row(1))
        at = self.run_app()
        next(b for b in at.button if b.label == "ניקוי כל הנתונים").click().run()
        self.assertEqual(len(P.get_all_receipts()), 1)  # nothing deleted yet
        next(b for b in at.button if b.label == "כן, למחוק").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(P.get_all_receipts(), [])

    def test_untrusted_text_is_escaped(self):
        P.save_receipt(_row(1, vendor_name="<img src=x onerror=alert(1)>"))
        at = self.run_app()
        text = self.markdown_text(at)
        self.assertNotIn("<img src=x", text)
        self.assertIn("&lt;img src=x", text)


if __name__ == "__main__":
    os.environ.setdefault("RECEIPTS_DB_PATH", os.path.join(tempfile.gettempdir(), "rs-app-test.db"))
    unittest.main()
