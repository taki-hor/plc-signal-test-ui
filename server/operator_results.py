"""Load explicit operator judgments without changing PLC or API evidence."""
from datetime import datetime
import json

from .api_checks import signature


def load_operator_results(path, context, tags):
    try:
        if not path.exists():
            return None, None
        saved = json.loads(path.read_text())
        if saved['format'] != 'operator-results-v1' or not isinstance(saved['records'], list):
            raise ValueError('Invalid operator result file')
        if saved['context'] != context:
            return None, None
        results = []
        for record in saved['records']:
            if (record['kind'] != 'human' or record['value'] not in ('pass', 'fail', 'unchecked')
                    or not datetime.fromisoformat(record['at']).tzinfo
                    or not isinstance(record['identity'], list) or len(record['identity']) != 5
                    or not isinstance(record['source'], str) or record.get('write_sent') is not False
                    or 'api_backfill_allowed' in record and type(record['api_backfill_allowed']) is not bool):
                raise ValueError('Invalid operator judgment')
            tag = tags.get(record['identity'][0])
            if tag is None or tag.read_write != 'W' or signature(tag) != record['identity']:
                continue
            results.append({key: record[key] for key in ('kind', 'identity', 'value', 'at', 'source',
                            'evidence_ref', 'observed_at', 'physical_stop_verified', 'write_sent', 'api_backfill_allowed') if key in record})
        return results, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return [], 'Saved operator results are unavailable. Previously loaded judgments are retained.'
