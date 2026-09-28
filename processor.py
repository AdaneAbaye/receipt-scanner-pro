"""
Receipt Scanner Pro - Processing Logic
Handles AI analysis, validation, currency conversion, data persistence, and Excel export.
Follows professional Data Engineering standards: SQLite persistence, Pydantic validation,
SHA-256 deduplication, multi-page PDF support, and fuzzy vendor matching.
"""

import base64
import hashlib
import json
import sqlite3
import threading
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from anthropic import Anthropic
from pydantic import BaseModel, field_validator
from rapidfuzz import fuzz
import fitz  # PyMuPDF
from PIL import Image

import streamlit as st


# ============ Database Configuration ============

DB_PATH = Path(__file__).parent / "receipts.db"
_DB_LOCK = threading.Lock()


# ============ Pydantic Schema ============

class ReceiptSchema(BaseModel):
    """
    Pydantic model for validating receipt data from Claude before database persistence.
    Enforces strict types: float for amounts, date for dates. Used prior to SQLite insert.
    """

    file_name: str
    vendor_name: str
    date: date
    total_amount: float
    vat: float
    currency: str
    total_ils: float
    business_id: str
    document_type: str

    @field_validator("total_amount", "vat", "total_ils", mode="before")
    @classmethod
    def parse_float(cls, v) -> float:
        """
        Parse string or numeric amounts to float. N/A/empty become 0.0.

        Raises:
            ValueError: If value cannot be parsed to a valid float.
        """
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("₪", "").replace("$", "").replace("€", "").replace("£", "")
            if s in ("N/A", "n/a", ""):
                return 0.0
            try:
                return float(s)
            except ValueError:
                raise ValueError(f"Invalid amount: {v}")
        raise ValueError(f"Cannot parse amount: {v}")

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v) -> date:
        """
        Parse date string (YYYY-MM-DD) or date/datetime to date object.

        Raises:
            ValueError: If N/A, empty, or invalid format.
        """
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            s = v.strip()
            if s in ("N/A", "n/a", ""):
                raise ValueError("Date cannot be N/A for valid receipts")
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD")
        raise ValueError(f"Cannot parse date: {v}")

    def to_db_row(self) -> dict:
        """
        Convert schema to flat dict for database insertion.

        Returns:
            dict: Keys match receipt table columns (file_name, vendor_name, date, etc.).
        """
        return {
            "file_name": self.file_name,
            "vendor_name": self.vendor_name,
            "date": self.date.isoformat(),
            "total_amount": self.total_amount,
            "vat": self.vat,
            "currency": self.currency,
            "total_ils": self.total_ils,
            "business_id": self.business_id,
            "document_type": self.document_type,
        }


# ============ Database Layer ============

def _get_connection() -> sqlite3.Connection:
    """
    Create a connection to the SQLite database with row factory for dict-like access.

    Returns:
        sqlite3.Connection: Database connection with row_factory=sqlite3.Row.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """
    Initialize the SQLite database and create the Receipt table if it does not exist.
    Uses receipt_hash as UNIQUE constraint for O(1) deduplication.
    Thread-safe via _DB_LOCK.
    """
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS receipt (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_hash TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    vendor_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    vat REAL NOT NULL,
                    currency TEXT NOT NULL,
                    total_ils REAL NOT NULL,
                    business_id TEXT,
                    document_type TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_receipt_hash ON receipt(receipt_hash)"
            )
            conn.commit()
        finally:
            conn.close()


def insert_receipt(receipt_hash: str, data: dict) -> bool:
    """
    Insert a receipt into the database. Returns False if duplicate (hash collision).
    Thread-safe for parallel processing.

    Args:
        receipt_hash: SHA-256 fingerprint for deduplication.
        data: Validated receipt data dict.

    Returns:
        bool: True if inserted, False if duplicate.
    """
    init_database()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO receipt (
                    receipt_hash, file_name, vendor_name, date, total_amount,
                    vat, currency, total_ils, business_id, document_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_hash,
                    data["file_name"],
                    data["vendor_name"],
                    data["date"],
                    data["total_amount"],
                    data["vat"],
                    data["currency"],
                    data["total_ils"],
                    data.get("business_id", "N/A"),
                    data.get("document_type", "unknown"),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Duplicate hash
        finally:
            conn.close()


def get_all_receipts() -> List[dict]:
    """
    Retrieve all receipts from the database as list of dicts.
    Thread-safe for parallel processing.

    Returns:
        List[dict]: All receipt records with keys: file_name, vendor_name, date,
            total_amount, vat, currency, total_ils, business_id, document_type, created_at.
    """
    init_database()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """
                SELECT file_name, vendor_name, date, total_amount, vat, currency,
                       total_ils, business_id, document_type, created_at
                FROM receipt ORDER BY created_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def clear_all_receipts() -> int:
    """
    Delete all receipts from the database.
    Thread-safe for parallel processing.

    Returns:
        int: Number of rows deleted.
    """
    init_database()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            cursor = conn.execute("DELETE FROM receipt")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


