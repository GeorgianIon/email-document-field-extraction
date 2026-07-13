"""
database.py
───────────
SQLite database for storing email analysis results.
Persists across sessions, enables historical reporting.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'demo_data', 'analyses.db')


def init_db():
    """Initialize database schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT,
            timestamp TEXT,
            sender TEXT,
            subject TEXT,
            body TEXT,
            received TEXT,
            attachments TEXT,
            paradigm TEXT,
            intent TEXT,
            email_amount TEXT,
            email_currency TEXT,
            email_doc_number TEXT,
            email_date TEXT,
            doc_amount TEXT,
            doc_currency TEXT,
            doc_doc_number TEXT,
            doc_date TEXT,
            is_consistent INTEGER,
            mismatched_fields TEXT,
            errors TEXT,
            full_result TEXT
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_email_id ON analyses(email_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON analyses(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_paradigm ON analyses(paradigm)')
    conn.commit()
    conn.close()


def save_analysis(email_data: Dict, result: Dict) -> int:
    """Save an analysis result to the database. Returns the inserted row ID."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    ef = result.get('email_fields', {})
    df = result.get('document_fields', {})

    is_consistent_int = None
    if result.get('is_consistent') is not None:
        is_consistent_int = 1 if result['is_consistent'] else 0

    c.execute('''
        INSERT INTO analyses (
            email_id, timestamp, sender, subject, body, received, attachments,
            paradigm, intent,
            email_amount, email_currency, email_doc_number, email_date,
            doc_amount, doc_currency, doc_doc_number, doc_date,
            is_consistent, mismatched_fields, errors, full_result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        email_data.get('id', ''),
        datetime.now().isoformat(),
        email_data.get('sender', ''),
        email_data.get('subject', ''),
        email_data.get('body', '')[:2000],
        email_data.get('received', ''),
        json.dumps([os.path.basename(a) for a in email_data.get('attachments', [])]),
        result.get('paradigm', ''),
        result.get('intent', ''),
        str(ef.get('amount', '')) if ef.get('amount') is not None else '',
        ef.get('currency', '') or '',
        ef.get('doc_number', '') or '',
        ef.get('date', '') or '',
        str(df.get('amount', '')) if df.get('amount') is not None else '',
        df.get('currency', '') or '',
        df.get('doc_number', '') or '',
        df.get('date', '') or '',
        is_consistent_int,
        json.dumps(result.get('mismatched_fields', [])),
        json.dumps(result.get('errors', [])),
        json.dumps(result),
    ))

    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_all_analyses(limit: int = 100, paradigm: Optional[str] = None) -> List[Dict]:
    """Retrieve recent analyses."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if paradigm:
        c.execute(
            'SELECT * FROM analyses WHERE paradigm = ? ORDER BY id DESC LIMIT ?',
            (paradigm, limit)
        )
    else:
        c.execute(
            'SELECT * FROM analyses ORDER BY id DESC LIMIT ?',
            (limit,)
        )

    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


def get_summary_stats() -> Dict:
    """Compute summary statistics."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    stats = {}

    # Total
    c.execute('SELECT COUNT(*) FROM analyses')
    stats['total'] = c.fetchone()[0]

    # By paradigm
    c.execute('SELECT paradigm, COUNT(*) FROM analyses GROUP BY paradigm')
    stats['by_paradigm'] = dict(c.fetchall())

    # By intent
    c.execute('SELECT intent, COUNT(*) FROM analyses GROUP BY intent')
    stats['by_intent'] = dict(c.fetchall())

    # Consistency
    c.execute('SELECT is_consistent, COUNT(*) FROM analyses WHERE is_consistent IS NOT NULL GROUP BY is_consistent')
    consistency = dict(c.fetchall())
    stats['consistent'] = consistency.get(1, 0)
    stats['mismatched'] = consistency.get(0, 0)

    # By sender
    c.execute('SELECT sender, COUNT(*) as cnt FROM analyses GROUP BY sender ORDER BY cnt DESC LIMIT 5')
    stats['top_senders'] = c.fetchall()

    # Mismatch by field
    c.execute('SELECT mismatched_fields FROM analyses WHERE is_consistent = 0')
    field_counts = {}
    for row in c.fetchall():
        try:
            fields = json.loads(row[0])
            for f in fields:
                field_counts[f] = field_counts.get(f, 0) + 1
        except: pass
    stats['mismatch_by_field'] = field_counts

    conn.close()
    return stats


def clear_database():
    """Clear all records (for testing)."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM analyses')
    conn.commit()
    conn.close()


def email_already_processed(email_id: str, paradigm: str) -> bool:
    """Check if this email was already processed with this paradigm."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT COUNT(*) FROM analyses WHERE email_id = ? AND paradigm = ?',
        (email_id, paradigm)
    )
    count = c.fetchone()[0]
    conn.close()
    return count > 0
