"""Command that collects the Langfuse metrics and writes the dashboard data."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dashboard import queries
from dashboard.exchange import ExchangeRateError, latest_usd_sell_rate
from dashboard.langfuse_client import LangfuseClient, LangfuseError
from dashboard.settings import load_settings
from dashboard.summary import build_dashboard

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEFAULT_OUTPUT = PROJECT_ROOT / "dashboard" / "data.js"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Read the command line options.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    argparse.Namespace
        Options: env, days, output and usd_brl.
    """
    parser = argparse.ArgumentParser(
        description="Build the Langfuse token and cost dashboard data.",
    )
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="Path of the .env file.")
    parser.add_argument(
        "--days", type=int, default=30, help="Length of the window, in days (1 to 90)."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write the data file."
    )
    parser.add_argument(
        "--usd-brl",
        type=float,
        default=None,
        help="Fixed exchange rate; skips the PTAX lookup.",
    )
    options = parser.parse_args(argv)
    if not 1 <= options.days <= 90:
        parser.error("--days deve estar entre 1 e 90.")
    return options


def collect(
    client: LangfuseClient,
    days: int,
    usd_brl: float,
    rate_date: str | None,
    now: datetime,
) -> dict:
    """Run every query of the dashboard and build its data.

    Parameters
    ----------
    client : LangfuseClient
        Client of the Langfuse project.
    days : int
        Length of the window, in days.
    usd_brl : float
        Exchange rate, reais per dollar.
    rate_date : str | None
        Date of the exchange rate.
    now : datetime
        Reference moment, timezone aware.

    Returns
    -------
    dict
        Data of the dashboard.
    """
    start_text, end_text = queries.window(now, days)
    start = datetime.strptime(start_text, "%Y-%m-%dT%H:%M:%SZ").date()
    end = now.date()
    return build_dashboard(
        totals=(client.metrics(queries.totals(start_text, end_text)) or [{}])[0],
        models=client.metrics(queries.by_model(start_text, end_text)),
        daily=client.metrics(queries.daily(start_text, end_text)),
        operations=client.metrics(queries.latency_by_operation(start_text, end_text)),
        users=client.metrics(queries.cost_by_user(start_text, end_text)),
        usd_brl=usd_brl,
        rate_date=rate_date,
        start=start,
        end=end,
        generated_at=now,
    )


def write_data(data: dict, output: Path) -> None:
    """Write the data as a JavaScript file, so the page works opened from disk.

    Parameters
    ----------
    data : dict
        Data of the dashboard.
    output : Path
        Destination file.

    Returns
    -------
    None
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    output.write_text(f"window.DASHBOARD_DATA = {body};\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Collect the data and write the dashboard file.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    int
        0 on success, 1 when a service cannot be used.
    """
    options = parse_args(argv)
    try:
        settings = load_settings(options.env)
    except KeyError as error:
        print(f"Variáveis ausentes no .env: {error.args[0]}")
        return 1
    now = datetime.now(timezone.utc)
    try:
        if options.usd_brl is not None:
            usd_brl, rate_date = options.usd_brl, None
        else:
            usd_brl, rate_date = latest_usd_sell_rate(now.date())
        data = collect(LangfuseClient(settings), options.days, usd_brl, rate_date, now)
    except (LangfuseError, ExchangeRateError) as error:
        print(str(error))
        return 1
    write_data(data, options.output)
    totals = data["totals"]
    print(
        f"Dados gravados em {options.output} "
        f"({totals['calls']} chamadas, R$ {totals['cost_brl']:.2f})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
