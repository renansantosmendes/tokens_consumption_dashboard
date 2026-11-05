"""Reads the billing charges of Vercel from the FOCUS JSON lines (pure)."""

import json
from typing import Any

DEFAULT_CURRENCY = "USD"
UNKNOWN_SERVICE = "Outros"


def _number(value: Any) -> float:
    """Read a money amount that may come as a number or as text.

    Parameters
    ----------
    value : Any
        Amount of a charge.

    Returns
    -------
    float
        The amount, or 0.0 when it is missing or not numeric.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_charges(text: str) -> list[dict[str, Any]]:
    """Read the charges written one per line as JSON.

    Parameters
    ----------
    text : str
        Raw answer of the billing endpoint; lines that are not JSON objects
        are skipped.

    Returns
    -------
    list[dict[str, Any]]
        Charges with the date (YYYY-MM-DD), service, cost, currency, consumed
        quantity and unit.

    Example
    -------
    >>> line = '{"ChargePeriodStart": "2026-11-02T00:00:00Z", '
    >>> line += '"ServiceName": "Edge Requests", "BilledCost": 0.5}'
    >>> parse_charges(line)[0]["cost"]
    0.5
    """
    charges: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        cost = row.get("BilledCost", row.get("EffectiveCost"))
        charges.append(
            {
                "date": str(row.get("ChargePeriodStart") or "")[:10],
                "service": str(row.get("ServiceName") or UNKNOWN_SERVICE),
                "cost": _number(cost),
                "currency": str(row.get("BillingCurrency") or DEFAULT_CURRENCY),
                "quantity": _number(row.get("ConsumedQuantity")),
                "unit": str(row.get("ConsumedUnit") or ""),
            }
        )
    return charges
