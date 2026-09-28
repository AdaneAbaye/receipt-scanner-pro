# 🧾 Receipt Scanner Pro

A professional Streamlit application for scanning and analyzing receipts using Claude 4.5 AI.

## Screenshots

<!-- Add screenshots to docs/screenshots/ and uncomment:
![Upload and scan](docs/screenshots/upload.png)
![Spending analytics](docs/screenshots/analytics.png)
-->

## Features

✨ **Key Features:**
- 📤 Multi-file upload support (JPG, PNG, PDF)
- 🤖 AI-powered receipt analysis using Claude 4.5
- 📊 Real-time data extraction and display with interactive visualizations
- 💰 Smart VAT detection (supports Hebrew מע"מ, English VAT, and more)
- 📈 Interactive pie charts and bar graphs for spending analysis
- 📥 Excel export with Hebrew character support
- 🎨 Modern, clean UI with bilingual support
- ⚡ Optimized performance with client caching
- 🗑️ Easy data management with clear button

**Extracted Data:**
- Vendor Name (automatically normalized)
- Date
- Total Amount
- VAT/Tax (with aggressive Hebrew/English detection)
- Currency
- Total in ILS (automatically converted)

**Smart Features:**
- 💱 **Live Currency Conversion**: Real-time exchange rates via API (cached hourly, with fallback to 1 USD = 3.7 ILS)
- 📊 **Rate Display**: Current exchange rates visible in sidebar (USD→ILS, EUR→ILS)
- 🏷️ **Vendor Normalization**: Standardizes vendor names with fuzzy matching (e.g., "MASSVID.COM" → "Massvid")
- 🚫 **Document Filtering**: Automatically skips non-receipt documents (certificates, etc.)
- 📈 **ILS-based Analytics**: All charts and totals use live ILS conversion for accurate comparison
- 🔍 **Enhanced VAT Detection**: Finds VAT/מע"מ even in complex layouts (e.g., "17%: 21.65")
- ⚡ **Performance Optimized**: @st.cache_resource for Anthropic client, @st.cache_data for currency API
- 🔐 **SHA-256 Deduplication**: O(1) duplicate detection via receipt fingerprint (vendor + date + amount)
- ⚡ **Parallel Processing**: ThreadPoolExecutor for concurrent API calls when multiple files are uploaded

**PDF Handling:**
- PDFs are automatically converted to images using PyMuPDF
- All pages are stitched vertically into a single image for multi-page invoices
- No external dependencies required (PyMuPDF is self-contained)

**Data Persistence:**
- Extracted metadata stored in local SQLite database (`receipts.db`)
- Pydantic validation before persistence

## Installation

1. **Clone or download this project**

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

## Setup

1. **Get your Anthropic API Key:**
   - Visit [console.anthropic.com](https://console.anthropic.com/)
   - Sign up or log in
   - Navigate to API Keys section
   - Create a new API key

2. **Configure API Key (Secure Method - Recommended):**

Create a `.streamlit/secrets.toml` file in your project root:

```toml
ANTHROPIC_API_KEY = "your-actual-api-key-here"
```

**Important Security Notes:**
- ✅ The `.streamlit/secrets.toml` file is already in `.gitignore`
- ✅ Never commit this file to version control
- ✅ Never share your API key publicly
- ⚠️ For Streamlit Cloud deployment, add secrets via the dashboard instead

**Alternative:** If you don't create the secrets file, you can enter the API key manually in the sidebar (less secure).

3. **Run the application:**
```bash
streamlit run app.py
```

4. **Open in browser:**
   - The app will automatically open in your default browser
   - If not, navigate to `http://localhost:8501`
   
5. **Verify in Sidebar:**
   You should see:
   ```
   ✅ API Key loaded from secrets
   Using secure API key from .streamlit/secrets.toml
   ```

## Usage

1. **Enter API Key** - Paste your Anthropic API key in the sidebar
2. **Upload Receipts** - Click 'Browse files' and select one or more receipts
3. **Analyze** - Click 'Analyze Receipts' to process with AI
4. **Review** - Check the extracted data in the table
5. **Download** - Export results to Excel format

## Supported File Formats

- JPG/JPEG images
- PNG images
- PDF files (all pages stitched)

## Requirements

- Python 3.8+
- Streamlit
- Anthropic API
- Pandas
- XlsxWriter
- PyMuPDF (for PDF conversion)
- Pillow
- Plotly (for interactive charts)
- Requests (for live currency rates)
- Pydantic (for data validation)
- RapidFuzz (for fuzzy vendor matching)

## Error Handling

The app includes comprehensive error handling for:
- Invalid API keys
- Unsupported file formats
- API call failures
- JSON parsing errors
- File read errors

## Notes

- Multiple receipts are processed in parallel for faster analysis
- Results are displayed in real-time and persisted to SQLite
- Excel exports include proper formatting for Hebrew text
- Receipt images/PDFs are processed in-memory only; only extracted metadata is stored locally

## Support

For issues or questions:
- Check the Anthropic API documentation
- Verify your API key is valid
- Ensure uploaded files are clear and readable

## License

This project is provided as-is for educational and commercial use.

---

**Powered by Claude 4.5 (claude-sonnet-4-5-20250929) 🤖**