def receipt_exists_by_hash(receipt_hash: str) -> bool:
    """
    Check if a receipt with the given hash already exists. O(1) lookup via unique index.
    Thread-safe for parallel processing.

    Args:
        receipt_hash: SHA-256 hex fingerprint (64 chars).

    Returns:
        bool: True if duplicate exists, False otherwise.
    """
    init_database()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM receipt WHERE receipt_hash = ?", (receipt_hash,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()


# ============ Deduplication Hashing ============

def compute_receipt_hash(vendor_name: str, date_str: str, total_amount: float) -> str:
    """
    Create a SHA-256 fingerprint for a receipt based on vendor, date, and amount.
    Used as unique constraint for O(1) duplicate detection.

    Args:
        vendor_name: Normalized vendor name. None/empty normalized to empty string.
        date_str: Date string (YYYY-MM-DD). None/empty normalized to empty string.
        total_amount: Total amount as float. NaN/inf handled via format.

    Returns:
        str: 64-character hex SHA-256 hash.
    """
    vendor = (vendor_name or "").strip().lower()
    date_part = (str(date_str) if date_str is not None else "").strip()
    try:
        amount_float = float(total_amount)
    except (TypeError, ValueError):
        amount_float = 0.0
    payload = f"{vendor}|{date_part}|{amount_float:.2f}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ============ Global Configuration ============

DOCUMENT_BLACKLIST_KEYWORDS = [
    "מכון טכנולוגי חולון",
    "HIT",
    "אישור לימודים",
    'תשפ"ה',
    'תשפ"ד',
]

ENTITY_RENAME_RULES = {
    "massvid": "Massvid",
}

# Fuzzy matching: canonical name -> list of similar substrings/patterns
FUZZY_VENDOR_MAPPINGS = {
    "Massvid": ["massvid", "masvid", "mass vid"],
    "Super-Pharm": ["superpharm", "super pharm", "סופר פארם"],
}


# ============ Exchange Rates ============

@st.cache_data(ttl=3600)
def fetch_live_exchange_rates() -> Tuple[Dict[str, float], bool]:
    """
    Fetch live exchange rates from API with 1-hour cache.

    Uses exchangerate-api.com; falls back to static rates on failure or timeout.

    Returns:
        Tuple[Dict[str, float], bool]: (rates_dict, is_live).
            rates_dict maps currency codes (ILS, USD, EUR, etc.) to ILS rate.
            is_live is False when fallback rates are used (API unavailable).
    """
    fallback_rates = {
        "ILS": 1.0,
        "₪": 1.0,
        "NIS": 1.0,
        "USD": 3.7,
        "$": 3.7,
        "EUR": 4.0,
        "€": 4.0,
        "GBP": 4.7,
        "£": 4.7,
    }

    try:
        response = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=5,
        )

        if response.status_code == 200:
            data = response.json()
            rates = data.get("rates", {})

            usd_to_ils = rates.get("ILS", 3.7)
            eur_to_usd = rates.get("EUR", 0.85)
            gbp_to_usd = rates.get("GBP", 0.73)

            live_rates = {
                "ILS": 1.0,
                "₪": 1.0,
                "NIS": 1.0,
                "USD": usd_to_ils,
                "$": usd_to_ils,
                "EUR": usd_to_ils / eur_to_usd if eur_to_usd > 0 else 4.0,
                "€": usd_to_ils / eur_to_usd if eur_to_usd > 0 else 4.0,
                "GBP": usd_to_ils / gbp_to_usd if gbp_to_usd > 0 else 4.7,
                "£": usd_to_ils / gbp_to_usd if gbp_to_usd > 0 else 4.7,
            }
            return live_rates, True
        else:
            return fallback_rates, False

    except Exception:
        return fallback_rates, False


