"""
outlook_monitor.py
──────────────────
Monitors Outlook inbox for new emails using COM (pywin32).
Windows-only. Requires Outlook desktop installed.

Usage:
    monitor = OutlookMonitor()
    new_emails = monitor.get_new_emails()
    for email in new_emails:
        print(email['subject'], email['attachments'])
"""

import os
import tempfile
import datetime
from typing import List, Dict, Optional


class OutlookMonitor:
    """Monitor Outlook inbox for new emails."""

    def __init__(self):
        self.last_check_time = datetime.datetime.now()
        self.processed_ids = set()
        self._connected = False
        self._seeded = False

    def _get_inbox(self):
        """Initialize COM on the *current* thread and return (outlook, namespace, inbox).

        COM objects must be created and used on the same thread. Streamlit runs
        each rerun on a (possibly different) ScriptRunner thread, so we acquire
        fresh objects on every call instead of caching them across reruns.
        Late binding (dynamic.Dispatch) avoids stale/corrupt gen_py wrappers.
        """
        import pythoncom
        import win32com.client

        # Idempotent on an already-initialized STA thread (returns S_FALSE).
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        outlook = win32com.client.dynamic.Dispatch('Outlook.Application')
        namespace = outlook.GetNamespace('MAPI')
        inbox = namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
        return outlook, namespace, inbox

    def connect(self) -> bool:
        """Verify Outlook is reachable on this thread. Does NOT cache COM objects."""
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            print('ERROR: pywin32 not installed. Run: pip install pywin32')
            self._connected = False
            return False
        try:
            outlook, namespace, inbox = self._get_inbox()
            _ = inbox.Name  # touch a property to confirm the link works
            self._connected = True
            # Snapshot the EntryIDs already present, so the existing backlog
            # is treated as 'already seen' and only mail arriving afterwards
            # is reported as new. Detection is by EntryID, not by timestamp,
            # which avoids timezone / clock issues entirely.
            self._seed_inbox(inbox, depth=50)
            return True
        except Exception as e:
            print(f'ERROR connecting to Outlook: {e}')
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return bool(getattr(self, '_connected', False))

    def get_account_info(self) -> Dict:
        """Get current account information (re-acquires COM on this thread)."""
        try:
            outlook, namespace, inbox = self._get_inbox()
            accounts = namespace.Accounts
            if accounts.Count > 0:
                acc = accounts.Item(1)
                return {
                    'email': acc.SmtpAddress,
                    'display_name': acc.DisplayName,
                }
        except Exception:
            pass
        return {}

    def _seed_inbox(self, inbox, depth: int = 50) -> None:
        """Mark the currently-present emails as already seen (no processing)."""
        try:
            messages = inbox.Items
            messages.Sort('[ReceivedTime]', True)  # newest first
            count = 0
            for msg in messages:
                if count >= depth:
                    break
                count += 1
                try:
                    self.processed_ids.add(msg.EntryID)
                except Exception:
                    continue
            self._seeded = True
        except Exception as e:
            print(f'Error seeding inbox: {e}')

    def get_new_emails(self, limit: int = 10) -> List[Dict]:
        """
        Return emails that appeared since monitoring started.

        New mail is detected by EntryID (a unique, stable identifier), not by
        comparing timestamps. This sidesteps timezone and clock-skew problems:
        any message whose EntryID has not been seen before is considered new.
        On the first call (if not already seeded at connect time) the current
        inbox is recorded as 'already seen' so the existing backlog is ignored.
        """
        if not self.is_connected():
            return []

        try:
            outlook, namespace, inbox = self._get_inbox()

            # First contact: record the existing inbox and report nothing new.
            if not self._seeded:
                self._seed_inbox(inbox, depth=max(50, limit))
                return []

            messages = inbox.Items
            messages.Sort('[ReceivedTime]', True)  # newest first

            new_emails = []
            count = 0

            for msg in messages:
                if count >= limit:
                    break
                count += 1

                try:
                    msg_id = msg.EntryID

                    # Already seen (backlog or processed earlier) -> skip
                    if msg_id in self.processed_ids:
                        continue

                    # Genuinely new -> process it
                    email_data = self._process_message(msg)
                    if email_data:
                        new_emails.append(email_data)
                    # Mark as seen even if processing failed, to avoid retry spam
                    self.processed_ids.add(msg_id)

                except Exception as e:
                    print(f'Error processing message: {e}')
                    continue

            self.last_check_time = datetime.datetime.now()
            return new_emails

        except Exception as e:
            print(f'Error reading inbox: {e}')
            return []

    def _process_message(self, msg) -> Optional[Dict]:
        """Extract data from a message object."""
        try:
            subject = msg.Subject or ''
            body = msg.Body or ''
            sender = msg.SenderEmailAddress or msg.SenderName or 'unknown'

            # Extract attachments
            attachments = []
            temp_dir = tempfile.mkdtemp(prefix='outlook_att_')

            for att in msg.Attachments:
                try:
                    filename = att.FileName
                    filepath = os.path.join(temp_dir, filename)
                    att.SaveAsFile(filepath)
                    attachments.append(filepath)
                except Exception as e:
                    print(f'Error saving attachment: {e}')

            return {
                'id': msg.EntryID,
                'subject': subject,
                'body': body,
                'sender': sender,
                'received': str(msg.ReceivedTime),
                'attachments': attachments,
            }
        except Exception as e:
            print(f'Error extracting message data: {e}')
            return None

    def reset_processed(self):
        """Clear processed IDs - useful for re-running."""
        self.processed_ids.clear()
        self.last_check_time = datetime.datetime.now()
        self._seeded = False


