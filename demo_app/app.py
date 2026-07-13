"""
app.py
──────
Main Streamlit application for the Email Analysis Demo.

Run with:
    streamlit run app.py

Pages:
  1. Setup — configure backend URL, check status
  2. Mode Selection — Live (Outlook) or Upload
  3. Live Monitor — watches Outlook inbox in real-time
  4. Upload Mode — process .msg files (single or bulk)
  5. Report — view analyses, statistics, export
"""

import streamlit as st
import os
import sys
import time
from datetime import datetime

# Add utils to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils'))

# Set Tesseract path early — before importing P1 modules.
# Point TESSERACT_PATH at your tesseract executable if it is not on PATH.
import os
import shutil
import pytesseract
TESSERACT_PATH = os.environ.get('TESSERACT_PATH') or shutil.which('tesseract')
if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

import config
from utils import inference_router
from utils import database
from utils import report_generator
from utils.outlook_monitor import OutlookMonitor, parse_msg_file, parse_email_file


# ═══════════════════════════════════════════════════════════
# Page configuration
# ═══════════════════════════════════════════════════════════

st.set_page_config(
    page_title='Email Analysis Demo',
    page_icon='📧',
    layout='wide',
    initial_sidebar_state='expanded',
)

# Custom CSS
st.markdown('''
<style>
.main-header { background: linear-gradient(135deg, #1a365d, #2b6cb0); color: white;
               padding: 20px; border-radius: 8px; margin-bottom: 20px; }
.main-header h1 { color: white; margin: 0; }
.status-ok { color: #2f855a; font-weight: bold; }
.status-error { color: #c53030; font-weight: bold; }
.status-warning { color: #d69e2e; font-weight: bold; }
.metric-box { background: #ebf8ff; padding: 15px; border-radius: 8px;
              text-align: center; border-left: 4px solid #2b6cb0; }
</style>
''', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# Session state initialization
# ═══════════════════════════════════════════════════════════

if 'page' not in st.session_state:
    st.session_state.page = 'setup'
if 'mode' not in st.session_state:
    st.session_state.mode = None
if 'paradigm' not in st.session_state:
    st.session_state.paradigm = 'P1'
if 'backend_url' not in st.session_state:
    st.session_state.backend_url = config.COLAB_BACKEND_URL
if 'outlook_monitor' not in st.session_state:
    st.session_state.outlook_monitor = None
if 'live_running' not in st.session_state:
    st.session_state.live_running = False
if 'processed_count' not in st.session_state:
    st.session_state.processed_count = 0


# ═══════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════

with st.sidebar:
    st.title('📧 Email Analysis Demo')
    st.markdown('---')

    # Navigation
    page_options = {
        'setup': '⚙️ Setup',
        'mode': '🎯 Mode Selection',
        'live': '🔴 Live Monitor',
        'upload': '📤 Upload Mode',
        'report': '📊 Report',
    }

    for page_key, page_label in page_options.items():
        if st.button(page_label, key=f'nav_{page_key}', width='stretch'):
            st.session_state.page = page_key
            st.rerun()

    st.markdown('---')

    # Status indicators
    st.subheader('Status')
    backend_status = inference_router.check_backend(st.session_state.backend_url)
    if backend_status.get('available'):
        st.markdown(
            f'<span class="status-ok">● Backend OK</span><br>'
            f'<small>{backend_status.get("gpu", "?")}</small>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<span class="status-error">● Backend Offline</span><br>'
            f'<small>{backend_status.get("reason", "?")}</small>',
            unsafe_allow_html=True
        )

    if st.session_state.outlook_monitor and st.session_state.outlook_monitor.is_connected():
        st.markdown('<span class="status-ok">● Outlook Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-warning">○ Outlook Not Connected</span>', unsafe_allow_html=True)

    st.markdown('---')
    st.caption(f'Paradigm: **{config.PARADIGMS[st.session_state.paradigm]["name"]}**')


# ═══════════════════════════════════════════════════════════
# Helper: process and save email
# ═══════════════════════════════════════════════════════════

def process_email(email_data: dict, paradigm: str) -> dict:
    """Process a single email with the selected paradigm and save to DB."""
    # Find primary attachment (PDF or image)
    attachment_path = None
    for att in email_data.get('attachments', []):
        if att.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            attachment_path = att
            break

    # Run inference
    result = inference_router.run_inference(
        paradigm=paradigm,
        subject=email_data.get('subject', ''),
        body=email_data.get('body', ''),
        attachment_path=attachment_path,
        backend_url=st.session_state.backend_url,
    )

    # Save to DB
    database.save_analysis(email_data, result)

    return result


# ═══════════════════════════════════════════════════════════
# Page: Setup
# ═══════════════════════════════════════════════════════════

def show_setup():
    st.markdown('<div class="main-header"><h1>⚙️ Setup</h1>'
                '<p>Configure backend connection and verify everything is ready</p></div>',
                unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader('Colab Backend URL')
        st.write('Paste the ngrok URL from your Colab backend notebook:')
        new_url = st.text_input(
            'Backend URL',
            value=st.session_state.backend_url,
            placeholder='https://abc123.ngrok-free.app',
            help='Get this from the Colab notebook after starting the FastAPI server',
        )
        if new_url != st.session_state.backend_url:
            st.session_state.backend_url = new_url
            config.COLAB_BACKEND_URL = new_url
            st.rerun()

        if st.button('🔄 Test Connection', type='primary'):
            with st.spinner('Testing...'):
                status = inference_router.check_backend(st.session_state.backend_url)
            if status.get('available'):
                st.success(f'✅ Backend is reachable!')
                st.json(status)
            else:
                st.error(f'❌ Cannot reach backend: {status.get("reason")}')

    with col2:
        st.subheader('Quick Reference')
        st.markdown('''
        **Backend setup:**
        1. Open `colab_backend.ipynb` on Colab Pro
        2. Set Runtime → T4 GPU
        3. Run all cells
        4. Copy the ngrok URL shown
        5. Paste it here

        **For Outlook live mode:**
        - Open Outlook desktop app
        - Make sure email is configured
        ''')

    st.markdown('---')

    # Configuration summary
    st.subheader('Current Configuration')
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric('Backend URL', '✓ Set' if st.session_state.backend_url else '✗ Empty')
    with col_b:
        st.metric('Project Path', '✓ Found' if os.path.exists(config.DISSERTATION_PATH) else '✗ Not found')
    with col_c:
        db_size = os.path.getsize(database.DB_PATH) if os.path.exists(database.DB_PATH) else 0
        st.metric('Database', f'{db_size/1024:.1f} KB')

    st.markdown('---')

    if st.button('Continue to Mode Selection →', type='primary', width='stretch'):
        st.session_state.page = 'mode'
        st.rerun()


# ═══════════════════════════════════════════════════════════
# Page: Mode Selection
# ═══════════════════════════════════════════════════════════

def show_mode_selection():
    st.markdown('<div class="main-header"><h1>🎯 Selectati Modul</h1>'
                '<p>Cum vreti sa procesati e-mailurile?</p></div>',
                unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('### 🔴 Live Monitor')
        st.markdown('''
        **Conectare directa la Outlook**

        - Monitorizeaza inbox-ul in timp real
        - Proceseaza automat e-mailurile noi pe masura ce vin
        - Necesita Outlook desktop deschis pe Windows
        - Ideal pentru demo live in fata comisiei
        ''')
        if st.button('🔴 Start Live Mode', type='primary', width='stretch'):
            st.session_state.mode = 'live'
            st.session_state.page = 'paradigm'
            st.rerun()

    with col2:
        st.markdown('### 📤 Upload Mode')
        st.markdown('''
        **Incarca fisiere .msg manual**

        - Atasezi un singur fisier sau un set
        - Util pentru testare si verificare
        - Functioneaza fara Outlook desktop
        - Bun pentru procesare batch
        ''')
        if st.button('📤 Start Upload Mode', type='primary', width='stretch'):
            st.session_state.mode = 'upload'
            st.session_state.page = 'paradigm'
            st.rerun()

    st.markdown('---')
    st.info('💡 Indiferent de mod, pe pagina urmatoare alegeti paradigma de procesare (P1/P2/P3).')


# ═══════════════════════════════════════════════════════════
# Page: Paradigm Selection
# ═══════════════════════════════════════════════════════════

def show_paradigm_selection():
    st.markdown('<div class="main-header"><h1>🧠 Selectati Paradigma</h1>'
                f'<p>Modul activ: <strong>{st.session_state.mode.upper()}</strong></p></div>',
                unsafe_allow_html=True)

    backend_status = inference_router.check_backend(st.session_state.backend_url)
    backend_ok = backend_status.get('available', False)

    cols = st.columns(3)

    paradigm_keys = ['P1', 'P2', 'P3']
    for i, p_key in enumerate(paradigm_keys):
        p = config.PARADIGMS[p_key]
        with cols[i]:
            st.markdown(f"### {p['name']}")
            st.markdown(p['description'])

            requires_backend = p['requires_backend']
            disabled = requires_backend and not backend_ok

            if requires_backend:
                if backend_ok:
                    st.markdown('<span class="status-ok">✓ Backend OK</span>',
                                unsafe_allow_html=True)
                else:
                    st.markdown('<span class="status-error">✗ Backend Required</span>',
                                unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-ok">✓ Functioneaza local</span>',
                            unsafe_allow_html=True)

            if st.button(f'Use {p_key}', key=f'choose_{p_key}',
                          disabled=disabled, width='stretch',
                          type='primary'):
                st.session_state.paradigm = p_key
                if st.session_state.mode == 'live':
                    st.session_state.page = 'live'
                else:
                    st.session_state.page = 'upload'
                st.rerun()

    if not backend_ok:
        st.warning('⚠️ Backend Colab nu e disponibil. Doar P1 poate rula in acest moment. '
                   'Mergi la Setup → Test Connection pentru detalii.')


# ═══════════════════════════════════════════════════════════
# Page: Live Monitor
# ═══════════════════════════════════════════════════════════

def show_live_monitor():
    st.markdown(f'<div class="main-header"><h1>🔴 Live Outlook Monitor</h1>'
                f'<p>Paradigma: <strong>{config.PARADIGMS[st.session_state.paradigm]["name"]}</strong></p></div>',
                unsafe_allow_html=True)

    # Connection control
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if not st.session_state.outlook_monitor or not st.session_state.outlook_monitor.is_connected():
            if st.button('🔌 Connect to Outlook', type='primary'):
                with st.spinner('Connecting...'):
                    monitor = OutlookMonitor()
                    if monitor.connect():
                        st.session_state.outlook_monitor = monitor
                        st.success('Connected!')
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error('Failed to connect. Make sure Outlook is open.')
        else:
            if st.button('🔌 Disconnect', type='secondary'):
                st.session_state.outlook_monitor = None
                st.session_state.live_running = False
                st.rerun()

    with col2:
        if st.session_state.outlook_monitor and st.session_state.outlook_monitor.is_connected():
            if not st.session_state.live_running:
                if st.button('▶️ Start Monitoring', type='primary'):
                    st.session_state.live_running = True
                    st.rerun()
            else:
                if st.button('⏸️ Pause', type='secondary'):
                    st.session_state.live_running = False
                    st.rerun()

    with col3:
        if st.session_state.outlook_monitor:
            info = st.session_state.outlook_monitor.get_account_info()
            if info:
                st.info(f'📬 **{info.get("display_name","")}** ({info.get("email","")})')

    st.markdown('---')

    # Status
    if st.session_state.live_running:
        st.success(f'🟢 Monitoring active — checking every {config.OUTLOOK_POLL_INTERVAL}s')
    else:
        st.info('⏸️ Monitoring paused')

    # Recent processed
    st.subheader('Recent Processed Emails')
    recent = database.get_all_analyses(limit=10)
    if recent:
        import json
        for a in recent:
            received = a.get('received') or ''
            # Prefer the actual reception time in the title; fall back to processing time
            title_time = received[:19] if received and received != 'uploaded' else a['timestamp'][:19]
            with st.expander(f'{title_time} — {a["subject"][:60]}'):
                # Recover full field detail so Live shows the same card as Upload Mode
                try:
                    fr = json.loads(a.get('full_result') or '{}')
                except Exception:
                    fr = {}
                email_fields = fr.get('email_fields') or {
                    'amount': a.get('email_amount') or None,
                    'currency': a.get('email_currency') or None,
                    'doc_number': a.get('email_doc_number') or None,
                    'date': a.get('email_date') or None,
                }
                document_fields = fr.get('document_fields') or {
                    'amount': a.get('doc_amount') or None,
                    'currency': a.get('doc_currency') or None,
                    'doc_number': a.get('doc_doc_number') or None,
                    'date': a.get('doc_date') or None,
                }

                col_a, col_b = st.columns(2)
                with col_a:
                    st.write(f'**From:** {a["sender"]}')
                    st.write(f'**Received:** {received or "—"}')
                    st.write(f'**Paradigm:** {a["paradigm"]}')
                    st.write(f'**Intent:** {a["intent"]}')
                    st.write('**Email fields:**')
                    for k, v in email_fields.items():
                        st.write(f'  {k}: {v}')
                with col_b:
                    st.write('**Document fields:**')
                    for k, v in document_fields.items():
                        st.write(f'  {k}: {v}')
                    if a['is_consistent'] == 1:
                        st.success('✅ Consistent')
                    elif a['is_consistent'] == 0:
                        try:
                            mf = json.loads(a['mismatched_fields'])
                        except Exception:
                            mf = []
                        st.error(f'❌ Mismatch: {", ".join(mf)}' if mf else '❌ Mismatch')
                    else:
                        st.info('— No comparison possible')
                    try:
                        errs = json.loads(a.get('errors') or '[]')
                    except Exception:
                        errs = []
                    if errs:
                        st.warning(f'⚠️ Errors: {", ".join(errs)}')
    else:
        st.write('No emails processed yet.')

    # Auto-refresh and process loop
    if st.session_state.live_running and st.session_state.outlook_monitor:
        # Poll for new emails
        new_emails = st.session_state.outlook_monitor.get_new_emails(
            limit=config.OUTLOOK_MAX_PER_POLL
        )

        if new_emails:
            st.balloons()
            for email_data in new_emails:
                with st.spinner(f'Processing: {email_data["subject"][:50]}...'):
                    result = process_email(email_data, st.session_state.paradigm)
                    st.session_state.processed_count += 1

        # Auto-refresh after polling interval
        time.sleep(config.OUTLOOK_POLL_INTERVAL)
        st.rerun()


# ═══════════════════════════════════════════════════════════
# Page: Upload Mode
# ═══════════════════════════════════════════════════════════

def show_upload_mode():
    st.markdown(f'<div class="main-header"><h1>📤 Upload Mode</h1>'
                f'<p>Paradigma: <strong>{config.PARADIGMS[st.session_state.paradigm]["name"]}</strong></p></div>',
                unsafe_allow_html=True)

    upload_type = st.radio(
        'Tipul incarcarii',
        ['Single file', 'Bulk (multiple files)'],
        horizontal=True,
    )

    if upload_type == 'Single file':
        uploaded = st.file_uploader('Incarcati fisier .msg sau .eml', type=['msg', 'eml'], accept_multiple_files=False)
        files = [uploaded] if uploaded else []
    else:
        files = st.file_uploader('Incarcati mai multe fisiere .msg / .eml (sau o arhiva .zip)', type=['msg', 'eml', 'zip'], accept_multiple_files=True)

    if files:
        st.write(f'**{len(files)} fisier(e) incarcat(e)**')

        if st.button('🚀 Proceseaza Toate', type='primary'):
            results = []
            progress = st.progress(0)
            status_box = st.empty()

            import tempfile
            import zipfile

            # Build a flat work list, expanding any .zip into its .msg/.eml members
            work_items = []  # list of (display_name, path_on_disk)
            for uploaded_file in files:
                tmp_dir = tempfile.mkdtemp()
                tmp_path = os.path.join(tmp_dir, uploaded_file.name)
                with open(tmp_path, 'wb') as f:
                    f.write(uploaded_file.getvalue())

                if uploaded_file.name.lower().endswith('.zip'):
                    try:
                        extract_dir = os.path.join(tmp_dir, 'extracted')
                        os.makedirs(extract_dir, exist_ok=True)
                        with zipfile.ZipFile(tmp_path) as zf:
                            for member in zf.namelist():
                                base = os.path.basename(member)
                                # skip directories, hidden files and macOS metadata
                                if not base or member.endswith('/'):
                                    continue
                                if '__MACOSX' in member or base.startswith('.'):
                                    continue
                                if base.lower().endswith(('.msg', '.eml')):
                                    zf.extract(member, extract_dir)
                                    work_items.append((base, os.path.join(extract_dir, member)))
                    except Exception as e:
                        st.error(f'Nu am putut deschide arhiva {uploaded_file.name}: {e}')
                else:
                    work_items.append((uploaded_file.name, tmp_path))

            total = len(work_items)
            if total == 0:
                status_box.warning('Niciun fisier .msg/.eml de procesat (verificati continutul arhivei).')

            for i, (name, path) in enumerate(work_items):
                # Parse .msg / .eml
                status_box.info(f'Procesare {i+1}/{total}: {name}')
                email_data = parse_email_file(path)

                if email_data is None:
                    st.error(f'Failed to parse {name}')
                    progress.progress((i + 1) / total)
                    continue

                # Run inference
                result = process_email(email_data, st.session_state.paradigm)
                results.append({'email': email_data, 'result': result})

                progress.progress((i + 1) / total)

            status_box.success(f'✅ Procesat {len(results)}/{total} fisiere!')

            # Show results summary
            st.markdown('---')
            st.subheader('Rezultate')

            for item in results:
                email = item['email']
                result = item['result']
                with st.expander(f'📧 {email["subject"][:80]}'):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f'**From:** {email["sender"]}')
                        st.write(f'**Intent:** {result.get("intent")}')
                        st.write('**Email fields:**')
                        for k, v in result.get('email_fields', {}).items():
                            st.write(f'  {k}: {v}')
                    with col_b:
                        st.write('**Document fields:**')
                        for k, v in result.get('document_fields', {}).items():
                            st.write(f'  {k}: {v}')
                        if result.get('is_consistent') is True:
                            st.success('✅ Consistent')
                        elif result.get('is_consistent') is False:
                            st.error(f'❌ Mismatch: {", ".join(result.get("mismatched_fields", []))}')
                        if result.get('errors'):
                            st.warning(f'⚠️ Errors: {", ".join(result["errors"])}')


# ═══════════════════════════════════════════════════════════
# Page: Report
# ═══════════════════════════════════════════════════════════

def show_report():
    st.markdown('<div class="main-header"><h1>📊 Raport Analizare</h1>'
                '<p>Statistici si export pentru toate e-mailurile procesate</p></div>',
                unsafe_allow_html=True)

    stats = database.get_summary_stats()

    # Stats overview
    cols = st.columns(4)
    with cols[0]:
        st.metric('Total e-mailuri', stats['total'])
    with cols[1]:
        st.metric('Consistente', stats.get('consistent', 0))
    with cols[2]:
        st.metric('Neconcordante', stats.get('mismatched', 0))
    with cols[3]:
        if stats['total'] > 0:
            mm_rate = stats.get('mismatched', 0) / stats['total'] * 100
            st.metric('Rata neconcordante', f'{mm_rate:.1f}%')

    if stats['total'] == 0:
        st.info('Niciun e-mail procesat inca. Mergi la Live sau Upload pentru a procesa.')
        return

    st.markdown('---')

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        paradigm_filter = st.selectbox('Filtru paradigma', ['Toate', 'P1', 'P2', 'P3 Hybrid'])
    with col_f2:
        limit = st.number_input('Numar maxim de inregistrari', 10, 1000, 100)
    with col_f3:
        st.write('')
        st.write('')
        if st.button('🗑️ Sterge Toate Datele'):
            if st.session_state.get('confirm_delete'):
                database.clear_database()
                st.session_state.confirm_delete = False
                st.rerun()
            else:
                st.session_state.confirm_delete = True
                st.warning('Click again to confirm!')

    # Charts
    if stats.get('by_intent'):
        st.subheader('Distributie Intent')
        import pandas as pd
        df = pd.DataFrame(list(stats['by_intent'].items()), columns=['Intent', 'Count'])
        st.bar_chart(df.set_index('Intent'))

    if stats.get('mismatch_by_field'):
        st.subheader('Neconcordante per Camp')
        df_mm = pd.DataFrame(list(stats['mismatch_by_field'].items()),
                              columns=['Field', 'Mismatches'])
        st.bar_chart(df_mm.set_index('Field'))

    # Detail table
    st.subheader('Detalii E-mailuri')
    p_filter = None if paradigm_filter == 'Toate' else paradigm_filter
    analyses = database.get_all_analyses(limit=limit, paradigm=p_filter)

    if analyses:
        import pandas as pd
        df_data = []
        for a in analyses:
            df_data.append({
                'Timestamp': a['timestamp'][:19],
                'Sender': a['sender'][:30],
                'Subject': a['subject'][:50],
                'Paradigm': a['paradigm'],
                'Intent': a['intent'],
                'Email Amount': a['email_amount'],
                'Doc Amount': a['doc_amount'],
                'Status': '✅' if a['is_consistent'] == 1 else
                          ('❌' if a['is_consistent'] == 0 else '—'),
            })
        st.dataframe(pd.DataFrame(df_data), width='stretch')

    # Export
    st.markdown('---')
    st.subheader('Export Raport')

    col_e1, col_e2, col_e3 = st.columns(3)

    with col_e1:
        if st.button('📄 Genereaza HTML', width='stretch'):
            html = report_generator.generate_html_report(analyses, stats)
            output_path = os.path.join(config.REPORTS_DIR,
                                         f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html')
            report_generator.save_html_report(html, output_path)
            with open(output_path, 'rb') as f:
                st.download_button('⬇️ Download HTML', f.read(),
                                    file_name=os.path.basename(output_path),
                                    mime='text/html')

    with col_e2:
        if st.button('📕 Genereaza PDF', width='stretch'):
            html = report_generator.generate_html_report(analyses, stats)
            pdf_path = os.path.join(config.REPORTS_DIR,
                                      f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
            ok = report_generator.export_to_pdf(html, pdf_path)
            if ok:
                with open(pdf_path, 'rb') as f:
                    st.download_button('⬇️ Download PDF', f.read(),
                                        file_name=os.path.basename(pdf_path),
                                        mime='application/pdf')
            else:
                st.error('Install: pip install weasyprint')

    with col_e3:
        if st.button('📊 Export CSV', width='stretch'):
            csv_path = os.path.join(config.REPORTS_DIR,
                                      f'report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
            report_generator.generate_csv_export(analyses, csv_path)
            with open(csv_path, 'rb') as f:
                st.download_button('⬇️ Download CSV', f.read(),
                                    file_name=os.path.basename(csv_path),
                                    mime='text/csv')


# ═══════════════════════════════════════════════════════════
# Main router
# ═══════════════════════════════════════════════════════════

page = st.session_state.page

if page == 'setup':
    show_setup()
elif page == 'mode':
    show_mode_selection()
elif page == 'paradigm':
    show_paradigm_selection()
elif page == 'live':
    show_live_monitor()
elif page == 'upload':
    show_upload_mode()
elif page == 'report':
    show_report()
else:
    show_setup()
