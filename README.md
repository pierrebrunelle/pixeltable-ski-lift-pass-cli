<!-- pixeltable-example-app: 20261105-ski-lift-pass-cli -->
# Ski-Lift Pass Gates CLI built with Pixeltable

![Ski-Lift Pass Gates CLI built with Pixeltable](.github/social-preview.png)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/pierrebrunelle/pixeltable-ski-lift-pass-cli?quickstart=1)
[![Built with Pixeltable](https://img.shields.io/badge/built%20with-Pixeltable-5b4bff)](https://pixeltable.com)
[![PyPI - pixeltable](https://img.shields.io/pypi/v/pixeltable?label=pixeltable)](https://pypi.org/project/pixeltable/)
[![GitHub stars](https://img.shields.io/github/stars/pixeltable/pixeltable?style=social)](https://github.com/pixeltable/pixeltable)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

`Passes` holds one lift pass per row (product, validity dates, a typed `pxt.Json[list[str]]` list of included zones, a `blocked` flag). `Scans` is the turnstile log: `cli.py` copies the pass fields onto each scan as it records it, and computed columns in `udfs.py` derive the lift's zone, the gate verdict (`{'ok': ..., 'reason': ...}`: unknown pass, blocked, not yet valid, expired, outside hours, zone not included) and the short code shown on the gate display. `PassZones` is a view that splits every pass into one row per included zone with `pixeltable.functions.json.list_iterator`, so "who can ride the glacier lift" is a plain query. Every command runs with Pixeltable's OpenTelemetry instrumentation on and appends its spans to `logs/spans.jsonl`; `cli.py trace` prints the newest trace as a tree, and against a cloud database it reads the database pod's sampled spans with `pxt db spans --json`. `cli.py upgrade-check` records the Pixeltable version, row counts, table versions and `pxt schema diff` before an upgrade and compares after it. `cli.py feedback` previews a gap report for the Pixeltable team with `pxt feedback` and never sends it.

[Pixeltable](https://pixeltable.com) is open-source, Python-native **multimodal AI data infrastructure**: tables, incremental computed columns, UDFs, indexes and serving in one library, running locally or on Pixeltable Cloud.

> ⭐ **Like this example?** Star [pixeltable/pixeltable](https://github.com/pixeltable/pixeltable) on GitHub. It helps other developers find it.

## What this example shows

- **Incremental computed columns** powered by plain Python UDFs (`@pxt.udf`)
- **Pixeltable Cloud lifecycle** from the `pxt` CLI (`db`, `schema`, `service`)
- **B-tree indexes** declared on the model (`__indexes__`) back the lookup queries
- **`pxt` CLI** for inspecting and operating the catalog
- **Iterators**: one input row fans out into many (frames, chunks, sentences) via a view
- **Importable UDF module**: UDFs live in `udfs.py`; tables and queries live in `app.py` (Pixeltable resolves UDFs by module path)
- **`pixeltable.toml`** declares a local database and a **Pixeltable Cloud** database, so the same code deploys with `pxt db update`

## Tracing

`cli.py` turns on Pixeltable's OpenTelemetry instrumentation for local targets:

```python
from opentelemetry.instrumentation.pixeltable import init
init(span_dump='logs/spans.jsonl', service_name='liftpass-cli')
```

A scan then leaves a trace like this (`python cli.py trace --root pixeltable.insert`):

```
pixeltable.insert  15.0 ms  {"pxt.num_rows": 1, "pxt.num_excs": 0, ...}
  pixeltable.data_source.prepare  0.1 ms
  pixeltable.catalog.begin_xact  1.4 ms  {"pxt.for_write": true, ...}
  pixeltable.store.insert_rows  3.0 ms
    pixeltable.sa.insert_rows  1.5 ms  {"pxt.rows": 1}
  pixeltable.catalog.write_tbl_md  5.1 ms  {"pxt.version": 3}
```

A failed insert (duplicate primary key, bad timestamp) is recorded with `status: ERROR` and an `exception` event. On a cloud target the client records nothing; read the database pod's sampled spans with `pxt db spans pxt://<org>:<db>` (or `cli.py --target ... trace`), where the same spans sit under `POST /rpc` -> `pixeltable.rpc`.

## Gate rules

| Product | Zones | Hours |
|---|---|---|
| day | base, summit | 08-17 |
| half-day | base, summit | 12-17 |
| season | base, summit, glacier | 08-17 |
| beginner | base | 08-17 |

The verdict is a computed column over the scan row, so changing a rule in `udfs.py` and running `pxt recompute` re-evaluates the whole log.

## Notes

- Timestamps without a time zone are read in the configured time zone of the process that stores them: your machine's zone locally, UTC in a Pixeltable Cloud database. Pass aware datetimes (`2026-02-14T10:15-07:00`) if both targets should agree.
- `pxt feedback --kind gap '...'` prints exactly what it would send; `cli.py feedback` never adds `--send`.

## What's inside

| File | What it is |
|------|------------|
| `.devcontainer/devcontainer.json` | GitHub Codespaces / Dev Container config: Python 3.12, installs `requirements.txt` |
| `.github/social-preview.png` | Social preview image (1280x640) |
| `CITATION.cff` | Citation metadata (authors, license, release date, keywords) |
| `app.py` | Tables declared as Python classes and `@pxt.query` functions |
| `cli.py` | liftpass: a command-line tool for ski-lift pass gates, backed by Pixeltable |
| `pixeltable.toml` | Project config: the local database plus a Pixeltable Cloud database (sizing, deploy excludes) |
| `udfs.py` | Pixeltable UDFs (`@pxt.udf`) in their own importable module, imported by `app.py` |
| `requirements.txt` / `pyproject.toml` | Dependencies (`pixeltable>=0.7.23`) |

**Tables**

| Table | Stored columns | Computed columns |
|-------|---------|------------------|
| `passes` | `pass_id`, `holder`, `product`, `valid_from`, `valid_to`, `zones`, `blocked` | - |
| `scans` | `scan_id`, `pass_id`, `lift_id`, `scanned_at`, `product`, `valid_from`, `valid_to`, `pass_zones`, `blocked` | `zone`, `verdict`, `code` |
| `pass_zones` | - | - |

## Run in your browser (GitHub Codespaces)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/pierrebrunelle/pixeltable-ski-lift-pass-cli?quickstart=1)

1. Click **Open in GitHub Codespaces** above (or [this link](https://codespaces.new/pierrebrunelle/pixeltable-ski-lift-pass-cli?quickstart=1)). The dev container installs Python 3.12 and `pixeltable>=0.7.23` from `requirements.txt`.
2. In the codespace terminal, create the tables, seed them and run the app:

   ```bash
   pxt schema update app.py lifts
   python cli.py seed                       # 8 passes + 48 gate scans on one ski day
   python cli.py denied                     # refused scans and why (expired, outside_hours, zone_not_included, ...)
   python cli.py scan P-1001 glacier --at 2026-02-14T10:15   # one turnstile scan -> OPEN / DENIED + gate code
   python cli.py block P-1006 && python cli.py scan P-1006 eagle --at 2026-02-14T11:00   # a blocked pass is refused
   python cli.py zone glacier               # holders whose pass includes a zone (PassZones view)
   python cli.py trace --root pixeltable.insert   # the newest insert's span tree from logs/spans.jsonl
   python cli.py upgrade-check              # record versions + row counts; run again after pip install -U
   python cli.py --target pxt://<your-org>:<your-db> seed   # the same commands against Pixeltable Cloud
   ```


## Quickstart

Requires Python 3.11+ and `pixeltable>=0.7.23`.

```bash
git clone https://github.com/pierrebrunelle/pixeltable-ski-lift-pass-cli.git
cd pixeltable-ski-lift-pass-cli
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Create the tables in a local catalog directory named `lifts`
pxt schema update app.py lifts

python cli.py seed                       # 8 passes + 48 gate scans on one ski day
python cli.py denied                     # refused scans and why (expired, outside_hours, zone_not_included, ...)
python cli.py scan P-1001 glacier --at 2026-02-14T10:15   # one turnstile scan -> OPEN / DENIED + gate code
python cli.py block P-1006 && python cli.py scan P-1006 eagle --at 2026-02-14T11:00   # a blocked pass is refused
python cli.py zone glacier               # holders whose pass includes a zone (PassZones view)
python cli.py trace --root pixeltable.insert   # the newest insert's span tree from logs/spans.jsonl
python cli.py upgrade-check              # record versions + row counts; run again after pip install -U
python cli.py --target pxt://<your-org>:<your-db> seed   # the same commands against Pixeltable Cloud
```

## Deploy to Pixeltable Cloud

The same `app.py` runs on [Pixeltable Cloud](https://pixeltable.com). Sign in (or get a free trial database with `pxt new`), point the second database entry in `pixeltable.toml` at your own database, then deploy:

```bash
pxt login                       # or: export PIXELTABLE_API_KEY=<your-api-key>
# edit pixeltable.toml: name = 'pxt://<your-org>:<your-db>'
pxt db update pxt://<your-org>:<your-db>                 # build the image and upload the project
pxt schema update app.py pxt://<your-org>:<your-db>       # create the tables at the database root (no per-app folder)
```

Keep keys in environment variables or `pxt secret set`, never in code.

## Code walkthrough

**1. Business logic is plain Python, in `udfs.py`.** A `@pxt.udf` function can be used as a column expression. Pixeltable records UDFs by module path (`udfs.lift_zone`), so they live in their own importable module rather than inline in the app: the daemon, serving workers and Pixeltable Cloud import it again by that path.

```python
# udfs.py
@pxt.udf
def lift_zone(lift_id: str) -> str:
    """The zone a lift serves ('unknown' for a lift we don't know)."""
    return LIFT_ZONES.get(lift_id, 'unknown')
```

**2. Tables are Python classes (`app.py`).** Annotated attributes are stored columns; attributes assigned an expression are **computed columns** (`zone`, `verdict`, `code`), evaluated incrementally on every insert or update and recomputed when their inputs change. Indexes live next to the columns.

```python
# app.py
class Scans(TableModel, name='scans'):
    """One turnstile scan, with the pass fields as they were at scan time."""

    scan_id = pxt.Column(type=pxt.String, primary_key=True)
    pass_id: pxt.String
    lift_id: pxt.String
    scanned_at: pxt.Timestamp
    product: pxt.String | None
    valid_from: pxt.Date | None
    valid_to: pxt.Date | None
    pass_zones: pxt.Json | None
    blocked: pxt.Bool | None

    zone = lift_zone(lift_id)
    verdict = gate_verdict(scanned_at, zone, product, valid_from, valid_to, pass_zones, blocked)
    code = gate_code(scan_id, lift_id)

    __indexes__ = [pxt.BtreeIndex(pass_id), pxt.BtreeIndex(lift_id)]
```

## Learn more

- 🌐 Website: https://pixeltable.com
- 📚 Docs: https://docs.pixeltable.com
- 💻 Source: https://github.com/pixeltable/pixeltable (⭐ star it if Pixeltable is useful to you)
- 📦 PyPI: https://pypi.org/project/pixeltable/
- 🧩 More example apps: https://pierrebrunelle.github.io/awesome-pixeltable-apps/

**[More Pixeltable example apps →](https://pierrebrunelle.github.io/awesome-pixeltable-apps/)**

---

<sub>Built as part of a daily series of Pixeltable example apps · Pixeltable 0.7.23 · Python, incremental computed columns · Licensed under Apache-2.0.</sub>
