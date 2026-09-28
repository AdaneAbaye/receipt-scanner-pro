import html

import streamlit as st
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Processing logic (modular)
from processor import (
    fetch_live_exchange_rates,
    convert_to_ils,
    is_valid_receipt,
    analyze_receipt_with_claude,
    convert_pdf_to_image,
    create_excel_download,
    get_all_receipts,
    clear_all_receipts,
)

# Multilingual UI strings (internal preparation; Hebrew preserved for end-user experience)
UI_STRINGS = {
    'en': {
        'app_title': '🧾 Receipt Scanner Pro',
        'page_title': 'Receipt Scanner Pro',
        'api_config': '🔑 API Configuration',
        'api_key_label': 'Anthropic API Key',
        'api_key_help': 'Enter your Anthropic API key to use Claude AI',
        'exchange_rates': '💱 Exchange Rates',
        'live_rates': '✅ Live rates (updated hourly)',
        'fallback_rates': '⚠️ Using fallback rates (API unavailable)',
        'current_rate': 'Current Rate',
        'view_all_rates': '📊 View all rates',
        'rates_cached': 'Rates cached for 1 hour',
        'instructions': '📖 Instructions',
        'clear_data': '🗑️ Clear All Data',
        'upload_receipts': '📤 Upload Receipts',
        'analyze_receipts': '🔍 Analyze Receipts',
        'extracted_data': '📊 Extracted Receipt Data',
        'download_excel': '📥 Download Excel Report',
        'summary': '📈 Summary',
        'total_receipts': 'Total Receipts',
        'total_amount_ils': 'Total Amount (ILS)',
        'unique_vendors': 'Unique Vendors',
        'total_vat': 'Total Recoverable VAT',
        'visual_analytics': '📊 Visual Analytics (All amounts in ILS)',
        'spending_by_vendor': '💰 Spending by Vendor (ILS)',
        'amount_by_vendor': '📊 Amount by Vendor (ILS)',
        'vat_analysis': '💳 VAT/Tax Analysis (ILS)',
        'duplicate_warning': '⚠️ Duplicate receipt detected',
        'success_processed': '✅ Successfully processed: {}',
        'failed_processed': '❌ Failed to process: {}',
        'data_cleared': '✅ All data cleared!',
    },
    'he': {
        'app_title': '🧾 סורק קבלות מקצועי',
        'page_title': 'סורק קבלות מקצועי',
        'api_config': '🔑 הגדרות API',
        'api_key_label': 'מפתח API של Anthropic',
        'api_key_help': 'הזן את מפתח ה-API שלך לשימוש ב-Claude AI',
        'exchange_rates': '💱 שערי המרה',
        'live_rates': '✅ שערים חיים (מתעדכן כל שעה)',
        'fallback_rates': '⚠️ שימוש בשערים קבועים (API לא זמין)',
        'current_rate': 'שער נוכחי',
        'view_all_rates': '📊 צפה בכל השערים',
        'rates_cached': 'שערים שמורים למשך שעה',
        'instructions': '📖 הוראות שימוש',
        'clear_data': '🗑️ נקה את כל הנתונים',
        'upload_receipts': '📤 העלאת קבלות',
        'analyze_receipts': '🔍 נתח קבלות',
        'extracted_data': '📊 נתוני קבלות שחולצו',
        'download_excel': '📥 הורד דוח Excel',
        'summary': '📈 סיכום',
        'total_receipts': 'סה"כ קבלות',
        'total_amount_ils': 'סה"כ סכום (שקלים)',
        'unique_vendors': 'ספקים ייחודיים',
        'total_vat': 'סה"כ מע"מ להחזר',
        'visual_analytics': '📊 ניתוח ויזואלי (כל הסכומים בשקלים)',
        'spending_by_vendor': '💰 הוצאות לפי ספק (שקלים)',
        'amount_by_vendor': '📊 סכום לפי ספק (שקלים)',
        'vat_analysis': '💳 ניתוח מע"מ (שקלים)',
        'duplicate_warning': '⚠️ קבלה כפולה התגלתה',
        'success_processed': '✅ עובד בהצלחה: {}',
        'failed_processed': '❌ נכשל בעיבוד: {}',
        'data_cleared': '✅ כל הנתונים נוקו!',
    }
}

