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
        sources=["agente"],
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
        sources=["proxy"], usd_brl=5.0, rate_date=None,
        start=date(2026, 11, 1), end=date(2026, 11, 1),
        generated_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert result["user_tracking"] is True
    assert result["users"] == [{"user_id": "u-1", "name": None, "cost_brl": 2.0, "tokens": 900}]
    assert result["sources"] == ["proxy"]


def test_settings_accept_the_proxy_base_url_name(tmp_path):
    env = tmp_path / ".env_proxy"
    env.write_text(
        "LANGFUSE_BASE_URL=https://us.cloud.langfuse.com/\nLANGFUSE_PUBLIC_KEY=pk\nLANGFUSE_SECRET_KEY=sk\n",
        encoding="utf-8",
    )
    assert load_settings(env).host == "https://us.cloud.langfuse.com"


def test_settings_without_any_host_name_the_missing_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LANGFUSE_PUBLIC_KEY=pk\nLANGFUSE_SECRET_KEY=sk\n", encoding="utf-8")
    with pytest.raises(KeyError, match="LANGFUSE_HOST"):
        load_settings(env)


def test_merge_sums_costs_tokens_and_calls_of_each_project():
    from dashboard.merge import merge_raw

    agent = {
        "totals": {"sum_totalCost": 0.2, "sum_totalTokens": 100, "count_count": 2, "p50_latency": 100.0},
        "models": [{"providedModelName": "gpt-x", "sum_totalCost": 0.2, "sum_totalTokens": 100, "count_count": 2}],
        "daily": [{"time_dimension": "2026-11-02", "sum_totalCost": 0.2, "sum_totalTokens": 100, "count_count": 2}],
        "operations": [{"name": "ChatOpenAI", "count_count": 2, "p50_latency": 100.0, "p95_latency": 300.0}],
        "users": [],
    }
    proxy = {
        "totals": {"sum_totalCost": 0.1, "sum_totalTokens": 50, "count_count": 1, "p50_latency": 300.0},
        "models": [{"providedModelName": "gpt-x", "sum_totalCost": 0.1, "sum_totalTokens": 50, "count_count": 1}],
        "daily": [{"time_dimension": "2026-11-02", "sum_totalCost": 0.1, "sum_totalTokens": 50, "count_count": 1}],
        "operations": [{"name": "ChatOpenAI", "count_count": 1, "p50_latency": 300.0, "p95_latency": 900.0}],
        "users": [{"userId": "1666122", "sum_totalCost": 0.1, "sum_totalTokens": 50}],
    }
    merged = merge_raw([agent, proxy])
    assert merged["totals"]["sum_totalCost"] == pytest.approx(0.3)
    assert merged["totals"]["sum_totalTokens"] == 150
    assert merged["totals"]["count_count"] == 3
    assert merged["totals"]["p50_latency"] == pytest.approx((100 * 2 + 300 * 1) / 3)
    assert merged["models"][0]["count_count"] == 3.0
    assert merged["daily"][0]["count_count"] == 3.0
    op = merged["operations"][0]
    assert op["count_count"] == 3.0
    assert op["p95_latency"] == 900.0
    assert merged["users"] == [{"userId": "1666122", "sum_totalCost": 0.1, "sum_totalTokens": 50.0}]


def test_source_argument_takes_label_and_path():
    import argparse

    from dashboard.build import parse_source

    source = parse_source("proxy=C:/x/.env_proxy")
    assert source.label == "proxy"
    assert str(source.env_path).endswith(".env_proxy")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_source("sem-igual")


def test_default_sources_are_the_agent_and_the_proxy():
    from dashboard.build import parse_args

    options = parse_args([])
    assert [source.label for source in options.source] == ["agente", "proxy"]
    assert options.source[1].env_path.name == ".env_proxy"


def test_user_rows_carry_the_student_name_when_known():
    result = build_dashboard(
        totals={}, models=[], daily=[], operations=[],
        users=[{"userId": "1666122", "sum_totalCost": 0.1, "sum_totalTokens": 50},
               {"userId": "999", "sum_totalCost": 0.05, "sum_totalTokens": 20}],
        sources=["proxy"], student_names={"1666122": "Aluno Teste"}, usd_brl=5.0, rate_date=None,
        start=date(2026, 11, 1), end=date(2026, 11, 1),
        generated_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert result["users"][0]["name"] == "Aluno Teste"
    assert result["users"][1]["name"] is None


def test_student_names_are_read_with_a_read_only_connection(tmp_path, monkeypatch):
    from dashboard import students

    seen = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, query):
            seen["query"] = query

        def fetchall(self):
            return [("1666122", "Aluno Teste")]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def cursor(self):
            return FakeCursor()

    def fake_connect(url, **kwargs):
        seen["url"] = url
        seen["options"] = kwargs["options"]
        return FakeConnection()

    monkeypatch.setattr("psycopg.connect", fake_connect)
    names = students.fetch_student_names("postgresql://user@host/db")
    assert names == {"1666122": "Aluno Teste"}
    assert "default_transaction_read_only=on" in seen["options"]
    assert seen["query"].lstrip().upper().startswith("SELECT")


def test_database_url_is_read_from_the_env_file(tmp_path):
    from dashboard.students import StudentsError, load_database_url

    env = tmp_path / ".env_proxy"
    env.write_text("NEON_DATABASE_URL=postgresql://u@h/db\n", encoding="utf-8")
    assert load_database_url(env) == "postgresql://u@h/db"
    empty = tmp_path / "vazio.env"
    empty.write_text("OUTRA=1\n", encoding="utf-8")
    with pytest.raises(StudentsError):
        load_database_url(empty)


def test_daily_latency_is_merged_per_day_across_projects():
    from dashboard.merge import merge_raw

    agent = {"daily_latency": [{"time_dimension": "2026-11-02", "p50_latency": 100.0, "p95_latency": 300.0, "count_count": 2}]}
    proxy = {"daily_latency": [{"time_dimension": "2026-11-02", "p50_latency": 400.0, "p95_latency": 900.0, "count_count": 2}]}
    row = merge_raw([agent, proxy])["daily_latency"][0]
    assert row["p50_latency"] == pytest.approx(250.0)
    assert row["p95_latency"] == 900.0
    assert row["count_count"] == 4.0


def test_latency_series_has_a_gap_on_days_without_calls():
    result = build_dashboard(
        totals={}, models=[], daily=[], operations=[], users=[],
        daily_latency=[{"time_dimension": "2026-11-02", "p50_latency": 500.0, "p95_latency": 1500.0, "count_count": 3}],
        sources=["agente"], usd_brl=5.0, rate_date=None,
        start=date(2026, 11, 1), end=date(2026, 11, 3),
        generated_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )
    series = result["latency_daily"]
    assert [item["date"] for item in series] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert series[0]["p50_ms"] is None
    assert series[1]["p50_ms"] == 500.0
    assert series[1]["calls"] == 3