_CURRENCY_SYMBOLS_TO_STRIP = (",", "€", "£", "₪", "$", " ", "\xa0")


def convert_to_ils(
    amount_str, currency: str, exchange_rates: Optional[Dict[str, float]] = None
) -> float:
    """
    Convert a monetary amount to Israeli Shekels (ILS).

    Args:
        amount_str: Amount as string (may include commas, currency symbols).
        currency: Currency code (e.g., USD, EUR, ILS).
        exchange_rates: Optional dict of rates. If None, fetches live rates.

    Returns:
        float: Amount in ILS, or 0.0 on parse error.
    """
    if exchange_rates is None:
        exchange_rates, _ = fetch_live_exchange_rates()

    try:
        s = str(amount_str).strip()
        for sym in _CURRENCY_SYMBOLS_TO_STRIP:
            s = s.replace(sym, "")
        s = s.replace("NIS", "").strip()
        amount = float(s)
        currency_upper = str(currency).upper().strip()
        rate = exchange_rates.get(currency_upper, 1.0)
        return amount * rate
    except (ValueError, TypeError):
        return 0.0


# ============ Vendor & Validation ============

def normalize_vendor_name(vendor_name: str) -> str:
    """
    Normalize vendor names using exact rules and fuzzy matching.
    Groups similar names (e.g., "Super Pharm" vs "Super-Pharm") for consistent reporting.

    Uses ENTITY_RENAME_RULES for exact substring matches, then FUZZY_VENDOR_MAPPINGS
    with rapidfuzz (ratio >= 85) for similar names.

    Args:
        vendor_name: Raw vendor name string from extraction.

    Returns:
        str: Normalized vendor name.
    """
    if not vendor_name or vendor_name == "N/A":
        return vendor_name

    vendor_lower = vendor_name.lower().strip()

    # 1. Exact rule-based normalization
    for pattern, canonical_name in ENTITY_RENAME_RULES.items():
        if pattern.lower() in vendor_lower:
            return canonical_name

    # 2. Fuzzy matching against known mappings
    FUZZY_THRESHOLD = 85
    for canonical_name, patterns in FUZZY_VENDOR_MAPPINGS.items():
        for pattern in patterns:
            if fuzz.ratio(vendor_lower, pattern.lower()) >= FUZZY_THRESHOLD:
                return canonical_name
            if pattern.lower() in vendor_lower:
                return canonical_name

    return vendor_name.strip()


