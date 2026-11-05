"""Query builders for the Langfuse metrics API (pure functions)."""

from datetime import datetime, timedelta
from typing import Any

GENERATION_FILTER = {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}
TOP_USERS = 20


def window(end: datetime, days: int) -> tuple[str, str]:
    """Build the start and end of the analysis window as ISO timestamps.

    Parameters
    ----------
    end : datetime
        Last moment of the window, timezone aware.
    days : int
        Length of the window, in days.

    Returns
    -------
    tuple[str, str]
        Start and end, in UTC ISO 8601 with a ``Z`` suffix.

    Example
    -------
    >>> from datetime import datetime, timezone
    >>> window(datetime(2026, 11, 4, tzinfo=timezone.utc), 2)
    ('2026-11-02T00:00:00Z', '2026-11-04T00:00:00Z')
    """
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def _base(start: str, end: str) -> dict[str, Any]:
    """Common fields of every query: the view and the window.

    Parameters
    ----------
    start : str
        Start of the window.
    end : str
        End of the window.

    Returns
    -------
    dict[str, Any]
        Query with the observations view and the window.
    """
    return {"view": "observations", "fromTimestamp": start, "toTimestamp": end, "filters": []}


def totals(start: str, end: str) -> dict[str, Any]:
    """Query the totals of the window: cost, tokens, calls and median latency.

    Parameters
    ----------
    start : str
        Start of the window.
    end : str
        End of the window.

    Returns
    -------
    dict[str, Any]
        Query for the totals.
    """
    query = _base(start, end)
    query["filters"] = [GENERATION_FILTER]
    query["metrics"] = [
        {"measure": "totalCost", "aggregation": "sum"},
        {"measure": "totalTokens", "aggregation": "sum"},
        {"measure": "count", "aggregation": "count"},
        {"measure": "latency", "aggregation": "p50"},
    ]
    return query


def by_model(start: str, end: str) -> dict[str, Any]:
    """Query cost, tokens and calls grouped by model.

    Parameters
    ----------
    start : str
        Start of the window.
    end : str
        End of the window.

    Returns
    -------
    dict[str, Any]
        Query grouped by the model name.
    """
    query = totals(start, end)
    query["dimensions"] = [{"field": "providedModelName"}]
    query["metrics"] = query["metrics"][:3]
    return query


def daily(start: str, end: str) -> dict[str, Any]:
    """Query cost, tokens and calls per day.

    Parameters
    ----------
    start : str
        Start of the window.
    end : str
        End of the window.

    Returns
    -------
    dict[str, Any]
        Query with a daily time dimension.
    """
    query = totals(start, end)
    query["metrics"] = query["metrics"][:3]
    query["timeDimension"] = {"granularity": "day"}
    return query


def latency_by_operation(start: str, end: str) -> dict[str, Any]:
    """Query the median and 95th percentile latency of each operation name.

    Parameters
    ----------
    start : str
        Start of the window.
    end : str
        End of the window.

    Returns
    -------
    dict[str, Any]
        Query grouped by the observation name.
    """
    query = _base(start, end)
    query["dimensions"] = [{"field": "name"}]
    query["metrics"] = [
        {"measure": "latency", "aggregation": "p50"},
        {"measure": "latency", "aggregation": "p95"},
        {"measure": "count", "aggregation": "count"},
    ]
    return query


def cost_by_user(start: str, end: str) -> dict[str, Any]:
    """Query cost and tokens grouped by user, highest cost first.

    Parameters
    ----------
    start : str
        Start of the window.
    end : str
        End of the window.

    Returns
    -------
    dict[str, Any]
        Query grouped by the user id, limited to the top users.
    """
    query = _base(start, end)
    query["filters"] = [GENERATION_FILTER]
    query["dimensions"] = [{"field": "userId"}]
    query["metrics"] = [
        {"measure": "totalCost", "aggregation": "sum"},
        {"measure": "totalTokens", "aggregation": "sum"},
    ]
    query["orderBy"] = [{"field": "sum_totalCost", "direction": "desc"}]
    query["config"] = {"row_limit": TOP_USERS}
    return query
