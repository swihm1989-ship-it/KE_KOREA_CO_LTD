"""Same metrics for the explicitly labelled, bounded in-memory fallback."""
from collections import defaultdict


def _known_sum(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return sum(values) if values else None


def metrics(rows):
    count = len(rows)
    success = sum(r['status']=='success' for r in rows)
    durations = sorted(r['duration_ms'] for r in rows)
    position = (count-1)*.95 if count else 0
    lower = int(position)
    p95 = (durations[lower] + (durations[min(lower+1,count-1)]-durations[lower])*(position-lower)) if count else None
    return {
        'calls': count, 'successes': success, 'failures': count-success,
        'success_rate': round(100*success/count,2) if count else None,
        'failure_rate': round(100*(count-success)/count,2) if count else None,
        'avg_duration_ms': sum(durations)/count if count else None,
        'p95_duration_ms': p95,
        'input_tokens': _known_sum(rows,'input_tokens'),
        'output_tokens': _known_sum(rows,'output_tokens'),
        'cached_input_tokens': _known_sum(rows,'cached_input_tokens'),
        'estimated_cost_usd': _known_sum(rows,'estimated_cost_usd'),
        'unpriced_calls': sum(r.get('estimated_cost_usd') is None for r in rows),
        'missing_usage_calls': sum(r.get('input_tokens') is None or r.get('output_tokens') is None for r in rows),
        'retry_calls': sum(r.get('retry_count',0)>0 for r in rows),
    }


def local_summary(events):
    # Only finish events count. Each span is counted once, even after retries of storage.
    finished = {e['span_id']: e for e in events if e['event_type']=='finish'}
    ai = [e for e in finished.values() if e['task']=='ai.request']
    models, tasks, errors = defaultdict(list), defaultdict(list), defaultdict(int)
    for row in finished.values():
        tasks[(row['task'],row['document_kind'])].append(row)
        if row['task']=='ai.request':
            models[row['model']].append(row)
        if row['status']=='failure':
            errors[(row['task'],row['model'],row['error_type'],row['http_status'])] += 1
    return {
        'totals': metrics(ai),
        'models': [dict(model=model,**metrics(rows)) for model,rows in sorted(models.items())],
        'tasks': [dict(task=task,document_kind=kind,runs=len(rows),
                       failures=sum(r['status']=='failure' for r in rows),
                       avg_duration_ms=sum(r['duration_ms'] for r in rows)/len(rows))
                  for (task,kind),rows in tasks.items()],
        'errors': [dict(task=t,model=m,error_type=e,http_status=h,failures=n)
                   for (t,m,e,h),n in errors.items()],
        'daily': [], 'retention_days': 30,
    }
