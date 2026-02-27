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
CURRENT_LANG = 'en'

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
    initial_sidebar_state="expanded"
)

# Custom CSS for Clean Minimalist Dark Theme with RTL support
st.markdown("""
<style>
    /* Hide Streamlit System Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    button[title="View fullscreen"] {visibility: hidden;}
    [data-testid="stToolbarIcon"] {display: none;}
    [data-testid="stHeaderDecorator"] {display: none;}
    
    .main {
        padding: 2rem;
    }
    
    /* RTL Support for Hebrew */
    h1, h2, h3 {
        direction: rtl;
        text-align: right;
    }
    
    .dataframe th {
        text-align: right !important;
        direction: rtl;
    }
    
    /* Professional Summary Metric Cards - RTL aligned for Hebrew */
    [data-testid="stMetric"] {
        background-color: rgba(30, 30, 30, 0.6);
        padding: 1rem 1.25rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        justify-content: center;
        direction: rtl;
    }
    
    [data-testid="stMetricLabel"] {
        direction: rtl;
        text-align: right;
        font-size: 0.9rem;
        color: #b0b0b0;
        font-weight: 400;
        display: block;
        unicode-bidi: embed;
        width: 100%;
    }
    
    [data-testid="stMetricValue"] {
        direction: ltr;
        text-align: right;
        font-size: 2rem;
        font-weight: 700;
        color: #00d9ff;
        display: block;
        unicode-bidi: embed;
        width: 100%;
    }
    
    /* Button Styling */
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        border: none;
        transition: all 0.3s;
    }
    
    .stButton>button:hover {
        background-color: #45a049;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Remove container borders */
    [data-testid="stExpander"] {
        border: none;
        background-color: transparent;
    }
    
    /* Clean container styling */
    [data-testid="stVerticalBlock"] {
        background-color: transparent;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """
    Run the Streamlit receipt scanner application.

    Handles file upload, AI analysis, validation, and Excel export.
    API key is retrieved strictly from Streamlit secrets.
    """
    # Initialize session state for uploader reset key only (receipts stored in SQLite)
    if 'uploader_key' not in st.session_state:
        st.session_state.uploader_key = 0
    
    # Fetch exchange rates once at app start (silent)
    exchange_rates, is_live = fetch_live_exchange_rates()
    
    # SECURITY: API key MUST be retrieved strictly from st.secrets (never hardcoded or env fallback)
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        if not api_key or not str(api_key).strip():
            st.error("⚠️ API key not found in secrets. Please configure .streamlit/secrets.toml")
            st.stop()
    except (KeyError, FileNotFoundError):
        st.error("⚠️ API key not found in secrets. Please configure .streamlit/secrets.toml")
        st.stop()
    
    # Minimal Sidebar
    with st.sidebar:
        st.title("🧾 סורק קבלות")
        st.markdown("---")
        
        # System status
        st.success("✅ System Ready")
        
        st.markdown("---")
        
        # Clear data button - clears SQLite DB AND increments uploader_key for hard reset
        if st.button("🗑️ Clear Data", use_container_width=True, type="primary"):
            deleted = clear_all_receipts()
            st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1
            st.success(f"✅ נתונים נוקו ({deleted} receipts removed)")
            st.rerun()
    
    # Main content
    st.title(get_text('app_title'))
    st.markdown("### Upload and analyze your receipts automatically using AI")
    st.markdown("---")
    
    # Check API key
    if not api_key:
        st.warning("⚠️ Please enter your Anthropic API key in the sidebar to continue.")
        st.info("💡 You can get your API key from [console.anthropic.com](https://console.anthropic.com/)")
        return
    
    # File uploader with dynamic key for hard reset (clears files when Clear Data is clicked)
    st.subheader(get_text('upload_receipts'))
    uploaded_files = st.file_uploader(
        "Choose receipt images or PDFs",
        type=['jpg', 'jpeg', 'png', 'pdf'],
        accept_multiple_files=True,
        help="Upload one or more receipt files (JPG, PNG, or PDF)",
        key=f"uploader_{st.session_state.uploader_key}"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} file(s) uploaded successfully")
        
        # Display uploaded files
        with st.expander("📋 View uploaded files"):
            for file in uploaded_files:
                st.write(f"- {file.name} ({file.size / 1024:.2f} KB)")
        
        st.markdown("---")
        
        # Analyze button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            analyze_button = st.button(get_text('analyze_receipts'), width='stretch')
        
        if analyze_button:
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_placeholder = st.container()

            def process_one(uploaded_file):
                """Process a single file; returns (file_name, result, file_bytes)."""
                file_bytes = uploaded_file.read()
                result = analyze_receipt_with_claude(
                    api_key, file_bytes, uploaded_file.name, exchange_rates
                )
                return (uploaded_file.name, result)

            completed = 0
            total = len(uploaded_files)

            with ThreadPoolExecutor(max_workers=min(6, total)) as executor:
                futures = {
                    executor.submit(process_one, f): f.name for f in uploaded_files
                }
                with results_placeholder:
                    for future in as_completed(futures):
                        file_name = futures[future]
                        try:
                            name, result = future.result()
                            if result:
                                is_valid, reason, user_message = is_valid_receipt(result)
                                if is_valid:
                                    if result.get("_duplicate", False):
                                        st.warning(f"⚠️ Duplicate receipt detected: {name}")
                                    else:
                                        doc_type = result.get("document_type", "receipt").title()
                                        st.success(f"✅ {doc_type} processed: {name}")
                                else:
                                    st.error(f"⚠️ File '{name}' was rejected: Non-business document identified.")
                                    with st.expander(f"Details for {name}"):
                                        st.write(f"**Reason:** {user_message}")
                                        st.write(f"**Code:** {reason}")
                            else:
                                st.error(f"❌ Failed to analyze {name}")
                        except Exception as e:
                            st.error(f"❌ Error processing {file_name}: {str(e)}")

                        completed += 1
                        progress_bar.progress(completed / total)
                        status_text.text(f"Processed {completed}/{total} files...")

            status_text.text("✨ Analysis complete!")
            st.rerun()
            
        # Display results from SQLite database (single source of truth)
        receipt_data = get_all_receipts()
        if receipt_data:
            st.markdown("---")
            st.subheader(get_text('extracted_data'))
            
            # Create DataFrame (exclude created_at for display)
            df = pd.DataFrame(receipt_data)
            display_cols = ['file_name', 'vendor_name', 'date', 'total_amount', 'vat', 'currency', 'total_ils']
            df = df[[c for c in display_cols if c in df.columns]]
            
            column_order = ['file_name', 'vendor_name', 'date', 'total_amount', 'vat', 'currency', 'total_ils']
            df = df[[c for c in column_order if c in df.columns]]
            
            col_rename = {
                'file_name': 'File Name',
                'vendor_name': 'Vendor Name',
                'date': 'Date',
                'total_amount': 'Total Amount',
                'vat': 'VAT (Tax)',
                'currency': 'Currency',
                'total_ils': 'Total in ILS',
            }
            df = df.rename(columns=col_rename)
            
            # Display dataframe
            st.dataframe(
                df,
                width='stretch',
                hide_index=True,
                height=400
            )
            
            # Download button
            st.markdown("---")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                excel_data = create_excel_download(df)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                st.download_button(
                    label=get_text('download_excel'),
                    data=excel_data,
                    file_name=f"receipt_analysis_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width='stretch'
                )
            
            # Clean Minimalist Summary Header
            st.markdown("---")
            st.subheader("📊 Financial Summary")
            
            # Calculate all metrics first
            total_receipts = len(df)
            
            try:
                total_ils = df['Total in ILS'].sum()
            except (KeyError, TypeError):
                total_ils = 0
            
            try:
                # Calculate Total VAT in ILS
                viz_df_temp = df.copy()
                viz_df_temp['VAT Numeric'] = pd.to_numeric(
                    viz_df_temp['VAT (Tax)'].astype(str).str.replace(',', '', regex=False),
                    errors='coerce'
                )
                viz_df_temp['VAT Numeric'] = viz_df_temp['VAT Numeric'].fillna(0)
                
                # Convert VAT to ILS
                viz_df_temp['VAT ILS'] = viz_df_temp.apply(
                    lambda row: convert_to_ils(row['VAT Numeric'], row['Currency'], exchange_rates), 
                    axis=1
                )
                
                total_vat = viz_df_temp['VAT ILS'].sum()
            except (KeyError, TypeError):
                total_vat = 0
            
            try:
                avg_receipt = total_ils / total_receipts if total_receipts > 0 else 0
            except (ZeroDivisionError, TypeError):
                avg_receipt = 0
            
            # Display in 4 clean columns (no borders, transparent background)
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="Total Receipts",
                    value=f"{total_receipts}"
                )
            
            with col2:
                st.metric(
                    label="Total Amount (ILS)",
                    value=f"₪{total_ils:,.2f}"
                )
            
            with col3:
                st.metric(
                    label="Total VAT (ILS)",
                    value=f"₪{total_vat:,.2f}"
                )
            
            with col4:
                st.metric(
                    label="Avg. Receipt Value",
                    value=f"₪{avg_receipt:,.2f}"
                )
            
            # Professional Visual Analytics Section (all data from DB-sourced df)
            st.markdown("---")
            
            with st.container():
                st.subheader("📈 Visual Analytics")
                
                # Prepare visualization data from DB-sourced DataFrame
                try:
                    viz_df = df.copy()
                    viz_df['Total ILS Numeric'] = pd.to_numeric(viz_df['Total in ILS'], errors='coerce')
                    viz_df = viz_df.dropna(subset=['Total ILS Numeric'])
                    viz_df = viz_df[viz_df['Total ILS Numeric'] > 0]
                    
                    if len(viz_df) > 0:
                        vendor_totals = viz_df.groupby('Vendor Name')['Total ILS Numeric'].sum().reset_index()
                        vendor_totals = vendor_totals.sort_values('Total ILS Numeric', ascending=False)
                        
                        chart_col1, chart_col2 = st.columns(2)
                        
                        with chart_col1:
                            st.markdown("**💰 Spending by Vendor (Pie)**")
                            fig_vendor_pie = px.pie(
                                vendor_totals,
                                values='Total ILS Numeric',
                                names='Vendor Name',
                                hole=0.4,
                                title=None,
                            )
                            fig_vendor_pie.update_traces(
                                textposition='inside',
                                textinfo='percent',
                                hovertemplate='<b style="color:white">Vendor:</b> <span style="color:white">%{label}</span><br><b style="color:white">Amount:</b> <span style="color:white">₪%{value:,.2f}</span><br><b style="color:white">Share:</b> <span style="color:white">%{percent}</span><extra></extra>',
                                marker=dict(line=dict(color='#333333', width=1)),
                            )
                            fig_vendor_pie.update_layout(
                                template='plotly_dark',
                                showlegend=True,
                                height=400,
                                margin=dict(t=20, b=20, l=20, r=20),
                                legend=dict(
                                    orientation="v",
                                    yanchor="middle",
                                    y=0.5,
                                    xanchor="left",
                                    x=1.05,
                                    font=dict(color='white', size=11),
                                ),
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                hoverlabel=dict(
                                    bgcolor='#2b2b2b',
                                    font_size=13,
                                    font_family="Arial",
                                    font_color='white',
                                ),
                            )
                            st.plotly_chart(fig_vendor_pie, use_container_width=True, key='pie_vendor')
                        
                        with chart_col2:
                            st.markdown("**📊 Spending by Vendor (Bar)**")
                            fig_bar = px.bar(
                                vendor_totals,
                                x='Vendor Name',
                                y='Total ILS Numeric',
                                color='Total ILS Numeric',
                                color_continuous_scale='Viridis',
                                labels={'Total ILS Numeric': 'Total in ILS'},
                                title=None,
                            )
                            fig_bar.update_traces(
                                hovertemplate='<b style="color:white">Vendor:</b> <span style="color:white">%{x}</span><br><b style="color:white">Amount:</b> <span style="color:white">₪%{y:,.2f}</span><extra></extra>',
                                marker=dict(line=dict(color='#333333', width=1)),
                            )
                            fig_bar.update_layout(
                                template='plotly_dark',
                                showlegend=False,
                                height=450,
                                xaxis_title="Vendor",
                                yaxis_title="Total Amount (₪)",
                                margin=dict(t=20, b=20, l=20, r=20),
                                xaxis=dict(
                                    tickangle=-45,
                                    showgrid=False,
                                    gridcolor='rgba(0,0,0,0)',
                                    title=dict(font=dict(color='white')),
                                    tickfont=dict(color='white'),
                                ),
                                yaxis=dict(
                                    showgrid=False,
                                    gridcolor='rgba(0,0,0,0)',
                                    title=dict(font=dict(color='white')),
                                    tickfont=dict(color='white'),
                                ),
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                hoverlabel=dict(
                                    bgcolor='#2b2b2b',
                                    font_size=13,
                                    font_family="Arial",
                                    font_color='white',
                                ),
                            )
                            st.plotly_chart(fig_bar, use_container_width=True, key='bar_vendor')
                        
                        # VAT Analysis in Clean Expander
                        with st.expander("💳 VAT/Tax Analysis Details", expanded=False):
                            # Calculate VAT totals
                            viz_df['VAT Numeric'] = pd.to_numeric(
                                viz_df['VAT (Tax)'].astype(str).str.replace(',', '', regex=False),
                                errors='coerce'
                            )
                            viz_df['VAT Numeric'] = viz_df['VAT Numeric'].fillna(0)
                            
                            # Convert VAT to ILS
                            viz_df['VAT ILS'] = viz_df.apply(
                                lambda row: convert_to_ils(row['VAT Numeric'], row['Currency'], exchange_rates), 
                                axis=1
                            )
                            
                            total_vat_ils = viz_df['VAT ILS'].sum()
                            total_with_vat_ils = viz_df['Total ILS Numeric'].sum()
                            total_without_vat_ils = total_with_vat_ils - total_vat_ils
                            avg_vat_rate = (total_vat_ils / total_without_vat_ils * 100) if total_without_vat_ils > 0 else 0
                            
                            vat_col1, vat_col2, vat_col3 = st.columns(3)
                            with vat_col1:
                                st.metric("Total VAT", f"₪{total_vat_ils:,.2f}")
                            with vat_col2:
                                st.metric("Net Amount", f"₪{total_without_vat_ils:,.2f}")
                            with vat_col3:
                                st.metric("Avg VAT Rate", f"{avg_vat_rate:.1f}%")
                            
                    else:
                        st.info("📊 Add receipts with valid amounts to see visualizations")
                        
                except Exception as e:
                    st.warning(f"⚠️ Could not generate visualizations: {str(e)}")
    
    else:
        st.info("👆 Upload receipt files to get started")

if __name__ == "__main__":
    main()
