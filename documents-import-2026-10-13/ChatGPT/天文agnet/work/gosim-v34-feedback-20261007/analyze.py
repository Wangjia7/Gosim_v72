"""Read-only post-run audit; feedback factors are never fed into the agent."""
import collections
import bisect
import csv
import hashlib
import json
import re
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent / 'raw'
OUT = Path(__file__).resolve().parents[2] / 'outputs/gosim-v34-feedback'
OUT.mkdir(parents=True, exist_ok=True)
cards = []
requests = []
for folder in sorted(BASE.iterdir()):
    if not folder.is_dir():
        continue
    score = json.loads((folder / 'score_report.json').read_text())
    workflow = json.loads((folder / 'workflow_result.json').read_text())
    decisions = list(csv.DictReader((folder / 'decisions.csv').open()))
    observations = list(csv.DictReader((folder / 'observations.csv').open()))
    messages = [json.loads(line) for line in (folder / 'messages.jsonl').open()]
    exposures = {d['observe_index']: d for d in decisions if d['action'] == 'observe'}
    by_target = collections.defaultdict(list)
    by_exposure = collections.defaultdict(list)
    monthly = collections.defaultdict(list)
    all_best, valid_best = collections.defaultdict(float), collections.defaultdict(float)
    for o in observations:
        d = exposures[o['observe_index']]
        by_target[o['target_id']].append((d, o))
        by_exposure[o['observe_index']].append(o)
        monthly[d['start_utc'][:7]].append(float(o['factor']))
        all_best[o['target_id']] = max(all_best[o['target_id']], float(o['score']))
        if o['valid'] == 'true':
            valid_best[o['target_id']] = max(valid_best[o['target_id']], float(o['score']))
    # Six decimal CSV rounding can add up. Check rather than silently overwrite official totals.
    assert abs(sum(valid_best.values()) - score['components']['sum_best_scores']) < .1
    assert abs(sum(score['components'].values()) - score['total']) < 1e-4
    failures = []
    for r in score['observation_requests']:
        if r['completion_reward'] <= 0:
            continue  # zero reward handover notes are not paid follow-up failures
        rows = []
        for tid in r['target_ids']:
            inside = [(d, o) for d, o in by_target[tid]
                      if r['issued_at_utc'] <= d['start_utc'] and d['end_utc'] <= r['deadline_utc']]
            good = [float(o['factor']) for _, o in inside if o['valid'] == 'true']
            rows.append({'target_id': tid, 'inside_rows': len(inside),
                         'valid_inside_rows': len(good), 'best_factor': max(good, default=0),
                         'exposures_anytime': len(by_target[tid])})
        # Use official completion status; rounding at threshold may disagree with CSV.
        item = {'card': folder.name, 'request_id': r['request_id'],
                'completed': r['completed'], 'minimum_completed': r['minimum_completed'],
                'official_completed_count': r['completed_count'],
                'reward_possible': r['completion_reward'], 'reward_earned': r['reward'],
                'issued': r['issued_at_utc'], 'deadline': r['deadline_utc'], 'targets': rows}
        requests.append(item)
        if not r['completed']:
            failures.append(item['request_id'])
    notes = [m.get('reason', '') for m in messages if m.get('record_type') == 'observation_request'
             and m.get('reason') != 'time-critical follow-up']
    reports = [m for m in messages if m.get('record_type') == 'report_result']
    log = (folder / 'agent.log').read_text()
    e_rows = [(float(e), float(s), float(b)) for e, s, b in re.findall(
        r'pro: E \S+ ([0-9.]+) scale ([0-9.]+) band ([0-9.]+)', log)]
    zero_exposures = [i for i, rows in by_exposure.items() if all(float(o['score']) == 0 for o in rows)]
    bulletins = sorted((m for m in messages if m.get('record_type') == 'bulletin'), key=lambda m: m['issued_at_utc'])
    bulletin_times = [m['issued_at_utc'] for m in bulletins]
    zero_with_closure = 0
    for i in zero_exposures:
        at = bisect.bisect_right(bulletin_times, exposures[i]['start_utc']) - 1
        notices = bulletins[at].get('notices', []) if at >= 0 else []
        zero_with_closure += any(n.get('event_kind') in ('rain', 'storm') and n.get('direction') == 'ALL' for n in notices)
    card = {'card': folder.name, 'scenario': score['scenario'], 'total': score['total'],
            'components': score['components'], 'counts': score['counts'],
            'clock': workflow['fair_clock'], 'termination': workflow['termination_reason'],
            'route_observed_in_log': 'enhanced' if 'family=enhanced' in log else 'fusion_core' if 'family=fusion_core' in log else 'unknown',
            'reports_correct': sum(m['correct'] for m in reports),
            'reports_false': sum(not m['correct'] for m in reports),
            'paid_requests': len(failures) + sum(r['completed'] for r in score['observation_requests'] if r['completion_reward'] > 0),
            'paid_completed': sum(r['completed'] for r in score['observation_requests'] if r['completion_reward'] > 0),
            'paid_reward_available': sum(r['completion_reward'] for r in score['observation_requests']),
            'failed_paid_ids': failures,
            'handover_notes': len(notes), 'notes_over_2000_chars': sum(len(t) > 2000 for t in notes),
            'notes_camera_only_after_2000': sum('导星相机' in t and '导星相机' not in t[:2000] for t in notes),
            'log_truncated': 'earlier output was truncated' in log,
            'retained_E_rows': len(e_rows), 'retained_E_normal_and_scale_floor': sum(e >= .99 and s <= .051 for e, s, _ in e_rows),
            'assigned': sum(int(d['assigned_count']) for d in exposures.values()),
            'hits': sum(int(d['hit_count']) for d in exposures.values()),
            'zero_score_rows': sum(float(o['score']) == 0 for o in observations),
            'all_zero_exposures': len(zero_exposures),
            'all_zero_with_explicit_allsky_rainstorm_at_start': zero_with_closure,
            'all_zero_exposure_seconds': sum(float(exposures[i]['duration_seconds']) for i in zero_exposures),
            'total_exposure_seconds': sum(float(d['duration_seconds']) for d in exposures.values()),
            'factor_median': statistics.median(float(o['factor']) for o in observations),
            'factor_at_least_half_rows': sum(float(o['factor']) >= .5 for o in observations),
            'final_science_loss_from_invalidation_csv': sum(all_best.values()) - sum(valid_best.values()),
            'monthly': {month: {'rows': len(factors), 'median_factor': statistics.median(factors),
                               'fraction_factor_at_least_half': sum(f >= .5 for f in factors) / len(factors)}
                        for month, factors in monthly.items()},
            'reports': reports,
            'file_hashes': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.iterdir() if f.is_file()}}
    cards.append(card)
    print(folder.name, round(card['total'], 2), 'paid', card['paid_completed'], '/', card['paid_requests'],
          'zero hours', round(card['all_zero_exposure_seconds'] / 3600, 2),
          'invalidation science loss', round(card['final_science_loss_from_invalidation_csv'], 3))
(OUT / 'metrics.json').write_text(json.dumps(cards, ensure_ascii=False, indent=2) + '\n')
(OUT / 'paid-request-audit.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2) + '\n')
with (OUT / 'score-summary.csv').open('w') as f:
    w = csv.writer(f)
    w.writerow(['card','total','science','required_penalty','report_reward','request_reward','uniformity','missing','paid_completed','paid_total','charged_cpu','run_wall','termination'])
    for c in cards:
        v = c['components']
        w.writerow([c['card'], c['total'], v['sum_best_scores'], v['required_penalty'], v['report_settlement'],
                    v['observation_request_reward'], v['uniformity_penalty'], c['counts']['required_missing'],
                    c['paid_completed'], c['paid_requests'], c['clock']['charged_seconds'], c['clock']['run_wall_seconds'], c['termination']])
