"""liftpass: a command-line tool for ski-lift pass gates, backed by Pixeltable.

    pxt schema update app.py lifts
    python cli.py seed                       # 8 passes + a morning of gate scans
    python cli.py scan P-1004 glacier --at 2026-02-14T10:15
    python cli.py denied                     # refused scans and why
    python cli.py pass P-1004                # one pass's scans
    python cli.py load                       # accepted scans per lift
    python cli.py zone glacier               # holders whose pass includes a zone (PassZones view)
    python cli.py block P-1006               # block a lost pass; later scans are refused
    python cli.py trace                      # the newest trace from logs/spans.jsonl, as a tree
    python cli.py trace --root pixeltable.insert     # the newest insert's trace
    python cli.py trace --target pxt://<org>:<db>   # sampled spans of a hosted database (pxt db spans)
    python cli.py feedback 'what was missing'       # preview a gap report for the Pixeltable team (never sends)
    python cli.py upgrade-check              # record / compare versions, row counts and schema drift

Every command takes --target: a local catalog dir (default 'lifts') or a Pixeltable Cloud URI pxt://<org>:<db>.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
SPANS = ROOT / 'logs' / 'spans.jsonl'
BASELINE = ROOT / 'logs' / 'upgrade-baseline.json'
SEASON = dt.date(2026, 2, 14)


def is_hosted(target: str) -> bool:
    return target.split(':', 1)[0] == 'pxt'


def start(target: str, trace: bool = True):
    """Turn on span recording (local targets), then bind the models to the target catalog."""
    if trace and not is_hosted(target):
        from opentelemetry.instrumentation.pixeltable import init

        SPANS.parent.mkdir(exist_ok=True)
        # passed here rather than as [otel] span_dump in pixeltable.toml: the [otel] section also applies to the
        # hosted database, whose pod then fails to start when the dump file's directory isn't in the project
        init(span_dump=str(SPANS), service_name='liftpass-cli')
    import app

    app.TableModel.bind_all(target)
    return app


def show(rows) -> None:
    rows = list(rows)
    if not rows:
        print('(none)')
        return
    cols = list(rows[0].keys())
    width = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print('  '.join(c.ljust(width[c]) for c in cols))
    for r in rows:
        print('  '.join(str(r[c]).ljust(width[c]) for c in cols))


def scan_row(app, scan_id: str, pass_id: str, lift_id: str, at: dt.datetime) -> dict:
    """A scan row with the pass fields as they are right now (None for an unknown pass)."""
    p = app.Passes.table
    found = list(
        p.where(p.pass_id == pass_id).select(p.product, p.valid_from, p.valid_to, p.zones, p.blocked).collect()
    )
    info = found[0] if found else {}
    return {
        'scan_id': scan_id,
        'pass_id': pass_id,
        'lift_id': lift_id,
        'scanned_at': at,
        'product': info.get('product'),
        'valid_from': info.get('valid_from'),
        'valid_to': info.get('valid_to'),
        'pass_zones': info.get('zones'),
        'blocked': info.get('blocked'),
    }


PASSES = [
    ('P-1001', 'Ines Navarro', 'season', SEASON - dt.timedelta(days=60), SEASON + dt.timedelta(days=60), ['base', 'summit', 'glacier']),
    ('P-1002', 'Tom Becker', 'day', SEASON, SEASON, ['base', 'summit']),
    ('P-1003', 'Aiko Mori', 'half-day', SEASON, SEASON, ['base', 'summit']),
    ('P-1004', 'Luca Rossi', 'day', SEASON, SEASON, ['base', 'summit']),
    ('P-1005', 'Emma Larsen', 'beginner', SEASON, SEASON, ['base']),
    ('P-1006', 'Noah Fischer', 'season', SEASON - dt.timedelta(days=60), SEASON + dt.timedelta(days=60), ['base', 'summit', 'glacier']),
    ('P-1007', 'Sara Okafor', 'day', SEASON - dt.timedelta(days=1), SEASON - dt.timedelta(days=1), ['base', 'summit']),
    ('P-1008', 'Jonas Weber', 'season', SEASON + dt.timedelta(days=1), SEASON + dt.timedelta(days=90), ['base', 'summit', 'glacier']),
]
LIFTS = ['gondola', 'eagle', 'summit-express', 'ridge-t-bar', 'glacier', 'kids-carpet']


def cmd_seed(args) -> None:
    app = start(args.target)
    p, s = app.Passes.table, app.Scans.table
    p.insert(
        [
            {'pass_id': i, 'holder': h, 'product': pr, 'valid_from': a, 'valid_to': b, 'zones': z, 'blocked': False}
            for i, h, pr, a, b, z in PASSES
        ],
        on_error='abort',
    )
    rng = random.Random(20260214)
    rows = []
    for n in range(48):
        pid = rng.choice([x[0] for x in PASSES] + ['P-9999'])
        at = dt.datetime.combine(SEASON, dt.time(8)) + dt.timedelta(minutes=rng.randrange(0, 9 * 60))
        rows.append(scan_row(app, f'S-{n:04d}', pid, rng.choice(LIFTS), at))
    status = s.insert(rows, on_error='abort')
    print(f'seeded {p.count()} passes, {status.num_rows} scans ({status.num_excs} errors)')
    print(f'PassZones view: {app.PassZones.table.count()} rows')


def cmd_scan(args) -> None:
    app = start(args.target)
    s = app.Scans.table
    at = dt.datetime.fromisoformat(args.at) if args.at else dt.datetime.now()
    sid = f'S-{at:%Y%m%d%H%M%S}-{args.pass_id}'
    s.insert([scan_row(app, sid, args.pass_id, args.lift_id, at)], on_error='abort')
    r = list(s.where(s.scan_id == sid).select(s.zone, s.verdict, s.code).collect())[0]
    print(f"{'OPEN' if r['verdict']['ok'] else 'DENIED'}  {args.pass_id} @ {args.lift_id} ({r['zone']})  "
          f"reason={r['verdict']['reason']}  code={r['code']}")


def cmd_pass(args) -> None:
    show(start(args.target).pass_scans(args.pass_id).collect())


def cmd_denied(args) -> None:
    show(start(args.target).denied_scans().collect())


def cmd_load(args) -> None:
    show(start(args.target).lift_load().collect())


def cmd_zone(args) -> None:
    show(start(args.target).zone_holders(args.zone).collect())


def cmd_block(args) -> None:
    app = start(args.target)
    p = app.Passes.table
    status = p.where(p.pass_id == args.pass_id).update({'blocked': True})
    print(f'blocked {args.pass_id}: {status.num_rows} row(s) updated')


def _span_fields(sp: dict) -> tuple:
    """(trace_id, span_id, parent_id, name, start, end_or_duration, attrs) from either span format."""
    ctx = sp.get('context') or {}
    trace_id = sp.get('trace_id') or ctx.get('trace_id')
    span_id = sp.get('span_id') or ctx.get('span_id')
    parent = sp.get('parent_id') or sp.get('parent_span_id')
    if isinstance(parent, dict):
        parent = parent.get('span_id')
    start_ = sp.get('start_time') or sp.get('start') or sp.get('timestamp')
    if start_ is None and sp.get('start_ms') is not None:  # pxt db spans --json
        start_ = dt.datetime.fromtimestamp(sp['start_ms'] / 1000, dt.timezone.utc).isoformat()
    dur = sp.get('duration_ms')
    if dur is None and sp.get('end_time') and start_:
        try:
            a = dt.datetime.fromisoformat(str(start_).replace('Z', '+00:00'))
            b = dt.datetime.fromisoformat(str(sp['end_time']).replace('Z', '+00:00'))
            dur = (b - a).total_seconds() * 1000
        except ValueError:
            dur = None
    return trace_id, span_id, parent, sp.get('name'), start_, dur, sp.get('attributes') or {}


def print_tree(spans: list[dict], trace_id: str | None, root: str | None = None) -> None:
    rows = [_span_fields(sp) for sp in spans]
    if root:
        keep = {r[0] for r in rows if r[3] == root}
        rows = [r for r in rows if r[0] in keep]
    if not rows:
        print('(no spans)')
        return
    if trace_id is None:
        trace_id = max(rows, key=lambda r: str(r[4]))[0]
    rows = [r for r in rows if r[0] == trace_id]
    ids = {r[1] for r in rows}
    kids = defaultdict(list)
    for r in rows:
        kids[r[2] if r[2] in ids else None].append(r)

    def walk(parent, depth):
        for r in sorted(kids[parent], key=lambda r: str(r[4])):
            attrs = {k: v for k, v in r[6].items() if k.startswith(('pxt.', 'pixeltable.', 'db.', 'http.')) or k in ('rows', 'tables')}
            dur = f'{r[5]:.1f} ms' if isinstance(r[5], (int, float)) else ''
            print(f"{'  ' * depth}{r[3]}  {dur}  {json.dumps(attrs)[:140] if attrs else ''}")
            walk(r[1], depth + 1)

    print(f'trace {trace_id}: {len(rows)} spans')
    walk(None, 1)


def cmd_trace(args) -> None:
    if is_hosted(args.target):
        cmd = ['pxt', 'db', 'spans', args.target, '--since', args.since, '--tail', str(args.tail), '--json']
        if args.trace_id:
            cmd += ['--trace', args.trace_id]
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode != 0:
            print(out.stderr.strip() or out.stdout.strip(), file=sys.stderr)
            sys.exit(out.returncode)
        data = json.loads(out.stdout)
        spans = data.get('spans', data) if isinstance(data, dict) else data
        print(f'{len(spans)} sampled spans in the last {args.since}')
        print_tree(spans, args.trace_id, args.root)
        return
    if not SPANS.exists():
        print('no logs/spans.jsonl yet: run a command first')
        return
    spans = [json.loads(line) for line in SPANS.read_text().splitlines() if line.strip()]
    print_tree(spans, args.trace_id, args.root)


def cmd_feedback(args) -> None:
    """Preview a gap report for the Pixeltable team. Sending is left to you: rerun `pxt feedback ... --send`."""
    out = subprocess.run(['pxt', 'feedback', '--kind', args.kind, args.text, '--json'], capture_output=True, text=True)
    print(out.stdout.strip() or out.stderr.strip())
    sys.exit(out.returncode)


def cmd_upgrade_check(args) -> None:
    """Record pxt version, table versions, row counts and schema drift; compare with the last recorded run."""
    import pixeltable as pxt

    app = start(args.target, trace=False)
    now = {
        'pxt_version': pxt.__version__,
        'tables': {
            md['name']: {'rows': m.table.count(), 'version': md['version'], 'schema_version': md['schema_version']}
            for m in app.MODELS
            for md in [m.table.get_metadata()]
        },
    }
    diff = subprocess.run(['pxt', 'schema', 'diff', 'app.py', args.target], cwd=ROOT, capture_output=True, text=True)
    now['schema_diff_exit'] = diff.returncode
    now['schema_diff'] = diff.stdout.strip().splitlines()[-1:] if diff.stdout.strip() else []
    print(json.dumps(now, indent=1, default=str))
    key = args.target
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    if key in base and not args.record:
        old = base[key]
        same = old['tables'] == now['tables']
        print(f"vs baseline (pxt {old['pxt_version']}): tables {'unchanged' if same else 'CHANGED'}, "
              f"schema diff exit {now['schema_diff_exit']}")
        sys.exit(0 if same and now['schema_diff_exit'] == 0 else 1)
    base[key] = now
    BASELINE.parent.mkdir(exist_ok=True)
    BASELINE.write_text(json.dumps(base, indent=1, default=str))
    print(f'baseline recorded for {key}')


def main() -> None:
    ap = argparse.ArgumentParser(prog='liftpass', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--target', default='lifts', help="catalog dir or pxt://<org>:<db> (default 'lifts')")
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('seed').set_defaults(fn=cmd_seed)
    p = sub.add_parser('scan')
    p.add_argument('pass_id')
    p.add_argument('lift_id')
    p.add_argument('--at', help='scan time, ISO format (default: now)')
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser('pass')
    p.add_argument('pass_id')
    p.set_defaults(fn=cmd_pass)
    sub.add_parser('denied').set_defaults(fn=cmd_denied)
    sub.add_parser('load').set_defaults(fn=cmd_load)
    p = sub.add_parser('zone')
    p.add_argument('zone')
    p.set_defaults(fn=cmd_zone)
    p = sub.add_parser('block')
    p.add_argument('pass_id')
    p.set_defaults(fn=cmd_block)
    p = sub.add_parser('trace')
    p.add_argument('--trace-id')
    p.add_argument('--root', help="newest trace containing a span with this name, e.g. 'pixeltable.insert'")
    p.add_argument('--since', default='1h')
    p.add_argument('--tail', type=int, default=200)
    p.set_defaults(fn=cmd_trace)
    p = sub.add_parser('feedback')
    p.add_argument('text')
    p.add_argument('--kind', default='gap', choices=['bug', 'gap', 'docs'])
    p.set_defaults(fn=cmd_feedback)
    p = sub.add_parser('upgrade-check')
    p.add_argument('--record', action='store_true', help='overwrite the baseline')
    p.set_defaults(fn=cmd_upgrade_check)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