# Current display language ('en' or 'he'); Hebrew UI strings preserved in UI_STRINGS
CURRENT_LANG = 'he'

def get_text(key: str) -> str:
    """
    Return UI text for the given key in the current language.

    Args:
        key: Key to look up in UI_STRINGS (e.g. 'app_title', 'upload_receipts').

    Returns:
        str: Localized string for the key, or the key itself if not found.
    """
    return UI_STRINGS[CURRENT_LANG].get(key, key)

# Page configuration
st.set_page_config(
    page_title=get_text('page_title'),
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Design tokens (white "review desk" theme)
# ---------------------------------------------------------------------------
ACCENT = "#0E7490"
FIELD_COLORS = {
    "vendor": "#1D4ED8",
    "date": "#BE185D",
    "vat": "#B45309",
    "total": "#15803D",
}
DOC_TYPE_LABELS = {
    "receipt": "קבלה",
    "invoice": "חשבונית",
    "tax_invoice": "חשבונית מס",
    "tax_invoice_receipt": "חשבונית מס קבלה",
    "credit_note": "חשבונית זיכוי",
}
CHART_COLORS = ["#0E7490", "#1D4ED8", "#B45309", "#BE185D", "#15803D", "#6D28D9", "#64748B"]

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    /* Hide Streamlit chrome */
    #MainMenu, footer, header {{visibility: hidden;}}
    .stDeployButton, [data-testid="stToolbarIcon"], [data-testid="stHeaderDecorator"],
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {{display: none;}}

    html, body, .stApp, .stApp * {{font-family: 'Rubik', sans-serif;}}
    .stApp {{background: #FFFFFF; color: #111827;}}
    .block-container {{direction: rtl; max-width: 1280px; padding: 1.5rem 2.5rem 3rem;}}
    h1, h2, h3, p, label {{text-align: right;}}

    /* Header + stepper */
    .rs-header {{display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 8px;}}
    .rs-brand {{display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 700;}}
    .rs-logo {{width: 38px; height: 38px; border-radius: 10px; background: {ACCENT}; display: flex; align-items: center; justify-content: center;}}
    .rs-steps {{margin: 0; padding: 0; list-style: none; display: flex; align-items: center; gap: 10px; font-size: 14px;}}
    .rs-step {{display: flex; align-items: center; gap: 6px; color: #6B7280;}}
    .rs-step .n {{width: 22px; height: 22px; border-radius: 11px; box-sizing: border-box; border: 2px solid #D1D5DB; display: flex; align-items: center; justify-content: center; font-size: 12px;}}
    .rs-step.done {{color: {ACCENT};}}
    .rs-step.done .n {{background: {ACCENT}; border-color: {ACCENT}; color: #FFFFFF;}}
    .rs-step.current {{color: #111827; font-weight: 700;}}
    .rs-step.current .n {{border-color: {ACCENT}; color: {ACCENT};}}
    .rs-line {{width: 28px; height: 2px; background: #D1D5DB;}}
    .rs-line.done {{background: {ACCENT};}}

    /* Uploader */
    [data-testid="stFileUploaderDropzone"] {{background: #F9FAFB; border: 2px dashed #CBD5E1; border-radius: 16px;}}

    /* Buttons */
    .stButton > button, .stDownloadButton > button {{
        border-radius: 12px; min-height: 48px; font-size: 15px; font-weight: 500;
        border: 1px solid #D1D5DB; background: #FFFFFF; color: #111827;
    }}
    .stButton > button[kind="primary"] {{background: {ACCENT}; border-color: {ACCENT}; color: #FFFFFF; font-weight: 700;}}
    .stButton > button[kind="primary"]:hover {{background: #155E75; border-color: #155E75;}}

    /* Receipt stage */
    .st-key-rs_stage {{background: #F3F4F6; border-radius: 20px; padding: 28px; min-height: 480px; justify-content: center;}}
    .st-key-rs_stage img {{box-shadow: 0 10px 30px rgba(17,24,39,0.12); border-radius: 4px; max-height: 560px; object-fit: contain;}}

    /* Extracted fields */
    .rs-kicker {{font-size: 13px; color: {ACCENT}; font-weight: 500;}}
    .rs-title {{margin: 2px 0 0; font-size: 28px; font-weight: 700;}}
    .rs-badge {{padding: 6px 12px; border-radius: 999px; background: #ECFEFF; color: {ACCENT}; font-size: 13px; font-weight: 500; white-space: nowrap;}}
    .rs-fields {{display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 18px 0 14px;}}
    .rs-field {{display: flex; flex-direction: column; gap: 6px;}}
    .rs-field .lbl {{display: flex; align-items: center; gap: 6px; font-size: 13px; color: #4B5563;}}
    .rs-field .dot {{width: 10px; height: 10px; border-radius: 3px;}}
    .rs-field .val {{height: 46px; box-sizing: border-box; padding: 0 14px; border-radius: 10px; border: 1px solid #D1D5DB; display: flex; align-items: center; font-size: 16px; color: #111827;}}
    .rs-meta {{display: flex; flex-wrap: wrap; gap: 12px; padding: 14px 16px; border-radius: 12px; background: #F9FAFB; font-size: 14px; color: #374151; margin-bottom: 14px;}}
    .rs-meta .sep {{color: #D1D5DB;}}

    /* Queue */
    .rs-queue-title {{font-size: 13px; color: #6B7280; margin: 18px 0 10px;}}
    .rs-queue {{display: flex; gap: 10px;}}
    .rs-q {{flex: 1 1 0; min-width: 0; padding: 10px 12px; border-radius: 10px; display: flex; flex-direction: column; gap: 2px; background: #F9FAFB; border: 1px solid #E5E7EB;}}
    .rs-q.done {{background: #ECFEFF; border-color: #A5F3FC;}}
    .rs-q.current {{background: #FFFFFF; border: 2px solid {ACCENT};}}
    .rs-q .v {{font-size: 12.5px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}}
    .rs-q .t {{font-size: 12px; color: #6B7280;}}

    /* Summary cards */
    .rs-section {{font-size: 20px; font-weight: 700; margin: 36px 0 14px;}}
    .rs-kpis {{display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px;}}
    .rs-kpi {{padding: 18px 20px; border-radius: 14px; border: 1px solid #E5E7EB; display: flex; flex-direction: column; gap: 6px;}}
    .rs-kpi .k {{font-size: 13.5px; color: #6B7280;}}
    .rs-kpi .v {{font-size: 28px; font-weight: 700;}}
    .rs-kpi.hl {{background: {ACCENT}; border-color: {ACCENT};}}
    .rs-kpi.hl .k {{color: #CFFAFE;}}
    .rs-kpi.hl .v {{color: #FFFFFF;}}
    .rs-empty {{padding: 18px 20px; border-radius: 14px; background: #F9FAFB; color: #4B5563; font-size: 15px;}}
    .rs-muted {{font-size: 12.5px; color: #6B7280;}}
</style>
""", unsafe_allow_html=True)


def _esc(value) -> str:
    """HTML-escape any value (AI output included) before placing it in markup."""
    return html.escape("" if value is None else str(value))


def _money(value, currency: str = "ILS") -> str:
    """Format an amount with its currency symbol."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "—"
    symbol = {"ILS": "₪", "USD": "$", "EUR": "€", "GBP": "£"}.get(str(currency).upper(), "")
    text = f"{amount:,.2f}"
    return f"{symbol}{text}" if symbol else f"{text} {_esc(currency)}"


def _receipt_key(r: dict) -> str:
    return f"{r.get('file_name')}|{r.get('date')}|{r.get('total_amount')}"


def render_header(step: int) -> None:
    """Brand + 4-step progress: upload → AI extraction → review → export."""
    labels = ["העלאה", "חילוץ AI", "בדיקה", "ייצוא"]
    parts = []
    for i, label in enumerate(labels, start=1):
        if i < step:
            cls, num = "done", "✓"
        elif i == step:
            cls, num = "current", str(i)
        else:
            cls, num = "", str(i)
        parts.append(f'<li class="rs-step {cls}"><span class="n">{num}</span>{label}</li>')
        if i < len(labels):
            parts.append(f'<li class="rs-line {"done" if i < step else ""}" aria-hidden="true"></li>')
    st.markdown(
        f"""
        <div class="rs-header">
          <div class="rs-brand">
            <div class="rs-logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 2h12v20l-3-2-3 2-3-2-3 2z"></path>
              <path d="M9 7h6"></path><path d="M9 11h6"></path><path d="M9 15h4"></path></svg></div>
            <span>Receipt Scanner Pro</span>
          </div>
          <ol class="rs-steps">{''.join(parts)}</ol>
        </div>
        """,
        unsafe_allow_html=True,
    )


def preview_image(file_name: str, files_by_name: dict):
    """Image bytes to show for a receipt (first page of a PDF), or None if unavailable."""
    data = files_by_name.get(file_name)
    if data is None:
        return None
    if file_name.lower().endswith(".pdf"):
        image_bytes, _err = convert_pdf_to_image(data)
        return image_bytes
    return data


def render_review(receipts: list, files_by_name: dict) -> None:
    """Side-by-side review: the original receipt next to what the AI extracted."""
    total = len(receipts)
    approved = st.session_state.setdefault("approved", set())
    idx = min(st.session_state.get("review_idx", 0), total - 1)
    r = receipts[idx]
    currency = r.get("currency") or "ILS"

    col_stage, col_fields = st.columns([1, 1.15], gap="large")

    with col_stage:
        with st.container(key="rs_stage"):
            img = preview_image(r.get("file_name", ""), files_by_name)
            if img:
                st.image(img)
            else:
                st.markdown(
                    '<div class="rs-empty">התמונה המקורית מוצגת רק כל עוד הקובץ נמצא בהעלאה הנוכחית.</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(f'<div class="rs-muted">{_esc(r.get("file_name"))}</div>', unsafe_allow_html=True)

    with col_fields:
        raw_type = str(r.get("document_type") or "receipt").lower()
        doc_type = DOC_TYPE_LABELS.get(raw_type, raw_type.replace("_", " "))
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:flex-end; gap:12px;">
              <div>
                <div class="rs-kicker">קבלה {idx + 1} מתוך {total}</div>
                <div class="rs-title">בדקו את מה שה-AI חילץ</div>
              </div>
              <span class="rs-badge">{_esc(doc_type)}</span>
            </div>
            <div class="rs-fields">
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['vendor']}"></span>ספק</span>
                <div class="val">{_esc(r.get('vendor_name'))}</div></div>
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['date']}"></span>תאריך</span>
                <div class="val">{_esc(r.get('date'))}</div></div>
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['vat']}"></span>מע"מ</span>
                <div class="val">{_money(r.get('vat'), currency)}</div></div>
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['total']}"></span>סה"כ</span>
                <div class="val" style="font-weight:700">{_money(r.get('total_amount'), currency)}</div></div>
            </div>
            <div class="rs-meta">
              <span>מטבע: <b>{_esc(currency)}</b></span><span class="sep">|</span>
              <span>בשקלים: <b>{_money(r.get('total_ils'))}</b></span><span class="sep">|</span>
              <span>ע.מ / ח.פ: <b>{_esc(r.get('business_id') or '—')}</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        b1, b2 = st.columns([3, 1])
        with b1:
            is_approved = _receipt_key(r) in approved
            label = "אושרה ✓ · מעבר לבאה" if is_approved else "אישור ומעבר לבאה"
            if st.button(label, type="primary", width="stretch", key=f"approve_{idx}"):
                approved.add(_receipt_key(r))
                st.session_state.review_idx = (idx + 1) % total
                st.rerun()
        with b2:
            if st.button("דילוג", width="stretch", key=f"skip_{idx}"):
                st.session_state.review_idx = (idx + 1) % total
                st.rerun()

        # Queue strip: up to 5 receipts around the current one, then "+N more"
        start = max(0, min(idx - 2, total - 5))
        window = receipts[start:start + 5]
        cells = []
        for j, q in enumerate(window, start=start):
            if j == idx:
                cls = "current"
            elif _receipt_key(q) in approved:
                cls = "done"
            else:
                cls = ""
            mark = "✓ " if _receipt_key(q) in approved else ""
            cells.append(
                f'<div class="rs-q {cls}"><span class="v">{mark}{_esc(q.get("vendor_name"))}</span>'
                f'<span class="t">{_money(q.get("total_amount"), q.get("currency") or "ILS")}</span></div>'
            )
        remaining = total - (start + len(window))
        if remaining > 0:
            cells.append(f'<div class="rs-q"><span class="v">+{remaining} נוספות</span><span class="t">ממתינות</span></div>')
        st.markdown(
            f'<div class="rs-queue-title">תור בדיקה · {len(approved & {_receipt_key(x) for x in receipts})} מתוך {total} אושרו</div>'
            f'<div class="rs-queue">{"".join(cells)}</div>',
            unsafe_allow_html=True,
        )


def render_summary(receipt_data: list, exchange_rates: dict) -> None:
    """KPIs, full table with Excel export, and spending charts (all in ILS)."""
    df = pd.DataFrame(receipt_data)
    column_order = ['file_name', 'vendor_name', 'date', 'total_amount', 'vat', 'currency', 'total_ils']
    df = df[[c for c in column_order if c in df.columns]]
    df = df.rename(columns={
        'file_name': 'קובץ',
        'vendor_name': 'ספק',
        'date': 'תאריך',
        'total_amount': 'סכום',
        'vat': 'מע"מ',
        'currency': 'מטבע',
        'total_ils': 'סכום בש"ח',
    })

    total_receipts = len(df)
    total_ils = pd.to_numeric(df.get('סכום בש"ח'), errors='coerce').fillna(0).sum() if total_receipts else 0
    vat_numeric = pd.to_numeric(df['מע"מ'].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)
    vat_ils = [convert_to_ils(v, c, exchange_rates) for v, c in zip(vat_numeric, df['מטבע'])]
    total_vat = float(sum(vat_ils))
    avg_receipt = total_ils / total_receipts if total_receipts else 0

    st.markdown('<div class="rs-section">סיכום</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="rs-kpis">
          <div class="rs-kpi hl"><span class="k">מע"מ לקיזוז</span><span class="v">₪{total_vat:,.2f}</span></div>
          <div class="rs-kpi"><span class="k">סה"כ הוצאות</span><span class="v">₪{total_ils:,.2f}</span></div>
          <div class="rs-kpi"><span class="k">קבלות</span><span class="v">{total_receipts}</span></div>
          <div class="rs-kpi"><span class="k">ממוצע לקבלה</span><span class="v">₪{avg_receipt:,.2f}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="rs-section">כל הקבלות</div>', unsafe_allow_html=True)
    st.dataframe(df, width='stretch', hide_index=True, height=360)

    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="הורדת דוח Excel",
            data=create_excel_download(df),
            file_name=f"receipt_analysis_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
        )
    with c2:
        if st.button("ניקוי כל הנתונים", width='stretch'):
            deleted = clear_all_receipts()
            st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1
            st.session_state.review_idx = 0
            st.session_state.approved = set()
            st.toast(f"נמחקו {deleted} קבלות")
            st.rerun()

    viz_df = df.copy()
    viz_df['total'] = pd.to_numeric(viz_df['סכום בש"ח'], errors='coerce')
    viz_df = viz_df.dropna(subset=['total'])
    viz_df = viz_df[viz_df['total'] > 0]
    if viz_df.empty:
        return

    vendor_totals = (
        viz_df.groupby('ספק')['total'].sum().reset_index().sort_values('total', ascending=False)
    )
    st.markdown('<div class="rs-section">לאן הולך הכסף</div>', unsafe_allow_html=True)
    ch1, ch2 = st.columns(2, gap="large")
    common = dict(
        template='plotly_white',
        font=dict(family='Rubik, sans-serif', color='#111827', size=13),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=10, b=10, l=10, r=10),
        hoverlabel=dict(bgcolor='#FFFFFF', font_family='Rubik, sans-serif'),
    )
    with ch1:
        fig_pie = px.pie(vendor_totals, values='total', names='ספק', hole=0.55,
                         color_discrete_sequence=CHART_COLORS)
        fig_pie.update_traces(
            textposition='inside', textinfo='percent',
            hovertemplate='%{label}<br>₪%{value:,.2f} · %{percent}<extra></extra>',
            marker=dict(line=dict(color='#FFFFFF', width=2)),
        )
        fig_pie.update_layout(height=380, showlegend=True, legend=dict(orientation='v', x=1.02, y=0.5), **common)
        st.plotly_chart(fig_pie, use_container_width=True, key='pie_vendor')
    with ch2:
        fig_bar = px.bar(vendor_totals, x='ספק', y='total', color_discrete_sequence=[ACCENT])
        fig_bar.update_traces(hovertemplate='%{x}<br>₪%{y:,.2f}<extra></extra>')
        fig_bar.update_layout(
            height=380, showlegend=False, xaxis_title=None, yaxis_title='₪',
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#EEF0F3'), **common,
        )
        st.plotly_chart(fig_bar, use_container_width=True, key='bar_vendor')


def main():
    """
    Run the Streamlit receipt scanner application.

    Handles file upload, AI analysis, review, validation, and Excel export.
    API key is retrieved strictly from Streamlit secrets.
    """
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0

    # Fetch exchange rates once at app start (silent)
    exchange_rates, is_live = fetch_live_exchange_rates()

    # SECURITY: API key MUST be retrieved strictly from st.secrets (never hardcoded or env fallback)
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        if not api_key or not str(api_key).strip():
            st.error("לא נמצא מפתח API. יש להגדיר אותו בקובץ .streamlit/secrets.toml")
            st.stop()
    except (KeyError, FileNotFoundError):
        st.error("לא נמצא מפתח API. יש להגדיר אותו בקובץ .streamlit/secrets.toml")
        st.stop()

    receipt_data = get_all_receipts()
    uploader_state = st.session_state.get(f"uploader_{st.session_state.uploader_key}")
    has_files = bool(uploader_state)
    if not has_files and not receipt_data:
        step = 1
    elif not receipt_data:
        step = 2
    else:
        approved_keys = st.session_state.get("approved", set())
        all_approved = all(_receipt_key(r) in approved_keys for r in receipt_data)
        step = 4 if all_approved else 3
    render_header(step)

    uploaded_files = st.file_uploader(
        "גררו לכאן קבלות (JPG, PNG, PDF)",
        type=['jpg', 'jpeg', 'png', 'pdf'],
        accept_multiple_files=True,
        help="אפשר להעלות כמה קבלות בבת אחת",
        key=f"uploader_{st.session_state.uploader_key}",
    )

    if uploaded_files:
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            analyze_button = st.button(f"ניתוח {len(uploaded_files)} קבצים עם AI", type="primary", width='stretch')

        if analyze_button:
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_placeholder = st.container()

            def process_one(uploaded_file):
                """Process a single file; returns (file_name, result)."""
                file_bytes = uploaded_file.getvalue()
                result = analyze_receipt_with_claude(
                    api_key, file_bytes, uploaded_file.name, exchange_rates
                )
                return (uploaded_file.name, result)

            completed = 0
            total = len(uploaded_files)

            with ThreadPoolExecutor(max_workers=min(6, total)) as executor:
                futures = {executor.submit(process_one, f): f.name for f in uploaded_files}
                with results_placeholder:
                    for future in as_completed(futures):
                        file_name = futures[future]
                        try:
                            name, result = future.result()
                            if result:
                                is_valid, reason, user_message = is_valid_receipt(result)
                                if is_valid:
                                    if result.get("_duplicate", False):
                                        st.warning(f"קבלה כפולה, לא נשמרה שוב: {name}")
                                else:
                                    st.error(f"הקובץ '{name}' נדחה: זה לא נראה כמו מסמך עסקי.")
                                    with st.expander(f"פרטים על {name}"):
                                        st.write(f"**סיבה:** {user_message}")
                                        st.write(f"**קוד:** {reason}")
                            else:
                                st.error(f"הניתוח של {name} נכשל")
                        except Exception as e:
                            st.error(f"שגיאה בעיבוד {file_name}: {str(e)}")

                        completed += 1
                        progress_bar.progress(completed / total)
                        status_text.text(f"עובדו {completed} מתוך {total} קבצים...")

            st.session_state.review_idx = 0
            st.rerun()

    if not receipt_data:
        st.markdown(
            '<div class="rs-empty" style="margin-top:12px">העלו קבלות כדי להתחיל. '
            'ה-AI יחלץ ספק, תאריך, סכום ומע"מ, ואתם תאשרו כל קבלה לפני הייצוא.</div>',
            unsafe_allow_html=True,
        )
        return

    files_by_name = {f.name: f.getvalue() for f in (uploaded_files or [])}
    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
    render_review(receipt_data, files_by_name)
    render_summary(receipt_data, exchange_rates)


if __name__ == "__main__":
    main()
