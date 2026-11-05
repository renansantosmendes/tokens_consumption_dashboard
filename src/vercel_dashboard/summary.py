"""Turns the Vercel projects, deployments and charges into dashboard data (pure)."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from vercel_dashboard.billing import DEFAULT_CURRENCY

RECENT_LIMIT = 30
TOP_SERVICES = 10
READY_STATE = "READY"
ERROR_STATE = "ERROR"
UNNAMED_PROJECT = "sem nome"
UNKNOWN_STATE = "DESCONHECIDO"


def _iso(milliseconds: Any) -> str | None:
    """Convert a Vercel timestamp in milliseconds to an ISO UTC text.

    Parameters
    ----------
    milliseconds : Any
        Timestamp in milliseconds since the epoch.

    Returns
    -------
    str | None
        ISO 8601 text in UTC, or None when the value is not a number.
    """
    if isinstance(milliseconds, bool) or not isinstance(milliseconds, (int, float)):
        return None
    moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _created(deployment: dict[str, Any]) -> float:
    """Creation time of a deployment, used to sort them.

    Parameters
    ----------
    deployment : dict[str, Any]
        Deployment as returned by the Vercel API.

    Returns
    -------
    float
        Creation time in milliseconds; zero when missing.
    """
    value = deployment.get("createdAt")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _state(deployment: dict[str, Any]) -> str:
    """Final or current state of a deployment.

    Parameters
    ----------
    deployment : dict[str, Any]
        Deployment as returned by the Vercel API.

    Returns
    -------
    str
        State such as READY, ERROR or BUILDING.
    """
    return str(deployment.get("readyState") or deployment.get("state") or UNKNOWN_STATE)


def _url(deployment: dict[str, Any]) -> str | None:
    """Public address of a deployment.

    Parameters
    ----------
    deployment : dict[str, Any]
        Deployment as returned by the Vercel API.

    Returns
    -------
    str | None
        The address with https, or None while the upload is incomplete.
    """
    url = deployment.get("url")
    return f"https://{url}" if url else None


def _duration_seconds(deployment: dict[str, Any]) -> float | None:
    """Time between the creation and the end of a build.

    Parameters
    ----------
    deployment : dict[str, Any]
        Deployment as returned by the Vercel API.

    Returns
    -------
    float | None
        Duration in seconds with one decimal, or None when the build did not end.
    """
    created = deployment.get("createdAt")
    ready = deployment.get("ready")
    if not isinstance(created, (int, float)) or not isinstance(ready, (int, float)):
        return None
    if ready < created:
        return None
    return round((ready - created) / 1000, 1)


def _days(start: date, end: date) -> list[str]:
    """List the dates of a window, both ends included.

    Parameters
    ----------
    start : date
        First day.
    end : date
        Last day.

    Returns
    -------
    list[str]
        Dates as YYYY-MM-DD, in order.
    """
    count = (end - start).days + 1
    return [(start + timedelta(days=offset)).isoformat() for offset in range(count)]


def _project_rows(
    projects: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One row per project with its latest deployment and counts.

    Parameters
    ----------
    projects : list[dict[str, Any]]
        Projects as returned by the Vercel API.
    deployments : list[dict[str, Any]]
        Deployments of the window.

    Returns
    -------
    list[dict[str, Any]]
        Rows sorted by the latest deployment, most recent first.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for deployment in deployments:
        grouped.setdefault(str(deployment.get("projectId")), []).append(deployment)
    rows = []
    for project in projects:
        items = sorted(
            grouped.get(str(project.get("id")), []), key=_created, reverse=True
        )
        latest = items[0] if items else {}
        rows.append(
            {
                "name": str(project.get("name") or UNNAMED_PROJECT),
                "framework": project.get("framework"),
                "deploys": len(items),
                "errors": sum(1 for item in items if _state(item) == ERROR_STATE),
                "last_state": _state(latest) if items else None,
                "last_target": latest.get("target"),
                "last_url": _url(latest),
                "last_at": _iso(latest.get("createdAt")),
            }
        )
    return sorted(rows, key=lambda row: row["last_at"] or "", reverse=True)


def _recent_rows(
    projects: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The latest deployments of the window, with the project name.

    Parameters
    ----------
    projects : list[dict[str, Any]]
        Projects, to name each deployment.
    deployments : list[dict[str, Any]]
        Deployments of the window.

    Returns
    -------
    list[dict[str, Any]]
        Up to ``RECENT_LIMIT`` rows, most recent first.
    """
    names = {str(project.get("id")): project.get("name") for project in projects}
    ordered = sorted(deployments, key=_created, reverse=True)[:RECENT_LIMIT]
    rows = []
    for deployment in ordered:
        meta = deployment.get("meta")
        branch = meta.get("githubCommitRef") if isinstance(meta, dict) else None
        project_id = str(deployment.get("projectId"))
        rows.append(
            {
                "time": _iso(deployment.get("createdAt")),
                "project": str(
                    names.get(project_id) or deployment.get("name") or UNNAMED_PROJECT
                ),
                "state": _state(deployment),
                "target": deployment.get("target"),
                "branch": branch,
                "url": _url(deployment),
                "duration_s": _duration_seconds(deployment),
            }
        )
    return rows


