"""Unit tests for processor.py: parsing, validation, duplicates, VAT, storage and the Excel report."""

import datetime as dt
import json
import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import processor as P

RATES = {"ILS": 1.0, "USD": 3.7, "EUR": 4.0, "JPY": 0.025}


class FakeClient:
    """Stands in for the Anthropic client; returns a canned reply and counts calls."""

    def __init__(self, reply):
        self.calls = 0
        self.reply = reply
        self.messages = self

    def create(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(text=self.reply)])


def reply(**overrides) -> str:
    data = {
        "is_valid_financial_document": True,
        "rejection_reason": None,
        "document_type": "tax_invoice_receipt",
        "vendor_name": "משרדית ציוד משרדי",
        "date": "2026-09-09",
        "total_amount": "186.50",
        "vat": "28.45",
        "currency": "ILS",
        "business_id": "514876321",
        "document_number": "20931",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def png_bytes(size=(40, 60)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


class TempDbTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_path = P.DB_PATH
        P.DB_PATH = Path(self._tmp.name) / "receipts.db"

    def tearDown(self):
        P.DB_PATH = self._old_path
        self._tmp.cleanup()

    def analyze(self, text, file_bytes=None, name="r.jpg"):
        client = FakeClient(text)
        result = P.analyze_receipt_with_claude("key", file_bytes or png_bytes(), name, RATES, client=client)
        return result, client


class TestParsing(unittest.TestCase):
    def test_parse_amount(self):
        cases = {
            "₪1,234.50": 1234.5,
            "1.234,56": 1234.56,
            "12,5": 12.5,
            "1,234": 1234.0,
            "-40.00": -40.0,
            186: 186.0,
            "N/A": None,
            "": None,
            None: None,
            True: None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(P.parse_amount(raw), expected)

    def test_normalize_currency(self):
        self.assertEqual(P.normalize_currency("₪"), "ILS")
        self.assertEqual(P.normalize_currency("nis"), "ILS")
        self.assertEqual(P.normalize_currency("$"), "USD")
        self.assertEqual(P.normalize_currency("jpy"), "JPY")
        self.assertIsNone(P.normalize_currency("N/A"))
        self.assertIsNone(P.normalize_currency(None))

    def test_dates_are_day_first(self):
        self.assertEqual(P.parse_receipt_date("03/04/2026"), dt.date(2026, 4, 3))
        self.assertEqual(P.parse_receipt_date("2026-04-03"), dt.date(2026, 4, 3))
        self.assertEqual(P.parse_receipt_date("03.04.26"), dt.date(2026, 4, 3))
        with self.assertRaises(ValueError):
            P.parse_receipt_date("N/A")

    def test_extract_json_with_surrounding_text(self):
        self.assertEqual(P.extract_json_object('Here it is:\n```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            P.extract_json_object("no json here")


class TestVendors(unittest.TestCase):
    def test_real_businesses_are_kept(self):
        for name in ["Amazon.com", "Delek Group", "Wix.com", "מקורות", "Booking.com"]:
            with self.subTest(name=name):
                self.assertEqual(P.clean_vendor_name(name), name)

    def test_labels_and_handles_are_not_vendors(self):
        for name in ["קבלה", "מקור", "חשבונית מס", "@somechannel", "https://t.me/x", None, ""]:
            with self.subTest(name=name):
                self.assertEqual(P.clean_vendor_name(name), P.UNKNOWN_VENDOR)

    def test_fuzzy_mapping(self):
        self.assertEqual(P.clean_vendor_name("SUPER PHARM"), "Super-Pharm")


class TestValidation(unittest.TestCase):
    def test_rejected_document(self):
        ok, code, _ = P.is_valid_receipt({"is_valid_financial_document": False, "rejection_reason": "personal_id"})
        self.assertFalse(ok)
        self.assertEqual(code, "personal_id")

    def test_amounts(self):
        base = {"is_valid_financial_document": True, "document_type": "receipt"}
        self.assertFalse(P.is_valid_receipt({**base, "total_amount": "0"})[0])
        self.assertFalse(P.is_valid_receipt({**base, "total_amount": "N/A"})[0])
        self.assertFalse(P.is_valid_receipt({**base, "total_amount": "-20"})[0])
        self.assertTrue(P.is_valid_receipt({**base, "document_type": "credit_note", "total_amount": "-20"})[0])
        self.assertTrue(P.is_valid_receipt({**base, "total_amount": "18.00"})[0])

    def test_parking_fine(self):
        ok, code, _ = P.is_valid_receipt(
            {"is_valid_financial_document": True, "document_type": "parking_ticket", "total_amount": "100"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, "fine_penalty")


class TestVat(unittest.TestCase):
    base = {"document_type": "tax_invoice", "currency": "ILS", "business_id": "514876321", "vat": 28.45}

    def test_tax_invoice_is_reclaimable(self):
        self.assertTrue(P.is_vat_reclaimable(self.base))
        self.assertTrue(P.is_vat_reclaimable({**self.base, "document_type": "tax_invoice_receipt"}))

    def test_not_reclaimable(self):
        cases = {
            "plain receipt": {"document_type": "receipt"},
            "foreign currency": {"currency": "USD"},
            "no business id": {"business_id": None},
            "short business id": {"business_id": "1234"},
            "zero vat": {"vat": 0},
        }
        for label, change in cases.items():
            with self.subTest(label):
                self.assertFalse(P.is_vat_reclaimable({**self.base, **change}))


class TestCurrency(unittest.TestCase):
    def test_build_rates_from_usd_base(self):
        rates = P.build_ils_rates({"USD": 1, "ILS": 3.7, "EUR": 0.925, "JPY": 148})
        self.assertEqual(rates["ILS"], 1.0)
        self.assertAlmostEqual(rates["USD"], 3.7)
        self.assertAlmostEqual(rates["EUR"], 4.0)
        self.assertAlmostEqual(rates["JPY"], 0.025, places=4)

    def test_convert(self):
        self.assertEqual(P.convert_to_ils("24.00", "USD", RATES), 88.8)
        self.assertEqual(P.convert_to_ils("1000", "JPY", RATES), 25.0)
        self.assertEqual(P.convert_to_ils("1.234,56", "EUR", RATES), 4938.24)
        self.assertIsNone(P.convert_to_ils("100", "XYZ", RATES))  # unknown currency is not shekels
        self.assertIsNone(P.convert_to_ils("100", "N/A", RATES))


class TestStorage(TempDbTestCase):
    def test_saved_with_numeric_business_id(self):
        result, _ = self.analyze(reply(business_id=514876321))
        self.assertEqual(result["_status"], P.STATUS_SAVED)
        self.assertEqual(P.get_all_receipts()[0]["business_id"], "514876321")

    def test_null_fields_do_not_lose_the_receipt(self):
        result, _ = self.analyze(reply(vendor_name=None, document_type=None, business_id=None, document_number=None))
        self.assertEqual(result["_status"], P.STATUS_SAVED)
        row = P.get_all_receipts()[0]
        self.assertEqual(row["vendor_name"], P.UNKNOWN_VENDOR)
        self.assertEqual(row["document_type"], "unknown")

    def test_same_file_twice_skips_the_api(self):
        data = png_bytes()
        self.analyze(reply(), file_bytes=data)
        result, client = self.analyze(reply(), file_bytes=data)
        self.assertEqual(result["_status"], P.STATUS_DUPLICATE)
        self.assertEqual(client.calls, 0)
        self.assertEqual(len(P.get_all_receipts()), 1)

    def test_two_coffees_with_different_numbers_are_both_kept(self):
        coffee = dict(vendor_name="קפה המרפסת", total_amount="18.00", vat="2.75")
        first, _ = self.analyze(reply(**coffee, document_number="1001"), file_bytes=png_bytes((40, 60)))
        second, _ = self.analyze(reply(**coffee, document_number="1002"), file_bytes=png_bytes((41, 60)))
        self.assertEqual(first["_status"], P.STATUS_SAVED)
        self.assertEqual(second["_status"], P.STATUS_SAVED)
        self.assertEqual(len(P.get_all_receipts()), 2)

    def test_same_document_number_from_another_photo_is_a_duplicate(self):
        self.analyze(reply(), file_bytes=png_bytes((40, 60)))
        result, _ = self.analyze(reply(), file_bytes=png_bytes((42, 60)))
        self.assertEqual(result["_status"], P.STATUS_DUPLICATE)

    def test_no_document_number_is_flagged_not_dropped(self):
        self.analyze(reply(document_number=None), file_bytes=png_bytes((40, 60)))
        result, _ = self.analyze(reply(document_number=None), file_bytes=png_bytes((43, 60)))
        self.assertEqual(result["_status"], P.STATUS_POSSIBLE_DUPLICATE)
        rows = P.get_all_receipts()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["possible_duplicate"], 1)

    def test_rejected_and_errors(self):
        rejected, _ = self.analyze(reply(is_valid_financial_document=False, rejection_reason="academic_certificate"))
        self.assertEqual(rejected["_status"], P.STATUS_REJECTED)
        unknown, _ = self.analyze(reply(currency="XYZ"), file_bytes=png_bytes((44, 60)))
        self.assertEqual(unknown["_status"], P.STATUS_ERROR)
        broken, _ = self.analyze("sorry, I can't read this", file_bytes=png_bytes((45, 60)))
        self.assertEqual(broken["_status"], P.STATUS_ERROR)
        self.assertEqual(P.get_all_receipts(), [])

    def test_foreign_invoice_converted_at_scan_time(self):
        self.analyze(reply(vendor_name="CloudHost", currency="USD", total_amount="24.00", vat="0",
                           business_id="INTERNATIONAL", document_type="invoice"))
        row = P.get_all_receipts()[0]
        self.assertEqual(row["total_ils"], 88.8)
        self.assertEqual(row["vat_ils"], 0.0)
        self.assertFalse(P.is_vat_reclaimable(row))

    def test_approve_and_clear(self):
        self.analyze(reply())
        row = P.get_all_receipts()[0]
        P.set_receipt_approved(row["id"])
        self.assertEqual(P.get_all_receipts()[0]["approved"], 1)
        self.assertEqual(P.clear_all_receipts(), 1)
        self.assertEqual(P.get_all_receipts(), [])

    def test_old_database_is_migrated(self):
        import sqlite3

        conn = sqlite3.connect(P.DB_PATH)
        conn.execute(
            """CREATE TABLE receipt (id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_hash TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL, vendor_name TEXT NOT NULL, date TEXT NOT NULL, total_amount REAL NOT NULL,
            vat REAL NOT NULL, currency TEXT NOT NULL, total_ils REAL NOT NULL, business_id TEXT,
            document_type TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"""
        )
        conn.execute(
            "INSERT INTO receipt (receipt_hash, file_name, vendor_name, date, total_amount, vat, currency, total_ils)"
            " VALUES ('h', 'old.jpg', 'Old', '2025-01-01', 10, 1.5, 'ILS', 10)"
        )
        conn.commit()
        conn.close()
        rows = P.get_all_receipts()
        self.assertEqual(rows[0]["vendor_name"], "Old")
        self.assertEqual(rows[0]["approved"], 0)
        self.assertIn("vat_ils", rows[0])


class TestImages(unittest.TestCase):
    def test_large_photo_is_downscaled(self):
        buf = BytesIO()
        Image.new("RGB", (4000, 3000), "white").save(buf, "PNG")
        data, media_type = P.prepare_image(buf.getvalue(), "image/png")
        self.assertEqual(media_type, "image/jpeg")
        self.assertLessEqual(max(Image.open(BytesIO(data)).size), P.MAX_IMAGE_SIDE)

    def test_phone_rotation_is_applied(self):
        img = Image.new("RGB", (60, 40), "white")
        exif = img.getexif()
        exif[0x0112] = 6  # rotated 90°
        buf = BytesIO()
        img.save(buf, "JPEG", exif=exif.tobytes())
        data, _ = P.prepare_image(buf.getvalue(), "image/jpeg")
        self.assertEqual(Image.open(BytesIO(data)).size, (40, 60))

    def test_small_image_untouched(self):
        data = png_bytes()
        self.assertEqual(P.prepare_image(data, "image/png"), (data, "image/png"))

    def test_pdf_goes_as_document(self):
        block = P.build_document_block(b"%PDF-1.4 test", "invoice.pdf")
        self.assertEqual(block["type"], "document")
        self.assertEqual(block["source"]["media_type"], "application/pdf")


class TestExcel(unittest.TestCase):
    def test_report(self):
        rows = [
            {"date": "2026-09-09", "vendor_name": "משרדית", "business_id": "514876321", "document_type": "tax_invoice",
             "document_number": "20931", "currency": "ILS", "total_amount": 186.5, "vat": 28.45, "total_ils": 186.5,
             "vat_ils": 28.45, "file_name": "a.jpg"},
            {"date": "2026-09-02", "vendor_name": "CloudHost", "business_id": "INTERNATIONAL", "document_type": "invoice",
             "document_number": None, "currency": "USD", "total_amount": 24.0, "vat": 0, "total_ils": 88.8,
             "vat_ils": 0.0, "file_name": "b.pdf"},
        ]
        data = P.create_excel_download(rows)
        with zipfile.ZipFile(BytesIO(data)) as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
            strings = z.read("xl/sharedStrings.xml").decode()
        self.assertIn('rightToLeft="1"', sheet)
        self.assertIn("SUM(L2:L3)", sheet)
        self.assertIn("חשבונית מס", strings)
        self.assertLess(strings.index("CloudHost"), strings.index("משרדית"))  # sorted by date

    def test_text_from_receipts_never_becomes_a_formula(self):
        evil = '=HYPERLINK("http://evil.example","click")'
        rows = [{"date": "2026-09-09", "vendor_name": evil, "business_id": "1", "document_type": "receipt",
                 "currency": "ILS", "total_amount": 10, "vat": 0, "total_ils": 10, "file_name": "=1+1.jpg"}]
        with zipfile.ZipFile(BytesIO(P.create_excel_download(rows))) as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertNotIn("HYPERLINK", sheet)  # stored as a shared string, not a <f> formula
        self.assertNotIn("<f>1+1</f>", sheet)


class TestErrors(unittest.TestCase):
    def test_api_errors_are_friendly(self):
        msg = P._friendly_api_error(RuntimeError("Error code: 401 authentication_error invalid x-api-key"))
        self.assertIn("ANTHROPIC_API_KEY", msg)
        self.assertNotIn("x-api-key", msg)
        self.assertNotIn("boom", P._friendly_api_error(ValueError("boom secret details")))


if __name__ == "__main__":
    os.environ.setdefault("RECEIPTS_DB_PATH", os.path.join(tempfile.gettempdir(), "rs-test.db"))
    unittest.main()
