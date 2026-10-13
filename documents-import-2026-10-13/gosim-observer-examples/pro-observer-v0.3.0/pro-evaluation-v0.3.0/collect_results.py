"""Collect settled native-Python runs without reading scenario cards or changing runs."""
from pathlib import Path
import csv
import json
import math

ROOT_OUTPUTS = Path(__file__).resolve().parent.parent
OLD = ROOT_OUTPUTS / 'pro-evaluation-v0.2.0'
NEW = Path(__file__).resolve().parent
REFERENCE_LABELS = (
    'original-pro-py312', 'successor-py312', 'attached-9c656-py312',
    'attached-adaptive-py312', 'attached-wide-py312',
)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def complete(metadata):
    return (metadata.get('status') == 'success'
            and metadata.get('summary', {}).get('termination_reason') == 'survey_complete')


def gain(value, reference, field):
    baseline = reference.get('summary', {}).get(field)
    if not numeric(value) or not numeric(baseline) or baseline <= 0:
        return None
    return 100 * (value / baseline - 1)


def collect():
    paths = [path for label in REFERENCE_LABELS
             for path in (OLD / label).glob('*/benchmark.json')]
    paths.extend(NEW.glob('*/*/benchmark.json'))
    # A later control with the same label/card supersedes its old location.
    runs = {}
    for path in sorted(paths):
        metadata = load_json(path)
        summary = metadata.get('summary', {})
        if metadata.get('status') in (None, 'running') or not numeric(summary.get('total')):
            continue
        runs[metadata['label'], metadata['card']] = (path, metadata)

    rows = []
    for (label, card), (path, metadata) in runs.items():
        summary = metadata['summary']
        is_complete = complete(metadata)
        original = runs.get(('original-pro-py312', card), (None, {}))[1]
        attached = runs.get(('attached-9c656-py312', card), (None, {}))[1]
        comparable = is_complete and complete(original) and complete(attached)
        # Missing/incomplete references never establish a gain or acceptance pass.
        original_total = original.get('summary', {}).get('total')
        target = 1.3 * original_total if complete(original) and numeric(original_total) and original_total > 0 else None
        clock = summary.get('fair_clock', {})
        rows.append(dict(
            label=label, card=card, status=metadata['status'],
            termination_reason=summary.get('termination_reason'), complete=is_complete,
            comparison_status='comparable' if comparable else 'not comparable',
            total=summary['total'], science=summary.get('sum_best_scores'),
            science_gain_vs_original_percent=gain(summary.get('sum_best_scores'), original, 'sum_best_scores') if comparable else None,
            science_gain_vs_attached_percent=gain(summary.get('sum_best_scores'), attached, 'sum_best_scores') if comparable else None,
            required_missing=summary.get('required_missing'), required_penalty=summary.get('required_penalty'),
            request_reward=summary.get('observation_request_reward'), report_settlement=summary.get('report_settlement'),
            uniformity=summary.get('uniformity_penalty'), charged_cpu=clock.get('charged_seconds'),
            process_cpu=clock.get('cpu_seconds'), wall_seconds=clock.get('run_wall_seconds'),
            gain_vs_original_percent=gain(summary['total'], original, 'total') if comparable else None,
            gain_vs_attached_percent=gain(summary['total'], attached, 'total') if comparable else None,
            target_30_percent=target,
            passes_30_percent=bool(comparable and target is not None and summary['total'] >= target),
            source_unchanged=metadata.get('source_unchanged'), card_unchanged=metadata.get('card_files_unchanged'),
            adaptive=metadata.get('adaptive'), settings=metadata.get('settings', {}),
            benchmark=str(path.relative_to(ROOT_OUTPUTS)),
        ))
    return sorted(rows, key=lambda row: (row['card'], row['label']))


def formatted(value):
    return f'{value:.3f}' if numeric(value) else 'unavailable'


def write_results(rows):
    (NEW / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    fields = [key for key in rows[0] if key != 'settings'] if rows else ['label', 'card', 'status']
    with (NEW / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        '# Matched local evaluation checkpoint', '',
        'Native arm64 Python 3.12.14, unchanged local engine, no external model, 900 normalized CPU seconds per episode. Original and attached fixed-tier references are explicit; adaptive controls are separately identified. Full source/config hashes, all components and raw artifacts are linked through results.json. Local results do not establish hidden platform performance.', '',
        '| Card | Configuration | Completion | Total | Science | vs original | Charged CPU | 30% met |',
        '|---|---|---|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        percentage = row['gain_vs_original_percent']
        comparison = f'{percentage:+.3f}%' if percentage is not None else 'not comparable'
        completion = 'complete' if row['complete'] else 'FAILED/INCOMPLETE'
        passed = 'yes' if row['passes_30_percent'] else ('no' if row['comparison_status'] == 'comparable' else 'not comparable')
        lines.append(f"| {row['card']} | {row['label']} | {completion} | {formatted(row['total'])} | {formatted(row['science'])} | {comparison} | {formatted(row['charged_cpu'])} | {passed} |")
    lines.extend([
        '', 'CPU is normalized charge, not process CPU or wall time. Complete component tables are in results.csv. Failed/incomplete rows retain their partial settlement for audit and are not full-survey performance comparisons. Missing or incomplete native original/attachment references produce null comparisons and no acceptance pass. A nonpositive original total has no percentage-improvement threshold; it cannot produce a 30% acceptance pass. A passed test suite or a higher proxy utility is not a demonstrated score gain.', '',
        'The supplied negative v4-public-test report uses a different card, 300 CPU budget and model-enabled policy; it is excluded from this comparison. Its exact card/source linkage is unresolved.',
    ])
    (NEW / 'RESULTS.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    settled = collect()
    write_results(settled)
    print(f'Recorded {len(settled)} settled run records (completion tracked separately)')
