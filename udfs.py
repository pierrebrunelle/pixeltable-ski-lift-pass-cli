"""UDFs for the ski-lift pass gate CLI. Pure Python, no table imports."""

from __future__ import annotations

import datetime as dt
import hashlib

import pixeltable as pxt

# Lift -> zone of the mountain it serves.
LIFT_ZONES = {
    'gondola': 'base',
    'eagle': 'base',
    'summit-express': 'summit',
    'ridge-t-bar': 'summit',
    'glacier': 'glacier',
    'kids-carpet': 'base',
}

# Products: the zones they include and the hours of the day they are valid.
PRODUCTS = {
    'day': {'zones': ['base', 'summit'], 'start_hour': 8, 'end_hour': 17},
    'half-day': {'zones': ['base', 'summit'], 'start_hour': 12, 'end_hour': 17},
    'season': {'zones': ['base', 'summit', 'glacier'], 'start_hour': 8, 'end_hour': 17},
    'beginner': {'zones': ['base'], 'start_hour': 8, 'end_hour': 17},
}


@pxt.udf
def lift_zone(lift_id: str) -> str:
    """The zone a lift serves ('unknown' for a lift we don't know)."""
    return LIFT_ZONES.get(lift_id, 'unknown')


@pxt.udf
def gate_verdict(
    scanned_at: dt.datetime,
    zone: str,
    product: str | None,
    valid_from: dt.date | None,
    valid_to: dt.date | None,
    zones: list | None,
    blocked: bool | None,
) -> dict:
    """Decide whether a gate scan opens the turnstile, and why not.

    The pass fields are copied onto the scan when it is recorded, so the verdict is a pure function of the row.
    """
    if product is None:
        return {'ok': False, 'reason': 'unknown_pass'}
    if blocked:
        return {'ok': False, 'reason': 'blocked'}
    day = scanned_at.date()
    if valid_from is not None and day < valid_from:
        return {'ok': False, 'reason': 'not_yet_valid'}
    if valid_to is not None and day > valid_to:
        return {'ok': False, 'reason': 'expired'}
    rule = PRODUCTS.get(product)
    if rule is None:
        return {'ok': False, 'reason': 'unknown_product'}
    if not rule['start_hour'] <= scanned_at.hour < rule['end_hour']:
        return {'ok': False, 'reason': 'outside_hours'}
    if zone not in (zones or rule['zones']):
        return {'ok': False, 'reason': 'zone_not_included'}
    return {'ok': True, 'reason': 'ok'}


@pxt.udf
def gate_code(scan_id: str, lift_id: str) -> str:
    """Short code printed on the gate display, stable per scan."""
    return f'{lift_id[:3].upper()}-{hashlib.sha1(scan_id.encode()).hexdigest()[:6]}'
