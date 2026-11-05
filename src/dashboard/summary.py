"""Turns the rows of the Langfuse metrics into the data of the dashboard (pure)."""

from datetime import date, datetime
from typing import Any

from dashboard.queries import TOP_USERS

TOP_OPERATIONS = 15
UNKNOWN_MODEL = "modelo não identificado"
UNNAMED_OPERATION = "sem nome"


def _number(value: Any) -> float:
    """Read a number from a metrics cell, treating missing values as zero.

    Parameters
    ----------
    value : Any
        Cell of the metrics answer.

    Returns
    -------
    float
        The number, or 0.0 when the cell is empty or not numeric.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _optional(value: Any) -> float | None:
    """Read a number from a metrics cell, keeping missing values as None.

    Parameters
    ----------
    value : Any
        Cell of the metrics answer.

    Returns
    -------
    float | None
        The number, or None when the cell is empty or not numeric.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _brl(usd: float, usd_brl: float) -> float:
    """Convert US dollars to reais, rounded to centavos.

    Parameters
    ----------
    usd : float
        Amount in US dollars.
    usd_brl : float
        Exchange rate, reais per dollar.

    Returns
    -------
    float
        Amount in reais.
    """
    return round(usd * usd_brl, 2)


def _daily_series(
    rows: list[dict[str, Any]],
    usd_brl: float,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Daily cost, tokens and calls, with the days without data filled with zero.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Rows of the daily query.
    usd_brl : float
        Exchange rate, reais per dollar.
    start : date
        First day of the window.
    end : date
        Last day of the window.

    Returns
    -------
    list[dict[str, Any]]
        One entry per day, oldest first.
    """
    by_day = {}
    for row in rows:
        day = str(row.get("time_dimension", ""))[:10]
        by_day[day] = row
    series = []
    current = start
    while current <= end:
        key = current.isoformat()
        row = by_day.get(key, {})
        series.append({
            "date": key,
            "cost_brl": _brl(_number(row.get("sum_totalCost")), usd_brl),
            "tokens": int(_number(row.get("sum_totalTokens"))),
            "calls": int(_number(row.get("count_count"))),
        })
        current = date.fromordinal(current.toordinal() + 1)
    return series


def build_dashboard(
    *,
    totals: dict[str, Any],
    models: list[dict[str, Any]],
    daily: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    users: list[dict[str, Any]],
    usd_brl: float,
    rate_date: str | None,
    start: date,
    end: date,
    generated_at: datetime,
) -> dict[str, Any]:
    """Build the dashboard data from the query answers.

    Parameters
    ----------
    totals : dict[str, Any]
        Row of the totals query.
    models : list[dict[str, Any]]
        Rows of the query by model.
    daily : list[dict[str, Any]]
        Rows of the daily query.
    operations : list[dict[str, Any]]
        Rows of the latency query by operation.
    users : list[dict[str, Any]]
        Rows of the query by user.
    usd_brl : float
        Exchange rate, reais per dollar.
    rate_date : str | None
        Date of the exchange rate, shown in the dashboard.
    start : date
        First day of the window.
    end : date
        Last day of the window.
    generated_at : datetime
        Moment the data was generated, timezone aware.

    Returns
    -------
    dict[str, Any]
        Data of the dashboard: totals, daily series, models, operations and users.
    """
    cost_usd = _number(totals.get("sum_totalCost"))
    model_rows = sorted(
        (
            {
                "model": str(row.get("providedModelName") or UNKNOWN_MODEL),
                "cost_brl": _brl(_number(row.get("sum_totalCost")), usd_brl),
                "tokens": int(_number(row.get("sum_totalTokens"))),
                "calls": int(_number(row.get("count_count"))),
            }
            for row in models
        ),
        key=lambda item: item["cost_brl"],
        reverse=True,
    )
    operation_rows = sorted(
        (
            {
                "name": str(row.get("name") or UNNAMED_OPERATION),
                "calls": int(_number(row.get("count_count"))),
                "p50_ms": _optional(row.get("p50_latency")),
                "p95_ms": _optional(row.get("p95_latency")),
            }
            for row in operations
        ),
        key=lambda item: item["calls"],
        reverse=True,
    )[:TOP_OPERATIONS]
    user_rows = [
        {
            "user_id": str(row["userId"]),
            "cost_brl": _brl(_number(row.get("sum_totalCost")), usd_brl),
            "tokens": int(_number(row.get("sum_totalTokens"))),
        }
        for row in users
        if row.get("userId")
    ][:TOP_USERS]
    return {
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "exchange": {"usd_brl": usd_brl, "rate_date": rate_date},
        "totals": {
            "cost_usd": round(cost_usd, 6),
            "cost_brl": _brl(cost_usd, usd_brl),
            "tokens": int(_number(totals.get("sum_totalTokens"))),
            "calls": int(_number(totals.get("count_count"))),
            "p50_ms": _optional(totals.get("p50_latency")),
        },
        "daily": _daily_series(daily, usd_brl, start, end),
        "models": model_rows,
        "operations": operation_rows,
        "users": user_rows,
        "user_tracking": bool(user_rows),
    }
