"""Tests of the collector: queries, summary, exchange rate and client, without network."""

import io
import json
from datetime import date, datetime, timezone

import pytest

from dashboard import queries
from dashboard.exchange import ExchangeRateError, latest_usd_sell_rate
from dashboard.langfuse_client import LangfuseClient, LangfuseError
from dashboard.settings import Settings, load_settings
from dashboard.summary import build_dashboard


class FakeResponse(io.BytesIO):
    """Response object that works as a context manager, like urllib's."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def fake_opener(payload):
    """Build an opener that answers any request with the given JSON payload.

    Parameters
    ----------
    payload : Any
        JSON body of the answer.

    Returns
    -------
    Callable
        Function with the signature of ``urllib.request.urlopen``.
    """

    def opener(request, timeout=None):
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    return opener


def test_window_is_iso_utc_with_the_requested_length():
    start, end = queries.window(datetime(2026, 11, 4, tzinfo=timezone.utc), 30)
    assert start == "2026-10-05T00:00:00Z"
    assert end == "2026-11-04T00:00:00Z"


def test_totals_and_models_count_only_generations():
    totals = queries.totals("a", "b")
    assert totals["filters"][0]["value"] == "GENERATION"
    by_model = queries.by_model("a", "b")
    assert by_model["dimensions"] == [{"field": "providedModelName"}]


def test_user_query_uses_a_row_limit_and_orders_by_cost():
    query = queries.cost_by_user("a", "b")
    assert query["config"]["row_limit"] == queries.TOP_USERS
    assert query["orderBy"] == [{"field": "sum_totalCost", "direction": "desc"}]


def test_client_sends_the_basic_authentication_and_the_query():
    seen = {}

    def opener(request, timeout=None):
        seen["auth"] = request.get_header("Authorization")
        seen["url"] = request.full_url
        return FakeResponse(json.dumps({"data": [{"sum_totalCost": 0.5}]}).encode())

    settings = Settings(host="https://langfuse.example", public_key="pk", secret_key="sk")
    rows = LangfuseClient(settings, opener=opener).metrics(queries.totals("a", "b"))
    assert rows == [{"sum_totalCost": 0.5}]
    assert seen["auth"].startswith("Basic ")
    assert seen["url"].startswith("https://langfuse.example/api/public/v2/metrics?query=")


def test_client_turns_http_errors_into_langfuse_errors():
    import urllib.error

    def opener(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    settings = Settings(host="https://langfuse.example", public_key="pk", secret_key="sk")
    with pytest.raises(LangfuseError, match="401"):
        LangfuseClient(settings, opener=opener).metrics(queries.totals("a", "b"))


def test_client_refuses_an_answer_without_data():
    settings = Settings(host="https://langfuse.example", public_key="pk", secret_key="sk")
    with pytest.raises(LangfuseError):
        LangfuseClient(settings, opener=fake_opener({"error": "x"})).metrics(queries.totals("a", "b"))


def test_exchange_rate_is_the_latest_selling_quote():
    payload = {"value": [
        {"cotacaoVenda": 5.4778, "dataHoraCotacao": "2026-11-04 13:05:19"},
        {"cotacaoVenda": 5.4935, "dataHoraCotacao": "2026-11-03 13:06:31"},
    ]}
    rate, when = latest_usd_sell_rate(date(2026, 11, 4), opener=fake_opener(payload))
    assert rate == 5.4778
    assert when == "2026-11-04 13:05:19"


def test_exchange_rate_without_quotes_is_an_error():
    with pytest.raises(ExchangeRateError):
        latest_usd_sell_rate(date(2026, 11, 4), opener=fake_opener({"value": []}))


def test_settings_require_the_langfuse_variables(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LANGFUSE_HOST=https://us.cloud.langfuse.com/\nLANGFUSE_PUBLIC_KEY=pk\n", encoding="utf-8")
    with pytest.raises(KeyError, match="LANGFUSE_SECRET_KEY"):
        load_settings(env)


def test_settings_strip_the_trailing_slash_of_the_host(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "LANGFUSE_HOST=https://us.cloud.langfuse.com/\nLANGFUSE_PUBLIC_KEY=pk\nLANGFUSE_SECRET_KEY=sk\n",
        encoding="utf-8",
    )
    assert load_settings(env).host == "https://us.cloud.langfuse.com"


def test_summary_converts_costs_and_fills_missing_days():
    daily_rows = [{"time_dimension": "2026-11-02", "sum_totalCost": 0.1, "sum_totalTokens": 1000, "count_count": 3}]
    result = build_dashboard(
        totals={"sum_totalCost": 0.2, "sum_totalTokens": 2000, "count_count": 5, "p50_latency": 700.0},
        models=[{"providedModelName": None, "sum_totalCost": 0, "sum_totalTokens": 0, "count_count": 2},
                {"providedModelName": "gpt-x", "sum_totalCost": 0.2, "sum_totalTokens": 2000, "count_count": 3}],
        daily=daily_rows,
        operations=[{"name": None, "count_count": 4, "p50_latency": 1.0, "p95_latency": 2.0}],
        users=[{"userId": None, "sum_totalCost": 0.2, "sum_totalTokens": 2000}],
        usd_brl=5.0,
        rate_date="2026-11-04",
        start=date(2026, 11, 1),
        end=date(2026, 11, 3),
        generated_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )
    assert result["totals"]["cost_brl"] == 1.0
    assert result["models"][0]["model"] == "gpt-x"
    assert result["models"][1]["model"] == "modelo não identificado"
    assert [day["date"] for day in result["daily"]] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert result["daily"][0]["calls"] == 0
    assert result["daily"][1]["cost_brl"] == 0.5
    assert result["operations"][0]["name"] == "sem nome"
    assert result["user_tracking"] is False
    assert result["users"] == []


def test_summary_lists_users_when_the_traces_have_them():
    result = build_dashboard(
        totals={}, models=[], daily=[], operations=[],
        users=[{"userId": "u-1", "sum_totalCost": 0.4, "sum_totalTokens": 900},
               {"userId": None, "sum_totalCost": 0.1, "sum_totalTokens": 100}],
        usd_brl=5.0, rate_date=None,
        start=date(2026, 11, 1), end=date(2026, 11, 1),
        generated_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert result["user_tracking"] is True
    assert result["users"] == [{"user_id": "u-1", "cost_brl": 2.0, "tokens": 900}]
