"""Receipt Scanner Pro - Streamlit UI for freelancers who send receipts to their accountant."""

import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from processor import (
    DOC_TYPE_LABELS,
    STATUS_DUPLICATE,
    STATUS_ERROR,
    STATUS_POSSIBLE_DUPLICATE,
    STATUS_REJECTED,
    STATUS_SAVED,
    analyze_receipt_with_claude,
    clear_all_receipts,
    convert_pdf_to_image,
    create_excel_download,
    fetch_live_exchange_rates,
    get_all_receipts,
    get_anthropic_client,
    is_vat_reclaimable,
    normalize_currency,
    normalize_document_type,
    parse_amount,
    parse_receipt_date,
    set_receipt_approved,
)

st.set_page_config(
    page_title="Receipt Scanner Pro",
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
    .rs-brand-text {{display: flex; flex-direction: column; gap: 2px;}}
    .rs-tagline {{font-size: 13px; font-weight: 400; color: #6B7280;}}
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

    .rs-kpi .s {{font-size: 12.5px; color: #6B7280;}}
    .rs-kpi.hl .s {{color: #CFFAFE;}}
    .rs-warn {{margin: 12px 0 0; padding: 10px 14px; border-radius: 10px; background: #FFFBEB; border: 1px solid #FDE68A; color: #92400E; font-size: 14px;}}
    .rs-results {{margin: 14px 0 6px; padding: 14px 18px; border-radius: 14px; border: 1px solid #E5E7EB; background: #F9FAFB;}}
    .rs-results-title {{font-size: 14px; font-weight: 700; margin-bottom: 8px;}}
    .rs-results ul {{margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px;}}
    .rs-res {{display: flex; align-items: baseline; gap: 8px; font-size: 14px; color: #374151;}}
    .rs-res .i {{width: 20px; height: 20px; border-radius: 10px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #FFFFFF; background: #9CA3AF;}}
    .rs-res.saved .i {{background: #15803D;}}
    .rs-res.possible_duplicate .i {{background: #B45309;}}
    .rs-res.rejected .i, .rs-res.error .i {{background: #B91C1C;}}

    /* Phones: most receipts are photographed and reviewed on mobile */
    @media (max-width: 640px) {{
        .block-container {{padding: 1rem 1rem 2rem;}}
        .rs-header {{flex-direction: column; align-items: flex-start; gap: 12px;}}
        .rs-steps {{gap: 6px; font-size: 12.5px;}}
        .rs-line {{width: 12px;}}
        .rs-title {{font-size: 22px;}}
        .rs-fields {{grid-template-columns: minmax(0, 1fr);}}
        .rs-kpis {{grid-template-columns: repeat(2, minmax(0, 1fr));}}
        .rs-kpi .v {{font-size: 22px;}}
        .rs-queue {{overflow-x: auto;}}
        .rs-q {{flex: 0 0 118px;}}
        .st-key-rs_stage {{min-height: 0; padding: 16px;}}
    }}
</style>
""", unsafe_allow_html=True)


def _esc(value) -> str:
    """HTML-escape any value (AI output included) before placing it in markup."""
    return html.escape("" if value is None else str(value))


def _money(value, currency: str = "ILS") -> str:
    """Format an amount with its currency symbol."""
    amount = parse_amount(value)
    if amount is None:
        return "—"
    symbol = {"ILS": "₪", "USD": "$", "EUR": "€", "GBP": "£"}.get(str(currency).upper(), "")
    text = f"{amount:,.2f}"
    return f"{symbol}{text}" if symbol else f"{text} {_esc(currency)}"


def _vat_ils(r: dict) -> float:
    """VAT in shekels; rows saved before vat_ils existed fall back to their ILS VAT."""
    if r.get("vat_ils") is not None:
        return float(r["vat_ils"])
    return float(parse_amount(r.get("vat")) or 0.0) if normalize_currency(r.get("currency")) == "ILS" else 0.0


def _doc_label(r: dict) -> str:
    return DOC_TYPE_LABELS[normalize_document_type(r.get("document_type"))]


def render_header(step: int) -> None:
    """Brand + 4-step progress: upload → AI extraction → review → report for the accountant."""
    labels = ["העלאה", "חילוץ AI", "בדיקה", 'דוח לרו"ח']
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
            <div class="rs-brand-text"><span>Receipt Scanner Pro</span><span class="rs-tagline">מצלמים קבלה, מאשרים, והדוח מוכן לרואה החשבון</span></div>
          </div>
          <ol class="rs-steps">{''.join(parts)}</ol>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _pdf_preview(data: bytes):
    image_bytes, _ = convert_pdf_to_image(data)
    return image_bytes


def preview_image(file_name: str, files_by_name: dict):
    """Image bytes to show for a receipt (first pages of a PDF), or None if unavailable."""
    data = files_by_name.get(file_name)
    if data is None:
        return None
    if file_name.lower().endswith(".pdf"):
        return _pdf_preview(data)
    return data


def render_results() -> None:
    """What happened to each file in the last analysis (kept across the rerun)."""
    results = st.session_state.get("last_results")
    if not results:
        return
    icons = {STATUS_SAVED: "✓", STATUS_POSSIBLE_DUPLICATE: "!", STATUS_DUPLICATE: "=", STATUS_REJECTED: "×", STATUS_ERROR: "×"}
    items = "".join(
        f'<li class="rs-res {r["_status"]}"><span class="i">{icons.get(r["_status"], "·")}</span>'
        f'<b>{_esc(r["file_name"])}</b><span>{_esc(r["_message"])}</span></li>'
        for r in results
    )
    saved = sum(r["_status"] in (STATUS_SAVED, STATUS_POSSIBLE_DUPLICATE) for r in results)
    st.markdown(
        f'<div class="rs-results"><div class="rs-results-title">תוצאות הניתוח · {saved} מתוך {len(results)} נקלטו</div>'
        f'<ul>{items}</ul></div>',
        unsafe_allow_html=True,
    )
    if st.button("סגירה", key="close_results"):
        st.session_state.last_results = []
        st.rerun()


def render_review(receipts: list, files_by_name: dict) -> None:
    """Side-by-side review: the original receipt next to what the AI extracted."""
    total = len(receipts)
    idx = min(st.session_state.get("review_idx", 0), total - 1)
    r = receipts[idx]
    currency = r.get("currency") or "ILS"
    reclaimable = is_vat_reclaimable(r)

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
        warning = (
            '<div class="rs-warn">ייתכן שזו כפילות: יש כבר מסמך עם אותו ספק, תאריך וסכום.</div>'
            if r.get("possible_duplicate")
            else ""
        )
        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:flex-end; gap:12px;">
              <div>
                <div class="rs-kicker">מסמך {idx + 1} מתוך {total}</div>
                <div class="rs-title">בדקו את מה שה-AI חילץ</div>
              </div>
              <span class="rs-badge">{_esc(_doc_label(r))}</span>
            </div>
            {warning}
            <div class="rs-fields">
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['vendor']}"></span>ספק</span>
                <div class="val">{_esc(r.get('vendor_name'))}</div></div>
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['date']}"></span>תאריך</span>
                <div class="val">{_esc(_display_date(r.get('date')))}</div></div>
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['vat']}"></span>מע"מ</span>
                <div class="val">{_money(r.get('vat'), currency)}</div></div>
              <div class="rs-field"><span class="lbl"><span class="dot" style="background:{FIELD_COLORS['total']}"></span>סה"כ</span>
                <div class="val" style="font-weight:700">{_money(r.get('total_amount'), currency)}</div></div>
            </div>
            <div class="rs-meta">
              <span>בשקלים: <b>{_money(r.get('total_ils'))}</b></span><span class="sep">|</span>
              <span>ע.מ / ח.פ: <b>{_esc(r.get('business_id') or '—')}</b></span><span class="sep">|</span>
              <span>מספר מסמך: <b>{_esc(r.get('document_number') or '—')}</b></span><span class="sep">|</span>
              <span>מע"מ לקיזוז: <b>{'כן' if reclaimable else 'לא'}</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        b1, b2 = st.columns([3, 1])
        with b1:
            label = "אושר ✓ · מעבר לבא" if r.get("approved") else "אישור ומעבר לבא"
            if st.button(label, type="primary", width="stretch", key=f"approve_{r['id']}"):
                if not r.get("approved"):
                    set_receipt_approved(r["id"], True)
                st.session_state.review_idx = (idx + 1) % total
                st.rerun()
        with b2:
            if st.button("דילוג", width="stretch", key=f"skip_{r['id']}"):
                st.session_state.review_idx = (idx + 1) % total
                st.rerun()

        # Queue strip: up to 5 documents around the current one, then "+N more"
        start = max(0, min(idx - 2, total - 5))
        window = receipts[start:start + 5]
        cells = []
        for j, q in enumerate(window, start=start):
            cls = "current" if j == idx else "done" if q.get("approved") else ""
            mark = "✓ " if q.get("approved") else ""
            cells.append(
                f'<div class="rs-q {cls}"><span class="v">{mark}{_esc(q.get("vendor_name"))}</span>'
                f'<span class="t">{_money(q.get("total_amount"), q.get("currency") or "ILS")}</span></div>'
            )
        remaining = total - (start + len(window))
        if remaining > 0:
            cells.append(f'<div class="rs-q"><span class="v">+{remaining} נוספים</span><span class="t">ממתינים</span></div>')
        approved_count = sum(1 for x in receipts if x.get("approved"))
        st.markdown(
            f'<div class="rs-queue-title">תור בדיקה · {approved_count} מתוך {total} אושרו</div>'
            f'<div class="rs-queue">{"".join(cells)}</div>',
            unsafe_allow_html=True,
        )


def _display_date(value) -> str:
    try:
        return parse_receipt_date(value).strftime("%d/%m/%Y")
    except ValueError:
        return str(value or "")


def render_summary(receipts: list, rates_are_live: bool) -> None:
    """KPIs, the full table, the Excel report (approved documents) and spending charts."""
    total_docs = len(receipts)
    total_ils = sum(float(r.get("total_ils") or 0.0) for r in receipts)
    vat_paid = sum(_vat_ils(r) for r in receipts)
    vat_reclaim = sum(_vat_ils(r) for r in receipts if is_vat_reclaimable(r))
    approved = [r for r in receipts if r.get("approved")]
    avg = total_ils / total_docs if total_docs else 0.0

    st.markdown('<div class="rs-section">הדוח לרואה החשבון</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="rs-kpis">
          <div class="rs-kpi hl"><span class="k">מע"מ לקיזוז</span><span class="v">₪{vat_reclaim:,.2f}</span>
            <span class="s">מתוך ₪{vat_paid:,.2f} מע"מ ששולם</span></div>
          <div class="rs-kpi"><span class="k">סה"כ הוצאות</span><span class="v">₪{total_ils:,.2f}</span></div>
          <div class="rs-kpi"><span class="k">מסמכים</span><span class="v">{total_docs}</span>
            <span class="s">{len(approved)} אושרו</span></div>
          <div class="rs-kpi"><span class="k">ממוצע למסמך</span><span class="v">₪{avg:,.2f}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not rates_are_live:
        st.markdown(
            '<div class="rs-muted" style="margin-top:8px">שירות שערי המטבע לא זמין כרגע, ולכן הומרו סכומים זרים לפי שער משוער.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="rs-section">כל המסמכים</div>', unsafe_allow_html=True)
    table = pd.DataFrame(
        [
            {
                "סטטוס": "✓ אושר" if r.get("approved") else "ממתין",
                "תאריך": _display_date(r.get("date")),
                "ספק": r.get("vendor_name"),
                "סוג": _doc_label(r),
                "סכום": parse_amount(r.get("total_amount")),
                'מע"מ': parse_amount(r.get("vat")) or 0.0,
                "מטבע": r.get("currency"),
                'סכום בש"ח': float(r.get("total_ils") or 0.0),
                "לקיזוז": "כן" if is_vat_reclaimable(r) else "לא",
                "קובץ": r.get("file_name"),
            }
            for r in receipts
        ]
    )
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        height=min(420, 38 + 35 * len(table)),
        column_config={
            "סכום": st.column_config.NumberColumn(format="%.2f"),
            'מע"מ': st.column_config.NumberColumn(format="%.2f"),
            'סכום בש"ח': st.column_config.NumberColumn(format="%.2f"),
        },
    )

    c1, c2, _ = st.columns([1.2, 1, 1.8])
    with c1:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label=f'הורדת הדוח לרו"ח (Excel) · {len(approved)} מסמכים',
            data=create_excel_download(approved) if approved else b"",
            file_name=f"receipts_for_accountant_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            disabled=not approved,
        )
        if not approved:
            st.markdown('<div class="rs-muted">הדוח כולל רק מסמכים שאישרתם.</div>', unsafe_allow_html=True)
    with c2:
        if not st.session_state.get("confirm_clear"):
            if st.button("ניקוי כל הנתונים", width="stretch"):
                st.session_state.confirm_clear = True
                st.rerun()
        else:
            st.markdown(f'<div class="rs-warn">למחוק את כל {total_docs} המסמכים? אי אפשר לבטל.</div>', unsafe_allow_html=True)
            y, n = st.columns(2)
            with y:
                if st.button("כן, למחוק", type="primary", width="stretch"):
                    deleted = clear_all_receipts()
                    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
                    st.session_state.review_idx = 0
                    st.session_state.confirm_clear = False
                    st.session_state.last_results = []
                    st.toast(f"נמחקו {deleted} מסמכים")
                    st.rerun()
            with n:
                if st.button("ביטול", width="stretch"):
                    st.session_state.confirm_clear = False
                    st.rerun()

    chart_df = table[table['סכום בש"ח'] > 0]
    if chart_df.empty:
        return
    vendor_totals = (
        chart_df.groupby("ספק")['סכום בש"ח'].sum().reset_index().sort_values('סכום בש"ח', ascending=False)
    )
    st.markdown('<div class="rs-section">לאן הולך הכסף</div>', unsafe_allow_html=True)
    ch1, ch2 = st.columns(2, gap="large")
    common = dict(
        template="plotly_white",
        font=dict(family="Rubik, sans-serif", color="#111827", size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=10, r=10),
        hoverlabel=dict(bgcolor="#FFFFFF", font_family="Rubik, sans-serif"),
    )
    with ch1:
        fig_pie = px.pie(vendor_totals, values='סכום בש"ח', names="ספק", hole=0.55, color_discrete_sequence=CHART_COLORS)
        fig_pie.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate="%{label}<br>₪%{value:,.2f} · %{percent}<extra></extra>",
            marker=dict(line=dict(color="#FFFFFF", width=2)),
        )
        fig_pie.update_layout(height=380, showlegend=True, legend=dict(orientation="v", x=1.02, y=0.5), **common)
        st.plotly_chart(fig_pie, use_container_width=True, key="pie_vendor")
    with ch2:
        fig_bar = px.bar(vendor_totals, x="ספק", y='סכום בש"ח', color_discrete_sequence=[ACCENT])
        fig_bar.update_traces(hovertemplate="%{x}<br>₪%{y:,.2f}<extra></extra>")
        fig_bar.update_layout(
            height=380, showlegend=False, xaxis_title=None, yaxis_title="₪",
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#EEF0F3"), **common,
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="bar_vendor")


def main():
    """
    Run the Streamlit receipt scanner application.

    Upload → AI extraction → review and approve → Excel report for the accountant.
    The API key is read only from Streamlit secrets.
    """
    st.session_state.setdefault("uploader_key", 0)
    exchange_rates, rates_are_live = fetch_live_exchange_rates()

    # SECURITY: the API key comes only from st.secrets (never hardcoded, never typed in the UI)
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:  # no secrets file, or the key is missing
        api_key = None
    if not api_key or not str(api_key).strip():
        st.error("לא נמצא מפתח API. יש להגדיר אותו בקובץ .streamlit/secrets.toml")
        st.stop()

    receipts = get_all_receipts()
    has_files = bool(st.session_state.get(f"uploader_{st.session_state.uploader_key}"))
    if not receipts:
        step = 2 if has_files else 1
    else:
        step = 4 if all(r.get("approved") for r in receipts) else 3
    render_header(step)

    uploaded_files = st.file_uploader(
        "צלמו או העלו קבלות וחשבוניות (JPG, PNG, PDF)",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        help="בנייד אפשר לצלם ישירות מהמצלמה. אפשר להעלות כמה מסמכים בבת אחת.",
        key=f"uploader_{st.session_state.uploader_key}",
    )

    if uploaded_files:
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            analyze = st.button(f"ניתוח {len(uploaded_files)} קבצים עם AI", type="primary", width="stretch")

        if analyze:
            client = get_anthropic_client(api_key)  # created on the main thread, shared by workers
            progress = st.progress(0.0, text="מנתחים את המסמכים...")
            files = [(f.name, f.getvalue()) for f in uploaded_files]
            results = []
            with ThreadPoolExecutor(max_workers=min(6, len(files))) as executor:
                futures = [
                    executor.submit(analyze_receipt_with_claude, api_key, data, name, exchange_rates, client)
                    for name, data in files
                ]
                for done, future in enumerate(as_completed(futures), start=1):
                    results.append(future.result())
                    progress.progress(done / len(files), text=f"נותחו {done} מתוך {len(files)}")
            order = {name: i for i, (name, _) in enumerate(files)}
            st.session_state.last_results = sorted(results, key=lambda r: order.get(r["file_name"], 0))
            st.session_state.review_idx = next(
                (i for i, r in enumerate(get_all_receipts()) if not r.get("approved")), 0
            )
            st.rerun()

    render_results()

    if not receipts:
        st.markdown(
            '<div class="rs-empty" style="margin-top:12px">צלמו את הקבלות והחשבוניות של העסק, מהנייד או מהמחשב. '
            'ה-AI יחלץ ספק, תאריך, סכום ומע"מ, אתם מאשרים כל מסמך, ובסוף מורידים דוח Excel מסודר לרואה החשבון.</div>',
            unsafe_allow_html=True,
        )
        return

    files_by_name = {f.name: f.getvalue() for f in (uploaded_files or [])}
    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
    render_review(receipts, files_by_name)
    render_summary(receipts, rates_are_live)


if __name__ == "__main__":
    main()
