"""
report_generator.py
───────────────────
Generates HTML reports from analyzed emails.
Optionally exports to PDF using weasyprint (if installed).
"""

import os
import json
from datetime import datetime
from typing import List, Dict


def _format_value(val):
    """Format a value for display."""
    if val is None or val == '':
        return '<span style="color:#999;">—</span>'
    return str(val)


def _format_consistency(is_consistent, mismatched_fields):
    """Format consistency status with color."""
    if is_consistent is None:
        return '<span style="color:#999;">N/A</span>'
    if is_consistent == 1 or is_consistent is True:
        return '<span style="color:#2f855a;font-weight:bold;">✓ CONSISTENT</span>'
    fields = ''
    if mismatched_fields:
        try:
            if isinstance(mismatched_fields, str):
                mf = json.loads(mismatched_fields)
            else:
                mf = mismatched_fields
            fields = ', '.join(mf)
        except: pass
    return f'<span style="color:#c53030;font-weight:bold;">✗ MISMATCH</span> <small>({fields})</small>'


def generate_html_report(analyses: List[Dict], stats: Dict, title: str = 'Email Analysis Report') -> str:
    """Generate an HTML report from analyses."""

    # Stats section
    stats_html = '<div class="stats-grid">'
    stats_html += f'<div class="stat-card"><div class="stat-num">{stats["total"]}</div><div class="stat-lbl">Total emails</div></div>'
    stats_html += f'<div class="stat-card"><div class="stat-num" style="color:#2f855a;">{stats.get("consistent",0)}</div><div class="stat-lbl">Consistent</div></div>'
    stats_html += f'<div class="stat-card"><div class="stat-num" style="color:#c53030;">{stats.get("mismatched",0)}</div><div class="stat-lbl">Mismatches</div></div>'

    by_paradigm = stats.get('by_paradigm', {})
    paradigm_str = ', '.join([f'{k}: {v}' for k, v in by_paradigm.items()])
    stats_html += f'<div class="stat-card"><div class="stat-num" style="font-size:14px;">{paradigm_str}</div><div class="stat-lbl">By paradigm</div></div>'
    stats_html += '</div>'

    # Intent breakdown
    intent_html = '<h3>Intent Distribution</h3><table class="mini-table">'
    intent_html += '<tr><th>Intent</th><th>Count</th></tr>'
    for intent, count in sorted(stats.get('by_intent', {}).items(), key=lambda x: -x[1]):
        intent_html += f'<tr><td>{intent}</td><td>{count}</td></tr>'
    intent_html += '</table>'

    # Mismatch breakdown
    mm_html = ''
    if stats.get('mismatch_by_field'):
        mm_html = '<h3>Mismatches by Field</h3><table class="mini-table">'
        mm_html += '<tr><th>Field</th><th>Count</th></tr>'
        for field, count in sorted(stats['mismatch_by_field'].items(), key=lambda x: -x[1]):
            mm_html += f'<tr><td>{field}</td><td>{count}</td></tr>'
        mm_html += '</table>'

    # Email details
    rows_html = ''
    for a in analyses:
        errors = ''
        try:
            err_list = json.loads(a.get('errors', '[]'))
            if err_list:
                errors = '<small style="color:#c53030;">⚠ ' + '; '.join(err_list[:2]) + '</small>'
        except: pass

        attachments = ''
        try:
            att_list = json.loads(a.get('attachments', '[]'))
            if att_list:
                attachments = ', '.join(att_list)
        except: pass

        rows_html += f'''
        <tr>
            <td><small>{a.get("timestamp","")[:19]}</small></td>
            <td><strong>{a.get("sender","")[:30]}</strong></td>
            <td>{a.get("subject","")[:50]}</td>
            <td><span class="badge">{a.get("paradigm","")}</span></td>
            <td><span class="intent">{a.get("intent","")}</span></td>
            <td><small>{_format_value(a.get("email_amount"))} {a.get("email_currency","")}</small></td>
            <td><small>{_format_value(a.get("doc_amount"))} {a.get("doc_currency","")}</small></td>
            <td>{_format_consistency(a.get("is_consistent"), a.get("mismatched_fields"))}</td>
            <td><small>{attachments}</small>{errors}</td>
        </tr>
        '''

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, Arial, sans-serif; max-width: 1400px; margin: 20px auto; padding: 20px; color: #2d3748; }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #2b6cb0; padding-bottom: 10px; }}
        h2 {{ color: #2b6cb0; margin-top: 30px; }}
        h3 {{ color: #4a5568; margin-top: 20px; }}
        .header {{ background: linear-gradient(135deg, #1a365d, #2b6cb0); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ color: white; border: none; margin: 0; }}
        .header .meta {{ opacity: 0.9; margin-top: 8px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #ebf8ff; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #2b6cb0; }}
        .stat-num {{ font-size: 32px; font-weight: bold; color: #2b6cb0; }}
        .stat-lbl {{ font-size: 13px; color: #4a5568; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: white; }}
        th {{ background: #1a365d; color: white; padding: 10px; text-align: left; font-size: 13px; }}
        td {{ padding: 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; vertical-align: top; }}
        tr:nth-child(even) {{ background: #f7fafc; }}
        tr:hover {{ background: #ebf8ff; }}
        .mini-table {{ width: auto; min-width: 300px; }}
        .badge {{ background: #2b6cb0; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; }}
        .intent {{ background: #fef5e7; padding: 3px 8px; border-radius: 4px; font-size: 11px; color: #c05621; }}
        .footer {{ margin-top: 40px; text-align: center; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div class="meta">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
    </div>

    <h2>Summary</h2>
    {stats_html}

    <div style="display: flex; gap: 30px; flex-wrap: wrap;">
        {intent_html}
        {mm_html}
    </div>

    <h2>Email Details ({len(analyses)} entries)</h2>
    <table>
        <thead>
            <tr>
                <th>Timestamp</th>
                <th>Sender</th>
                <th>Subject</th>
                <th>Paradigm</th>
                <th>Intent</th>
                <th>Email Amount</th>
                <th>Doc Amount</th>
                <th>Status</th>
                <th>Notes</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="footer">
        Generated by Email Analysis System | Disertatie 2026 | Ion Florentin-Georgian
    </div>
</body>
</html>'''
    return html


def save_html_report(html_content: str, output_path: str):
    """Save HTML report to file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def export_to_pdf(html_content: str, output_path: str) -> bool:
    """Export HTML to PDF using weasyprint (optional)."""
    try:
        from weasyprint import HTML
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        HTML(string=html_content).write_pdf(output_path)
        return True
    except ImportError:
        print('weasyprint not installed — PDF export unavailable')
        print('Install: pip install weasyprint')
        return False
    except Exception as e:
        print(f'PDF export error: {e}')
        return False


def generate_csv_export(analyses: List[Dict], output_path: str):
    """Export analyses to CSV for further processing."""
    import csv
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fields = [
        'timestamp', 'sender', 'subject', 'paradigm', 'intent',
        'email_amount', 'email_currency', 'email_doc_number', 'email_date',
        'doc_amount', 'doc_currency', 'doc_doc_number', 'doc_date',
        'is_consistent', 'mismatched_fields',
    ]

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for a in analyses:
            row = {k: a.get(k, '') for k in fields}
            writer.writerow(row)
