# Security Best Practices

## 🔐 API Key Security

### Local Development

**Required:** Create `.streamlit/secrets.toml` file:

```toml
# .streamlit/secrets.toml
ANTHROPIC_API_KEY = "your-actual-api-key-here"
```

**Security Checklist:**
- ✅ `.streamlit/secrets.toml` is already in `.gitignore`
- ✅ Never commit API keys to version control
- ✅ Never share API keys publicly
- ✅ Rotate keys regularly
- ✅ Use separate keys for development and production

### Production Deployment (Streamlit Cloud)

1. Go to your app dashboard on Streamlit Cloud
2. Click on "⚙️ Settings"
3. Navigate to "Secrets" section
4. Add your secret:
   ```toml
   ANTHROPIC_API_KEY = "your-production-api-key"
   ```
5. Save and restart the app

## 🛡️ Data Security

### File Handling
- ✅ **Receipt images and PDFs are processed strictly in-memory** using `BytesIO`
- ✅ **Original receipt files are never saved to disk**
- ✅ **Uploaded files exist only in memory during analysis** and are discarded after processing

### Extracted Metadata Storage
- Extracted metadata (Vendor, Date, Amount, VAT, Currency, etc.) is stored in a **local SQLite database** (`receipts.db`) for persistence
- This allows the app to retain receipt data across sessions without storing the original images
- The database file is in the project directory and is listed in `.gitignore` to avoid accidental commits

### Data Flow
```
User Upload → Memory (BytesIO) → Claude API → JSON Response → SQLite (receipts.db) → Charts
```

**Original receipt images/PDFs:**
- Processed in-memory only
- Never saved to disk
- Discarded after extraction completes

**Extracted metadata:**
- Stored locally in `receipts.db`
- Persists across sessions until user clears data

## 🔒 Privacy

### What is Processed
- Receipt images (temporary, in-memory only—never written to disk)
- Extracted text data (vendor, date, amount, VAT)
- Currency conversion rates (public data)

### What is Stored Locally
- Extracted metadata only (vendor name, date, amount, VAT, currency, etc.) in `receipts.db`

### What is NOT Stored
- Original receipt images or PDF files
- User personal information
- Payment card details

## 🚨 Security Warnings

**DO NOT:**
- ❌ Commit `.streamlit/secrets.toml` to Git
- ❌ Share your API key in screenshots
- ❌ Use production keys in development
- ❌ Store sensitive data in the app

**DO:**
- ✅ Use secrets management for API keys
- ✅ Review `.gitignore` before commits
- ✅ Rotate API keys regularly
- ✅ Monitor API usage for anomalies

## 📋 Audit Trail

The app includes:
- ✅ SHA-256 duplicate detection (prevents re-processing of identical receipts)
- ✅ Business ID validation (ensures data quality)
- ✅ Error handling and logging
- ✅ Thread-safe SQLite persistence for concurrent processing

## 🔄 Updates

To update your API key:

**Local:**
1. Edit `.streamlit/secrets.toml`
2. Restart Streamlit app

**Production:**
1. Update secrets in Streamlit Cloud dashboard
2. App automatically restarts

## ⚠️ Incident Response

If you suspect your API key is compromised:

1. **Immediately revoke** the key at [console.anthropic.com](https://console.anthropic.com/)
2. **Generate** a new API key
3. **Update** your secrets file
4. **Monitor** API usage for unauthorized requests
5. **Review** recent activity logs

---

**Last Updated:** January 2026  
**Version:** 1.0