def is_valid_receipt(receipt_data: dict) -> Tuple[bool, str, str]:
    """
    Validate receipt data as an accounting-grade financial document.

    Args:
        receipt_data: Dict from analyze_receipt_with_claude.

    Returns:
        Tuple[bool, str, str]: (is_valid, reason_code, user_message).
    """
    if not receipt_data:
        return False, "no_data", "No data received from analysis"

    is_financial = receipt_data.get("is_valid_financial_document", False)
    rejection_reason = receipt_data.get("rejection_reason", None)
    document_type = receipt_data.get("document_type", "unknown")

    if not is_financial:
        reason_map = {
            "academic_certificate": (
                "academic_document",
                "Non-accounting document rejected: Academic certificate",
            ),
            "personal_id": (
                "personal_id",
                "Non-accounting document rejected: Personal identification",
            ),
            "non_financial": (
                "non_accounting",
                "Non-accounting document rejected: Not a business transaction",
            ),
            "no_transaction_details": (
                "no_transaction",
                "Non-accounting document rejected: Missing business transaction details",
            ),
            "fine_penalty": (
                "fine_penalty",
                "Non-accounting document rejected: Fine or penalty (not deductible)",
            ),
            "parking_fine": (
                "parking_fine",
                "Non-accounting document rejected: Parking fine/ticket",
            ),
            "id_number_detected": (
                "id_number",
                "Non-accounting document rejected: Amount appears to be ID number",
            ),
        }

        if rejection_reason in reason_map:
            return False, reason_map[rejection_reason][0], reason_map[rejection_reason][1]
        return (
            False,
            "non_accounting",
            "Non-accounting document rejected: Not a valid tax invoice or business receipt",
        )

    if document_type in ["parking_ticket", "fine", "penalty"]:
        return False, "fine_penalty", "Parking fine or penalty (not a deductible business expense)"

    if rejection_reason in ["parking_fine", "penalty", "fine", "id_number_detected"]:
        return False, "fine_penalty", "Fine, penalty, or invalid document (not for accounting)"

    total_amount = receipt_data.get("total_amount", "0")
    vendor_name = receipt_data.get("vendor_name") or "N/A"
    if isinstance(vendor_name, str):
        vendor_name = vendor_name.strip() or "N/A"

    if vendor_name == "INVALID_VENDOR":
        return (
            False,
            "invalid_vendor",
            "Non-accounting document rejected: Vendor name appears to be watermark or social media handle",
        )

    # Handle None, empty, or invalid amount representations
    if total_amount in ["N/A", "n/a", "", None, "0", "0.0", "0.00"]:
        return False, "no_amount", "Non-accounting document rejected: No valid transaction amount"

    try:
        amount_str = str(total_amount).replace(",", "").replace("$", "").replace("₪", "").replace("€", "").replace("£", "").strip()
        if not amount_str:
            return False, "invalid_amount", "Non-accounting document rejected: Invalid amount format"
        amount_float = float(amount_str)
        if amount_float != amount_float:  # NaN check
            return False, "invalid_amount", "Non-accounting document rejected: Invalid amount format"

        if amount_float > 0:
            return True, "", "Valid accounting document"
        return False, "invalid_amount", "Non-accounting document rejected: Invalid amount"
    except (ValueError, TypeError):
        return False, "invalid_amount", "Non-accounting document rejected: Invalid amount format"


def is_duplicate_receipt(receipt_data: dict) -> bool:
    """
    Check if a receipt is a duplicate using SHA-256 hash (O(1) database lookup).

    Args:
        receipt_data: Validated receipt dict with vendor_name, date, total_amount.

    Returns:
        bool: True if duplicate exists in database.
    """
    if not receipt_data:
        return False

    vendor = receipt_data.get("vendor_name", "").strip()
    date_str = receipt_data.get("date", "")
    total = receipt_data.get("total_amount", 0)

    try:
        amount_float = (
            float(total)
            if isinstance(total, (int, float))
            else float(str(total).replace(",", "").replace("₪", "").replace("$", "").strip())
        )
    except (ValueError, TypeError):
        return False

    receipt_hash = compute_receipt_hash(vendor, str(date_str), amount_float)
    return receipt_exists_by_hash(receipt_hash)


# ============ Image/PDF Helpers ============

