"""Tests of the Vercel dashboard: settings, client, billing and summary (no network)."""

import io
import json
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from vercel_dashboard.billing import parse_charges
from vercel_dashboard.client import VercelClient, VercelError
from vercel_dashboard.settings import VercelSettings, load_vercel_settings
from vercel_dashboard.summary import build_vercel_data

GENERATED = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
DAY_MS = 86_400_000
NOON_MS = int(GENERATED.timestamp() * 1000)


class FakeResponse(io.BytesIO):
    """Response object that works as a context manager, like urllib's."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class RecordingOpener:
    """Opener that answers the requests in order and keeps what was asked.

    Parameters
    ----------
    answers : list[bytes | Exception]
        Body of each answer, or an exception to raise, in order.
    """

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


def make_client(answers, team_id=None):
    """Build a client that uses a recording opener.

    Parameters
    ----------
    answers : list[bytes | Exception]
        Answers of the fake opener, in order.
    team_id : str | None
        Team id to configure, if any.

    Returns
    -------
    tuple[VercelClient, RecordingOpener]
        The client and the opener, to inspect the requests.
    """
    opener = RecordingOpener(answers)
    settings = VercelSettings(token="tok_test", team_id=team_id)
    return VercelClient(settings, opener=opener), opener


def json_bytes(payload):
    """Encode a payload as the bytes of a JSON answer.

    Parameters
    ----------
    payload : Any
        Value to encode.

    Returns
    -------
    bytes
        UTF-8 JSON.
    """
    return json.dumps(payload).encode("utf-8")


def test_token_is_required_and_team_is_optional(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("VERCEL_TOKEN=abc\n", encoding="utf-8")
    settings = load_vercel_settings(env)
    assert settings.token == "abc"
    assert settings.team_id is None


def test_missing_token_raises_key_error(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("VERCEL_TEAM_ID=team_1\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_vercel_settings(env)


def test_requests_send_the_bearer_token_and_the_team():
    client, opener = make_client([json_bytes([])], team_id="team_1")
    client.projects()
    request = opener.requests[0]
    assert request.get_header("Authorization") == "Bearer tok_test"
    query = parse_qs(urlsplit(request.full_url).query)
    assert query["teamId"] == ["team_1"]
    assert urlsplit(request.full_url).path == "/v10/projects"


def test_projects_accept_a_list_or_an_object_answer():
    client, _ = make_client([json_bytes({"projects": [{"id": "p1", "name": "app"}]})])
    assert client.projects() == [{"id": "p1", "name": "app"}]


def test_http_error_becomes_a_readable_vercel_error():
    error = urllib.error.HTTPError("https://api.vercel.com", 403, "Forbidden", None, None)
    client, _ = make_client([error])
    with pytest.raises(VercelError, match="403"):
        client.projects()


def test_deployments_follow_the_pagination_until_the_end():
    first = {"deployments": [{"uid": "d1"}], "pagination": {"next": 1000}}
    second = {"deployments": [{"uid": "d2"}], "pagination": {"next": None}}
    client, opener = make_client([json_bytes(first), json_bytes(second)])
    rows = client.deployments(since_ms=500)
    assert [row["uid"] for row in rows] == ["d1", "d2"]
    second_query = parse_qs(urlsplit(opener.requests[1].full_url).query)
    assert second_query["until"] == ["1000"]
    assert second_query["since"] == ["500"]


def test_charges_are_returned_as_text_for_the_period():
    client, opener = make_client([b'{"BilledCost": 1}\n'])
    text = client.charges("2026-10-01T00:00:00Z", "2026-11-05T00:00:00Z")
    assert text == '{"BilledCost": 1}\n'
    query = parse_qs(urlsplit(opener.requests[0].full_url).query)
    assert query["from"] == ["2026-10-01T00:00:00Z"]
    assert urlsplit(opener.requests[0].full_url).path == "/v1/billing/charges"


def test_charge_lines_are_parsed_and_bad_lines_skipped():
    text = "\n".join([
        json.dumps({
            "ChargePeriodStart": "2026-11-02T00:00:00Z",
            "ServiceName": "Edge Requests",
            "BilledCost": 0.5,
            "BillingCurrency": "USD",
        }),
        "isto não é json",
        json.dumps({"ServiceName": "Build", "BilledCost": "1.25"}),
    ])
    charges = parse_charges(text)
    assert len(charges) == 2
    assert charges[0] == {
        "date": "2026-11-02",
        "service": "Edge Requests",
        "cost": 0.5,
        "currency": "USD",
        "quantity": 0.0,
        "unit": "",
    }
    assert charges[1]["cost"] == 1.25
    assert charges[1]["service"] == "Build"


def test_consumed_quantity_and_unit_are_read():
    text = json.dumps({
        "ServiceName": "Fast Data Transfer",
        "BilledCost": 0,
        "ConsumedQuantity": "2.5",
        "ConsumedUnit": "GB",
    })
    charge = parse_charges(text)[0]
    assert charge["quantity"] == 2.5
    assert charge["unit"] == "GB"


def test_usage_is_listed_even_when_the_cost_is_zero():
    charges = [
        {"date": "2026-11-04", "service": "Fast Data Transfer", "cost": 0.0,
         "currency": "USD", "quantity": 12.0, "unit": "GB"},
    ]
    data = build_vercel_data(
        [], [], charges, None, date(2026, 11, 3), date(2026, 11, 5), GENERATED,
    )
    assert data["billing"]["total"] == 0.0
    assert data["billing"]["by_service"][0] == {
        "service": "Fast Data Transfer",
        "cost": 0.0,
        "quantity": 12.0,
        "unit": "GB",
    }


def make_deployment(uid, project_id, state, created_ms, target="production"):
    """Build a deployment as the Vercel API returns it, for the tests.

    Parameters
    ----------
    uid : str
        Deployment id.
    project_id : str
        Id of the project.
    state : str
        Ready state, such as READY or ERROR.
    created_ms : int
        Creation time, in milliseconds since the epoch.
    target : str
        Environment of the deployment.

    Returns
    -------
    dict
        Deployment with the fields the summary reads.
    """
    return {
        "uid": uid,
        "projectId": project_id,
        "readyState": state,
        "createdAt": created_ms,
        "ready": created_ms + 30_000,
        "url": f"{uid}.vercel.app",
        "target": target,
        "meta": {"githubCommitRef": "main"},
    }


def test_summary_counts_states_projects_and_success_rate():
    projects = [{"id": "p1", "name": "site"}, {"id": "p2", "name": "api"}]
    deployments = [
        make_deployment("d1", "p1", "READY", NOON_MS),
        make_deployment("d2", "p1", "ERROR", NOON_MS - DAY_MS),
        make_deployment("d3", "p2", "READY", NOON_MS - 2 * DAY_MS),
    ]
    data = build_vercel_data(
        projects, deployments, None, "sem permissão",
        date(2026, 11, 3), date(2026, 11, 5), GENERATED,
    )
    assert data["summary"] == {
        "applications": 2,
        "deploys": 3,
        "ready": 2,
        "errors": 1,
        "success_rate": 66.7,
    }
    site = next(row for row in data["projects"] if row["name"] == "site")
    assert site["deploys"] == 2
    assert site["errors"] == 1
    assert site["last_state"] == "READY"
    assert site["last_url"] == "https://d1.vercel.app"


def test_daily_counts_cover_every_day_of_the_window():
    deployments = [make_deployment("d1", "p1", "READY", NOON_MS)]
    data = build_vercel_data(
        [{"id": "p1", "name": "site"}], deployments, None, None,
        date(2026, 11, 3), date(2026, 11, 5), GENERATED,
    )
    assert [day["date"] for day in data["daily"]] == [
        "2026-11-03", "2026-11-04", "2026-11-05",
    ]
    assert data["daily"][-1]["ready"] == 1


def test_recent_rows_carry_branch_and_duration():
    deployments = [make_deployment("d1", "p1", "READY", NOON_MS)]
    data = build_vercel_data(
        [{"id": "p1", "name": "site"}], deployments, None, None,
        date(2026, 11, 3), date(2026, 11, 5), GENERATED,
    )
    row = data["recent"][0]
    assert row["project"] == "site"
    assert row["branch"] == "main"
    assert row["duration_s"] == 30.0


def test_billing_is_summarized_by_service_and_day():
    charges = [
        {"date": "2026-11-04", "service": "Edge Requests", "cost": 1.0,
         "currency": "USD", "quantity": 3.0, "unit": "GB"},
        {"date": "2026-11-04", "service": "Build", "cost": 0.5,
         "currency": "USD", "quantity": 10.0, "unit": "min"},
        {"date": "2026-11-05", "service": "Edge Requests", "cost": 0.25,
         "currency": "USD", "quantity": 1.0, "unit": "GB"},
    ]
    data = build_vercel_data(
        [], [], charges, None, date(2026, 11, 3), date(2026, 11, 5), GENERATED,
    )
    billing = data["billing"]
    assert billing["available"] is True
    assert billing["total"] == 1.75
    assert billing["by_service"][0]["service"] == "Edge Requests"
    assert billing["by_service"][0]["cost"] == 1.25
    assert billing["by_service"][0]["quantity"] == 4.0
    assert billing["by_service"][0]["unit"] == "GB"
    assert [day["cost"] for day in billing["daily"]] == [0.0, 1.5, 0.25]


def test_unavailable_billing_keeps_the_reason():
    data = build_vercel_data(
        [], [], None, "Sem permissão.", date(2026, 11, 3), date(2026, 11, 5), GENERATED,
    )
    assert data["billing"]["available"] is False
    assert data["billing"]["message"] == "Sem permissão."
    assert data["summary"]["success_rate"] is None