def _daily_deploys(
    deployments: list[dict[str, Any]],
    days: list[str],
) -> list[dict[str, Any]]:
    """Count the deployments of each day of the window.

    Parameters
    ----------
    deployments : list[dict[str, Any]]
        Deployments of the window.
    days : list[str]
        Dates of the window, as YYYY-MM-DD.

    Returns
    -------
    list[dict[str, Any]]
        One entry per day with total, ready and error counts.
    """
    counts = {day: {"date": day, "total": 0, "ready": 0, "error": 0} for day in days}
    for deployment in deployments:
        day = (_iso(deployment.get("createdAt")) or "")[:10]
        if day not in counts:
            continue
        counts[day]["total"] += 1
        state = _state(deployment)
        if state == READY_STATE:
            counts[day]["ready"] += 1
        elif state == ERROR_STATE:
            counts[day]["error"] += 1
    return list(counts.values())


def _billing_block(
    charges: list[dict[str, Any]] | None,
    charges_error: str | None,
    days: list[str],
) -> dict[str, Any]:
    """Summarize the charges, or explain why they are not available.

    Parameters
    ----------
    charges : list[dict[str, Any]] | None
        Charges read from the billing endpoint; None when it failed.
    charges_error : str | None
        Message of the failure, when the billing could not be read.
    days : list[str]
        Dates of the window, as YYYY-MM-DD.

    Returns
    -------
    dict[str, Any]
        Availability, currency, total, cost by service and cost by day.
    """
    if charges is None:
        return {
            "available": False,
            "message": charges_error or "Cobrança indisponível.",
            "currency": DEFAULT_CURRENCY,
            "total": 0.0,
            "by_service": [],
            "daily": [],
        }
    currency_counts = Counter(charge["currency"] for charge in charges)
    currency = currency_counts.most_common(1)[0][0] if currency_counts else DEFAULT_CURRENCY
    by_service: Counter[str] = Counter()
    quantity_by_service: Counter[str] = Counter()
    unit_by_service: dict[str, str] = {}
    by_day: Counter[str] = Counter()
    for charge in charges:
        by_service[charge["service"]] += charge["cost"]
        quantity_by_service[charge["service"]] += charge["quantity"]
        unit_by_service.setdefault(charge["service"], charge["unit"])
        by_day[charge["date"]] += charge["cost"]
    ranked = sorted(
        by_service,
        key=lambda name: (by_service[name], quantity_by_service[name]),
        reverse=True,
    )[:TOP_SERVICES]
    services = [
        {
            "service": name,
            "cost": round(by_service[name], 4),
            "quantity": round(quantity_by_service[name], 4),
            "unit": unit_by_service.get(name, ""),
        }
        for name in ranked
    ]
    daily = [
        {"date": day, "cost": round(by_day.get(day, 0.0), 4)} for day in days
    ]
    return {
        "available": True,
        "message": None,
        "currency": currency,
        "total": round(sum(by_service.values()), 4),
        "by_service": services,
        "daily": daily,
    }


def build_vercel_data(
    projects: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
    charges: list[dict[str, Any]] | None,
    charges_error: str | None,
    start: date,
    end: date,
    generated_at: datetime,
) -> dict[str, Any]:
    """Build the data of the Vercel dashboard.

    Parameters
    ----------
    projects : list[dict[str, Any]]
        Projects as returned by the Vercel API.
    deployments : list[dict[str, Any]]
        Deployments created in the window.
    charges : list[dict[str, Any]] | None
        Parsed billing charges; None when the billing could not be read.
    charges_error : str | None
        Reason why the billing could not be read.
    start : date
        First day of the window.
    end : date
        Last day of the window.
    generated_at : datetime
        Moment of the collection, timezone aware.

    Returns
    -------
    dict[str, Any]
        Summary, projects, recent deployments, daily counts and billing.

    Example
    -------
    >>> from datetime import date, datetime, timezone
    >>> data = build_vercel_data(
    ...     [{"id": "p1", "name": "app"}],
    ...     [{"projectId": "p1", "readyState": "READY", "createdAt": 0}],
    ...     None,
    ...     "sem permissão",
    ...     date(1970, 1, 1),
    ...     date(1970, 1, 1),
    ...     datetime(1970, 1, 2, tzinfo=timezone.utc),
    ... )
    >>> data["summary"]["success_rate"]
    100.0
    """
    days = _days(start, end)
    ready = sum(1 for item in deployments if _state(item) == READY_STATE)
    errors = sum(1 for item in deployments if _state(item) == ERROR_STATE)
    finished = ready + errors
    return {
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "summary": {
            "applications": len(projects),
            "deploys": len(deployments),
            "ready": ready,
            "errors": errors,
            "success_rate": round(100 * ready / finished, 1) if finished else None,
        },
        "projects": _project_rows(projects, deployments),
        "recent": _recent_rows(projects, deployments),
        "daily": _daily_deploys(deployments, days),
        "states": dict(Counter(_state(item) for item in deployments)),
        "billing": _billing_block(charges, charges_error, days),
    }