def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    Encode image bytes to base64 string for API transmission.

    Args:
        image_bytes: Raw image bytes (e.g., PNG or JPEG).

    Returns:
        str: Base64-encoded string suitable for Anthropic API image payload.
    """
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def convert_pdf_to_image(pdf_bytes: bytes) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Convert ALL pages of a PDF to a single vertically stitched PNG image.

    Iterates through every page, renders each at 2x resolution, and concatenates
    them vertically to capture multi-page invoices fully.

    Args:
        pdf_bytes: PDF file content as bytes.

    Returns:
        Tuple[Optional[bytes], Optional[str]]: (image_bytes, media_type) or (None, None) on error.
    """
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        mat = fitz.Matrix(2.0, 2.0)
        pil_images: List[Image.Image] = []

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            pil_images.append(Image.open(BytesIO(img_bytes)).convert("RGB"))

        pdf_document.close()

        if not pil_images:
            return None, None

        if len(pil_images) == 1:
            buffer = BytesIO()
            pil_images[0].save(buffer, format="PNG")
            return buffer.getvalue(), "image/png"

        # Stitch all pages vertically: use max width, sum of heights
        max_width = max(img.width for img in pil_images)
        total_height = sum(img.height for img in pil_images)

        stitched = Image.new("RGB", (max_width, total_height), (255, 255, 255))
        y_offset = 0
        for img in pil_images:
            # Center horizontally if narrower than max
            x_offset = (max_width - img.width) // 2
            stitched.paste(img, (x_offset, y_offset))
            y_offset += img.height

        buffer = BytesIO()
        stitched.save(buffer, format="PNG")
        return buffer.getvalue(), "image/png"

    except Exception:
        return None, None


def determine_media_type(file_name: str) -> str:
    """
    Determine MIME type from file extension.

    Args:
        file_name: Filename with extension (e.g., receipt.jpg, invoice.png).

    Returns:
        str: MIME type (e.g., image/jpeg, image/png). Defaults to image/jpeg if unknown.
    """
    extension = file_name.lower().split(".")[-1]
    media_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "pdf": "application/pdf",
    }
    return media_types.get(extension, "image/jpeg")


# ============ Anthropic Client ============

@st.cache_resource
def get_anthropic_client(api_key: str):
    """
    Initialize and cache the Anthropic API client. Cached per session (Streamlit).

    Args:
        api_key: Anthropic API key from secrets. Never hardcoded.

    Returns:
        Anthropic: Cached Anthropic client instance.
    """
    return Anthropic(api_key=api_key)


# ============ AI Analysis ============

