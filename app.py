"""Ski-lift pass gates as Pixeltable tables: passes, gate scans and a per-zone view.

`Passes` holds one lift pass per row (product, validity dates, included zones). `Scans` is the turnstile log:
the CLI copies the pass fields onto each scan as it records it, and computed columns derive the lift's zone,
the gate verdict (open, or why not) and the code shown on the gate display. `PassZones` is a view that splits
every pass into one row per included zone with `list_iterator`.

Layout: UDFs live in udfs.py; this file holds the table models and the query helpers. cli.py drives it.

    pxt schema update app.py lifts
    python cli.py seed
    python cli.py denied
"""

from __future__ import annotations

import pixeltable as pxt
import pixeltable.functions as pxtf

from udfs import gate_code, gate_verdict, lift_zone

TableModel = pxt.model_base()


class Passes(TableModel, name='passes'):
    """One lift pass."""

    pass_id = pxt.Column(type=pxt.String, primary_key=True)
    holder: pxt.String
    product: pxt.String
    valid_from: pxt.Date
    valid_to: pxt.Date
    zones: pxt.Json[list[str]]
    blocked: pxt.Bool

    __indexes__ = [pxt.BtreeIndex(holder)]


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


class PassZones(TableModel, name='pass_zones', base=Passes, iterator=pxtf.json.list_iterator(zone=Passes.zones)):
    """One row per (pass, included zone)."""


MODELS = (Passes, Scans, PassZones)


# Query helpers: plain functions over the bound tables.
def pass_scans(pass_id: str) -> pxt.Query:
    """Every scan of one pass, oldest first."""
    s = Scans.table
    return s.where(s.pass_id == pass_id).order_by(s.scanned_at).select(s.scanned_at, s.lift_id, s.zone, s.verdict, s.code)


def denied_scans() -> pxt.Query:
    """Scans the gate refused, newest first."""
    s = Scans.table
    return (
        s.where(s.verdict.ok == False)  # noqa: E712
        .order_by(s.scanned_at, asc=False)
        .select(s.scanned_at, s.pass_id, s.lift_id, s.verdict.reason, s.code)
    )


def lift_load() -> pxt.Query:
    """Accepted scans per lift."""
    s = Scans.table
    return (
        s.where(s.verdict.ok == True)  # noqa: E712
        .group_by(s.lift_id)
        .select(s.lift_id, n=pxtf.count(s.scan_id))
        .order_by(s.lift_id)
    )


def zone_holders(zone: str) -> pxt.Query:
    """Holders whose pass includes a zone (from the PassZones view)."""
    z = PassZones.table
    return z.where(z.zone == zone).order_by(z.pass_id).select(z.pass_id, z.holder, z.product)
