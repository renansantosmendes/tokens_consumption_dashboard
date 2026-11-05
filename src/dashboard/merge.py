"""Combines the query answers of several Langfuse projects (pure functions)."""

from typing import Any

RawData = dict[str, Any]
COST_TOKEN_CALL_FIELDS = ("sum_totalCost", "sum_totalTokens", "count_count")


def _add(target: dict[str, float], key: str, value: Any) -> None:
    """Add a numeric cell to a running total, ignoring empty cells.

    Parameters
    ----------
    target : dict[str, float]
        Running totals, by field name.
    key : str
        Field to add to.
    value : Any
        Cell to add; non-numeric values are skipped.

    Returns
    -------
    None
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        target[key] = target.get(key, 0.0) + float(value)


def _add_fields(target: dict[str, float], row: dict[str, Any], fields: tuple[str, ...]) -> None:
    """Add several numeric cells of a row to a running total.

    Parameters
    ----------
    target : dict[str, float]
        Running totals, by field name.
    row : dict[str, Any]
        Row whose cells are added.
    fields : tuple[str, ...]
        Cells to add.

    Returns
    -------
    None
    """
    for field in fields:
        _add(target, field, row.get(field))


def _weighted_latency(pairs: list[tuple[float, float]]) -> float | None:
    """Weighted average of latencies, weighted by the number of calls.

    Parameters
    ----------
    pairs : list[tuple[float, float]]
        Pairs of (latency in ms, number of calls).

    Returns
    -------
    float | None
        The average, or None when there is no weight.
    """
    weight = sum(calls for _latency, calls in pairs)
    if not weight:
        return None
    return sum(latency * calls for latency, calls in pairs) / weight


def _merge_totals(raws: list[RawData]) -> dict[str, Any]:
    """Sum the totals of the projects and combine their median latencies.

    Parameters
    ----------
    raws : list[RawData]
        Raw answers of the projects.

    Returns
    -------
    dict[str, Any]
        Totals row with the combined median latency.
    """
    totals: dict[str, float] = {}
    pairs: list[tuple[float, float]] = []
    for raw in raws:
        total = raw.get("totals") or {}
        _add_fields(totals, total, COST_TOKEN_CALL_FIELDS)
        if isinstance(total.get("p50_latency"), (int, float)):
            calls = float(total.get("count_count") or 0)
            pairs.append((float(total["p50_latency"]), calls))
    return {**totals, "p50_latency": _weighted_latency(pairs)}


def _merge_by_key(
    rows: list[dict[str, Any]],
    key: str,
    fields: tuple[str, ...],
    target: dict,
) -> None:
    """Add the cells of rows into groups identified by one key.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Rows of one project's answer.
    key : str
        Field that identifies the group of each row.
    fields : tuple[str, ...]
        Cells to add.
    target : dict
        Groups, updated in place.

    Returns
    -------
    None
    """
    for row in rows:
        _add_fields(target.setdefault(row.get(key), {}), row, fields)


def _merge_operations(raws: list[RawData]) -> list[dict[str, Any]]:
    """Combine the latency of each operation across the projects.

    Parameters
    ----------
    raws : list[RawData]
        Raw answers of the projects.

    Returns
    -------
    list[dict[str, Any]]
        One row per operation name, with summed calls, the weighted median and
        the highest 95th percentile.
    """
    groups: dict[Any, dict[str, Any]] = {}
    for raw in raws:
        for row in raw.get("operations") or []:
            entry = groups.setdefault(
                row.get("name"), {"count_count": 0.0, "pairs": [], "p95_latency": None}
            )
            calls = float(row.get("count_count") or 0)
            entry["count_count"] += calls
            if isinstance(row.get("p50_latency"), (int, float)):
                entry["pairs"].append((float(row["p50_latency"]), calls))
            p95 = row.get("p95_latency")
            current = entry["p95_latency"]
            is_number = isinstance(p95, (int, float))
            if is_number and (current is None or p95 > current):
                entry["p95_latency"] = float(p95)
    return [
        {
            "name": name,
            "count_count": entry["count_count"],
            "p50_latency": _weighted_latency(entry["pairs"]),
            "p95_latency": entry["p95_latency"],
        }
        for name, entry in groups.items()
    ]


def _merge_daily_latency(raws: list[RawData]) -> list[dict[str, Any]]:
    """Combine the daily latency of the projects.

    Parameters
    ----------
    raws : list[RawData]
        Raw answers of the projects.

    Returns
    -------
    list[dict[str, Any]]
        One row per day with the weighted median, the highest 95th percentile
        and the number of calls.
    """
    groups: dict[str, dict[str, Any]] = {}
    for raw in raws:
        for row in raw.get("daily_latency") or []:
            day = str(row.get("time_dimension", ""))
            entry = groups.setdefault(day, {"pairs": [], "p95": None, "calls": 0.0})
            calls = float(row.get("count_count") or 0)
            entry["calls"] += calls
            if isinstance(row.get("p50_latency"), (int, float)):
                entry["pairs"].append((float(row["p50_latency"]), calls))
            p95 = row.get("p95_latency")
            if isinstance(p95, (int, float)) and (entry["p95"] is None or p95 > entry["p95"]):
                entry["p95"] = float(p95)
    return [
        {
            "time_dimension": day,
            "p50_latency": _weighted_latency(entry["pairs"]),
            "p95_latency": entry["p95"],
            "count_count": entry["calls"],
        }
        for day, entry in sorted(groups.items())
    ]


def merge_raw(sources: list[RawData]) -> RawData:
    """Merge the raw answers of each project into one set of rows.

    Costs, tokens and calls are summed. Latency medians are combined as
    averages weighted by calls, and the 95th percentile keeps the highest
    value of the sources, so both are approximations across projects.

    Parameters
    ----------
    sources : list[RawData]
        One raw answer per project, with keys totals, models, daily,
        operations and users.

    Returns
    -------
    RawData
        Rows with the same shape as one project's answer.
    """
    models: dict[Any, dict[str, float]] = {}
    daily: dict[Any, dict[str, float]] = {}
    users: dict[Any, dict[str, float]] = {}
    for raw in sources:
        _merge_by_key(raw.get("models") or [], "providedModelName", COST_TOKEN_CALL_FIELDS, models)
        _merge_by_key(raw.get("daily") or [], "time_dimension", COST_TOKEN_CALL_FIELDS, daily)
        _merge_by_key(
            [row for row in raw.get("users") or [] if row.get("userId")],
            "userId",
            ("sum_totalCost", "sum_totalTokens"),
            users,
        )
    return {
        "totals": _merge_totals(sources),
        "models": [{"providedModelName": name, **values} for name, values in models.items()],
        "daily": [
            {"time_dimension": day, **values}
            for day, values in sorted(daily.items(), key=lambda item: str(item[0]))
        ],
        "daily_latency": _merge_daily_latency(sources),
        "operations": _merge_operations(sources),
        "users": [{"userId": user, **values} for user, values in users.items()],
    }