def analyze_receipt_with_claude(api_key, image_bytes, file_name, exchange_rates=None):
    """
    Analyze a receipt image using Claude API for structured data extraction.

    Validates output with ReceiptSchema (Pydantic) before saving to SQLite.
    Uses SHA-256 hash for O(1) deduplication.

    Args:
        api_key: Anthropic API key (from Streamlit secrets).
        image_bytes: Receipt image or PDF (all pages stitched) as bytes.
        file_name: Original filename (used for type detection).
        exchange_rates: Optional dict for ILS conversion.

    Returns:
        dict: Extracted receipt data, or None on error.
    """
    try:
        client = get_anthropic_client(api_key)

        if file_name.lower().endswith(".pdf"):
            image_bytes, media_type = convert_pdf_to_image(image_bytes)
            if image_bytes is None:
                return None
        else:
            media_type = determine_media_type(file_name)

        base64_image = encode_image_to_base64(image_bytes)
        model_id = "claude-sonnet-4-5-20250929"

        try:
            message = client.messages.create(
                model=model_id,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_image,
                                },
                            },
                            {
                                "type": "text",
                                "text": _get_extraction_prompt(),
                            },
                        ],
                    }
                ],
            )

            response_text = message.content[0].text.strip()

            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            receipt_data = json.loads(response_text)
            receipt_data["file_name"] = file_name

            required_fields = [
                "is_valid_financial_document",
                "document_type",
                "rejection_reason",
                "vendor_name",
                "date",
                "total_amount",
                "vat",
                "currency",
                "business_id",
            ]
            for field in required_fields:
                if field not in receipt_data:
                    if field == "is_valid_financial_document":
                        receipt_data[field] = False
                    elif field == "rejection_reason":
                        receipt_data[field] = None
                    elif field == "document_type":
                        receipt_data[field] = "unknown"
                    else:
                        receipt_data[field] = "N/A"

            vendor = receipt_data.get("vendor_name", "N/A")
            vendor_prepared = vendor.title() if vendor and vendor != "N/A" else vendor
            receipt_data["vendor_name"] = normalize_vendor_name(vendor_prepared)

            forbidden_vendor_words = ["מקור", "קבלה", "תקבול", "חשבונית"]
            vendor_stripped = receipt_data["vendor_name"].strip()
            if any(word in vendor_stripped for word in forbidden_vendor_words):
                receipt_data["vendor_name"] = "Unknown Business"
            else:
                vendor_lower = receipt_data["vendor_name"].lower()
                invalid_patterns = [
                    "@",
                    "www.",
                    "http",
                    ".com",
                    ".co.",
                    ".net",
                    "telegram",
                    "whatsapp",
                    "group",
                    "קבוצ",
                    "channel",
                ]
                if any(pattern in vendor_lower for pattern in invalid_patterns):
                    receipt_data["vendor_name"] = "INVALID_VENDOR"
                    st.warning(
                        f"⚠️ Suspicious vendor detected in {file_name}: {receipt_data['vendor_name']}"
                    )

            ils_amount = convert_to_ils(
                receipt_data["total_amount"],
                receipt_data["currency"],
                exchange_rates,
            )
            receipt_data["total_ils"] = round(ils_amount, 2)

            # Pydantic validation and DB persistence (only for valid receipts)
            is_valid, _, _ = is_valid_receipt(receipt_data)
            if is_valid:
                try:
                    schema = ReceiptSchema(
                        file_name=receipt_data["file_name"],
                        vendor_name=receipt_data["vendor_name"],
                        date=receipt_data["date"],
                        total_amount=receipt_data["total_amount"],
                        vat=receipt_data["vat"],
                        currency=receipt_data["currency"],
                        total_ils=receipt_data["total_ils"],
                        business_id=receipt_data.get("business_id", "N/A"),
                        document_type=receipt_data.get("document_type", "unknown"),
                    )
                    data = schema.to_db_row()
                    data["date"] = schema.date.isoformat()
                    data["total_amount"] = schema.total_amount
                    data["vat"] = schema.vat
                    data["total_ils"] = schema.total_ils

                    receipt_hash = compute_receipt_hash(
                        data["vendor_name"],
                        data["date"],
                        data["total_amount"],
                    )
                    receipt_data["_duplicate"] = receipt_exists_by_hash(receipt_hash)
                    if not receipt_data["_duplicate"]:
                        insert_receipt(receipt_hash, data)
                except Exception as e:
                    st.warning(f"⚠️ Validation/save warning for {file_name}: {e}")
                    receipt_data["_duplicate"] = False

            return receipt_data

        except Exception as e:
            st.error(f"❌ Model error for {file_name}: {str(e)}")
            return None

    except json.JSONDecodeError as e:
        st.error(f"❌ Error parsing JSON response for {file_name}: {str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ Error analyzing {file_name}: {str(e)}")
        return None


