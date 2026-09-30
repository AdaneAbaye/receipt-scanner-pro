# 🧾 Receipt Scanner Pro

**For Israeli freelancers and small businesses (עוסק מורשה) who need to get their receipts to their accountant.**
Photograph receipts and invoices on your phone or upload them from your computer. Claude AI extracts the details, you approve each document, and you download a tidy Excel report for your accountant.

## Screenshots

![Review: the original receipt next to the fields the AI extracted](docs/screenshots/review.png)
![The report for the accountant: VAT paid, totals, all documents and spending breakdown](docs/screenshots/summary.png)
![On a phone: photograph a receipt, then review and approve it](docs/screenshots/mobile.png)

*Screenshots use sample data.*

## How it works

1. **Upload**: photograph receipts with your phone's camera or upload JPG, PNG or PDF files, several at once.
2. **AI extraction**: each document is analyzed in parallel with Claude. The app extracts:
   - vendor
   - date
   - total
   - VAT (מע"מ)
   - currency
   - business ID (ע.מ / ח.פ)
   - document type
3. **Review**: the original image is shown next to the extracted fields. Approve each document or skip it.
4. **Report for the accountant**: the report shows VAT paid, total expenses, a table of every document, and spending by vendor. Download it as Excel.

## Features

- **Hebrew-first, right-to-left interface** that works on desktop and mobile.
- **Totals in shekels**: foreign-currency amounts are converted to ILS using live exchange rates, cached hourly. If the rate service is unavailable, a fixed fallback rate is used.
- **Duplicate detection**: a SHA-256 fingerprint of vendor, date and amount stops the same receipt from being counted twice.
- **Filters out non-business documents**, such as certificates and school documents, before they reach the report.
- **Local storage**: the extracted data is validated with Pydantic and stored in a local SQLite database (`receipts.db`, gitignored).
- **Multi-page PDFs**: every page is converted to an image and stitched together with PyMuPDF.

## Setup

Requires Python 3.9+ and an [Anthropic API key](https://console.anthropic.com/).

```bash
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` (it is gitignored):

```toml
ANTHROPIC_API_KEY = "your-api-key"
```

For Streamlit Community Cloud, add the key in the app's Secrets settings instead.

Then run:

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. To use it from your phone, open the same address on your local network (`http://<your-computer-ip>:8501`).

## Privacy

- Receipt images are sent to the Anthropic API for extraction. Only the extracted fields are stored, locally, in `receipts.db`.
- The app is designed for **one user on their own computer**. Do not deploy it publicly as-is: every visitor would share the same database and your API key.

## Tech stack

Streamlit · Anthropic Claude · Pandas · Plotly · PyMuPDF · Pydantic · SQLite · XlsxWriter · RapidFuzz

## License

MIT, see [LICENSE](LICENSE).
