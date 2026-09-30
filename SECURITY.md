# Security and privacy

## API key

The Anthropic API key is read **only** from Streamlit secrets. It is never typed into the UI and never hardcoded.

- Local: put it in `.streamlit/secrets.toml` (gitignored):
  ```toml
  ANTHROPIC_API_KEY = "your-api-key"
  ```
- Streamlit Community Cloud: add it under the app's **Settings → Secrets**.

If a key is ever exposed, revoke it at [console.anthropic.com](https://console.anthropic.com/) and create a new one.

## Where your data goes

```
Upload (memory) → Anthropic API (extraction) → validated fields → SQLite (receipts.db) → screen / Excel
```

- **Receipt images and PDFs** are held in memory only and are never written to disk by the app. To extract the data, they are **sent to the Anthropic API**. Anthropic's commercial terms and data retention apply.
- **Extracted fields** are stored in a local SQLite file, `receipts.db`, which is gitignored. They are the vendor, date, amounts, VAT, currency, business ID, document type and number, and approval status. Set `RECEIPTS_DB_PATH` to keep it somewhere else.
- **Exchange rates** are public data from exchangerate-api.com. No personal data is sent to that service.

## Single-user design

The app has **no login**, and everyone who opens it shares one database and your API key. Run it on your own computer, or behind authentication. Do not publish it on the open internet as is.

## Safeguards in the code

- **Duplicate detection**: an exact re-upload is detected by a SHA-256 hash of the file, before any API call. The same document from another photo is detected by its vendor, date, amount, currency and document number.
- **Validation**: the model's output is validated with Pydantic before it is stored. Every query uses SQL parameters.
- **Untrusted AI output**: everything the model returns is HTML-escaped before it is shown in the UI.
- **Prompt injection**: the extraction prompt tells the model to treat the document as data, not instructions. You still review every document before it goes into the report.