def _get_extraction_prompt() -> str:
    """
    Return the full extraction prompt for Claude document analysis.

    Includes document triage (blacklist, parking fines, IDs), data extraction rules,
    and JSON schema. Uses DOCUMENT_BLACKLIST_KEYWORDS for dynamic rejection.

    Returns:
        str: Multi-stage prompt for document classification and field extraction.
    """
    blacklist_str = " | ".join(f'"{kw}"' for kw in DOCUMENT_BLACKLIST_KEYWORDS)
    return f"""ACCOUNTING-GRADE DOCUMENT CLASSIFIER & EXTRACTOR
================================================================
DOCUMENT TRIAGE (STEP 1 - NO EXCEPTIONS)
=========================================
If the document text contains ANY of these → Return is_valid_financial_document: false, rejection_reason: "academic_certificate".
Do NOT extract any data. Set vendor_name, date, total_amount, vat, currency, business_id ALL to "N/A".

🚫 DOCUMENT BLACKLIST - IMMEDIATE REJECTION:
   {blacklist_str}
   No exceptions. If ANY of these appear → academic_certificate

2. PARKING FINES & PENALTIES:
   Keywords: "דוח חניה", "דו"ח", "קנס", "Parking Violation", "Fine", "Penalty"
   Reason: "parking_fine"

3. PERSONAL IDs:
   Keywords: "תעודת זהות", "דרכון", "רישיון", "ID Card", "Passport"
   Reason: "personal_id"

4. 9-DIGIT CONTEXTUAL ANALYSIS (Smart ID Fix):
   If you see a 9-digit number, perform CONTEXTUAL ANALYSIS:
   - If it is near labels like "ID", "ת.ז", "Identity", "תעודת זהות" → mark is_valid_financial_document: false, rejection_reason: "id_number_detected". Do NOT extract as total_amount.
   - If a 9-digit number is clearly at the bottom next to "Total", "סה"כ", "סה"כ לתשלום", or similar payment-total labels, and the document is a valid invoice/receipt → extract it as total_amount and do NOT reject it. High-value transactions are valid.

⚠️ FOR REJECTED FILES: Return ONLY validity and reason. ALL other fields = "N/A":
{{
    "is_valid_financial_document": false,
    "rejection_reason": "academic_certificate",
    "vendor_name": "N/A",
    "date": "N/A",
    "total_amount": "N/A",
    "vat": "0",
    "currency": "N/A",
    "business_id": "N/A"
}}

✅ ACCEPT ONLY: Tax invoices, purchase receipts, service invoices with payment proof.

STAGE 2: DATA EXTRACTION (Only if Stage 1 = ACCEPT)
====================================================

4. Vendor Name (Final Total Logic):
   IGNORE "מקור" or "קבלה" - these are structural labels, NOT vendors.
   Extract ONLY the business entity name (e.g., "Sample Business", "the entity").
   Look near "ח.פ" or "עוסק מורשה" for the legal business name.

5. Date: Transaction date only (YYYY-MM-DD). NOT due dates.

6. Total Amount (Final Total Logic):
   Prioritize the ABSOLUTE FINAL PAYABLE TOTAL at the bottom of the document.
   IGNORE individual item prices (e.g., 74.50). Use "סה"כ לתשלום" or "Total" labeled value.

7. VAT/Tax (Final Total Logic):
   If "עוסק פטור" appears anywhere → VAT is 0.
   Else: Extract the currency amount next to the 17% label (e.g., 21.65 for the entity).
   Do NOT guess or calculate. Only extract if explicitly written. No amount → "0"

8. Currency (e.g., USD, EUR, ILS, NIS, ₪, etc.)

9. Business ID (if available - use "INTERNATIONAL" for international receipts)

Return ONLY a valid JSON object with these exact keys:
{{
    "is_valid_financial_document": true or false,
    "document_type": "invoice" / "receipt" / "bill" / "parking_ticket" / "unknown",
    "rejection_reason": "academic_certificate" / "personal_id" / "non_financial" / "no_transaction_details" / "id_number_detected" / null,
    "vendor_name": "Formal Business Entity Name",
    "date": "2024-01-15",
    "total_amount": "150.00",
    "vat": "25.50",
    "currency": "USD",
    "business_id": "123456789" or "INTERNATIONAL" or "N/A"
}}

Return ONLY the JSON, no additional text or explanation."""


# ============ Excel Export ============

def create_excel_download(df: pd.DataFrame) -> bytes:
    """
    Create an Excel file with receipt data and proper formatting.

    Args:
        df: DataFrame with receipt columns (file_name, vendor_name, etc.).

    Returns:
        bytes: Excel file content as bytes for download.
    """
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Receipts")
        workbook = writer.book
        worksheet = writer.sheets["Receipts"]

        header_format = workbook.add_format(
            {
                "bold": True,
                "text_wrap": True,
                "valign": "top",
                "fg_color": "#0E7490",
                "font_color": "white",
                "border": 1,
            }
        )

        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        worksheet.set_column("A:A", 30)
        worksheet.set_column("B:B", 25)
        worksheet.set_column("C:C", 15)
        worksheet.set_column("D:D", 15)
        worksheet.set_column("E:E", 12)
        worksheet.set_column("F:F", 12)
        worksheet.set_column("G:G", 12)

    output.seek(0)
    return output.getvalue()