def parse_msg_file(msg_path: str) -> Optional[Dict]:
    """Parse a .msg file (uploaded file, no Outlook needed)."""
    try:
        import extract_msg
    except ImportError:
        print('ERROR: extract-msg not installed. Run: pip install extract-msg')
        return None

    try:
        msg = extract_msg.Message(msg_path)
        subject = msg.subject or ''
        sender = msg.sender or ''
        body = msg.body or ''

        # Try HTML body if plain is empty
        if not body.strip():
            html_body = msg.htmlBody
            if html_body:
                if isinstance(html_body, bytes):
                    html_body = html_body.decode('utf-8', errors='ignore')
                import re
                text = re.sub(r'<style[^>]*>.*?</style>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</(p|div|tr|li)>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'<[^>]+>', '', text)
                text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
                text = re.sub(r'\n\s*\n', '\n\n', text)
                body = text.strip()

        # Extract attachments
        temp_dir = tempfile.mkdtemp(prefix='msg_att_')
        attachments = []
        for att in msg.attachments:
            filename = att.longFilename or att.shortFilename
            if filename:
                try:
                    att.save(customPath=temp_dir)
                    filepath = os.path.join(temp_dir, filename)
                    if os.path.exists(filepath):
                        attachments.append(filepath)
                    else:
                        for f in os.listdir(temp_dir):
                            full = os.path.join(temp_dir, f)
                            if full not in attachments:
                                attachments.append(full)
                except Exception as e:
                    print(f'Error saving attachment: {e}')

        result = {
            'id': os.path.basename(msg_path),
            'subject': str(subject).replace('\x00', '').strip(),
            'body': str(body).replace('\x00', '').strip(),
            'sender': str(sender).replace('\x00', '').strip(),
            'received': 'uploaded',
            'attachments': attachments,
        }
        msg.close()
        return result

    except Exception as e:
        print(f'Error parsing .msg: {e}')
        return None


def parse_eml_file(eml_path: str) -> Optional[Dict]:
    """Parse a standard .eml file (RFC822, no Outlook needed)."""
    import email
    from email import policy

    try:
        with open(eml_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        subject = msg.get('subject', '') or ''
        sender = msg.get('from', '') or ''

        # Prefer the plain-text body; fall back to stripped HTML
        body = ''
        html_body = ''
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get('Content-Disposition') or '')
                if 'attachment' in disp:
                    continue
                if ctype == 'text/plain' and not body:
                    try:
                        body = part.get_content()
                    except Exception:
                        body = part.get_payload(decode=True).decode(
                            part.get_content_charset() or 'utf-8', errors='ignore')
                elif ctype == 'text/html' and not html_body:
                    try:
                        html_body = part.get_content()
                    except Exception:
                        html_body = part.get_payload(decode=True).decode(
                            part.get_content_charset() or 'utf-8', errors='ignore')
        else:
            ctype = msg.get_content_type()
            payload = msg.get_content()
            if ctype == 'text/html':
                html_body = payload
            else:
                body = payload

        if not str(body).strip() and html_body:
            import re
            text = re.sub(r'<style[^>]*>.*?</style>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</(p|div|tr|li)>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
            text = re.sub(r'\n\s*\n', '\n\n', text)
            body = text.strip()

        # Extract attachments to a temp folder
        temp_dir = tempfile.mkdtemp(prefix='eml_att_')
        attachments = []
        for part in msg.iter_attachments() if hasattr(msg, 'iter_attachments') else []:
            filename = part.get_filename()
            if not filename:
                continue
            try:
                data = part.get_payload(decode=True)
                if data is None:
                    continue
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, 'wb') as out:
                    out.write(data)
                attachments.append(filepath)
            except Exception as e:
                print(f'Error saving attachment: {e}')

        return {
            'id': os.path.basename(eml_path),
            'subject': str(subject).replace('\x00', '').strip(),
            'body': str(body).replace('\x00', '').strip(),
            'sender': str(sender).replace('\x00', '').strip(),
            'received': 'uploaded',
            'attachments': attachments,
        }

    except Exception as e:
        print(f'Error parsing .eml: {e}')
        return None


def parse_email_file(path: str) -> Optional[Dict]:
    """Dispatch to the right parser based on file extension (.msg or .eml)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.eml':
        return parse_eml_file(path)
    return parse_msg_file(path)


if __name__ == '__main__':
    # Test
    monitor = OutlookMonitor()
    if monitor.connect():
        print('Connected to Outlook!')
        info = monitor.get_account_info()
        print(f'Account: {info}')
        emails = monitor.get_new_emails(limit=5)
        print(f'Found {len(emails)} recent emails')
        for e in emails:
            print(f'  {e["received"]}: {e["subject"]}')
    else:
        print('Could not connect to Outlook')
