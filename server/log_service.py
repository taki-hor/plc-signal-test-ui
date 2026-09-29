from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import csv
import io
import json
from threading import Lock

class LogService:
    def __init__(self, path: Path, secret: str = ''):
        self.path = path
        self.secret = secret
        self.entries = deque(maxlen=10000)
        self.lock = Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with path.open(encoding='utf-8') as saved:
                for line in deque(saved, maxlen=10000):
                    try: self.entries.append(self.scrub(json.loads(line)))
                    except json.JSONDecodeError: continue

    def scrub(self, value):
        if isinstance(value, str):
            return value.replace(self.secret, '[REDACTED]') if self.secret else value
        if isinstance(value, dict):
            return {k: ('[REDACTED]' if 'key' in k.lower() or 'token' in k.lower() else self.scrub(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        return value

    def add(self, event: str, **fields):
        entry = self.scrub({'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, **fields})
        with self.lock:
            self.entries.append(entry)
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return entry

    def get(self, kind: str = 'all'):
        with self.lock:
            entries = list(self.entries)
        return [e for e in entries if kind == 'all' or (kind == 'tests' and e['event'].startswith('TEST_')) or (kind == 'communication' and not e['event'].startswith('TEST_'))]

    def export(self, kind: str, format: str):
        rows = self.get(kind)
        if format == 'json':
            return json.dumps(rows, ensure_ascii=False, indent=2), 'application/json'
        columns = ['timestamp', 'event', 'test_name', 'command', 'expected_feedback', 'actual_feedback', 'result', 'elapsed_ms', 'http_status', 'error', 'tag_name', 'value']
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue(), 'text/csv'
