"""Command that collects the Vercel data and writes the dashboard file."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from vercel_dashboard.billing import parse_charges
from vercel_dashboard.client import VercelClient, VercelError
from vercel_dashboard.settings import load_vercel_settings
from vercel_dashboard.summary import build_vercel_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEFAULT_OUTPUT = PROJECT_ROOT / "vercel" / "data.js"
MAX_DAYS = 90


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Read the command line options.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    argparse.Namespace
        Options: env, days and output.
    """
    parser = argparse.ArgumentParser(
        description="Build the data of the Vercel applications dashboard.",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=DEFAULT_ENV,
        help=".env file with VERCEL_TOKEN and, optionally, VERCEL_TEAM_ID.",
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Length of the window, in days (1 to 90)."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write the data file."
    )
    options = parser.parse_args(argv)
    if not 1 <= options.days <= MAX_DAYS:
        parser.error("--days deve estar entre 1 e 90.")
    return options


def read_charges(
    client: VercelClient,
    start: datetime,
    end: datetime,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Read the billing charges, without failing the whole collection.

    Parameters
    ----------
    client : VercelClient
        Client of the Vercel account.
    start : datetime
        Start of the window, timezone aware.
    end : datetime
        End of the window, timezone aware.

    Returns
    -------
    tuple[list[dict[str, Any]] | None, str | None]
        Parsed charges and None, or None and the reason why they failed.
    """
    try:
        text = client.charges(_iso(start), _iso(end))
    except VercelError as error:
        return None, str(error)
    return parse_charges(text), None


def _iso(moment: datetime) -> str:
    """Format a moment as ISO 8601 in UTC, with a Z suffix.

    Parameters
    ----------
    moment : datetime
        Moment, timezone aware.

    Returns
    -------
    str
        Text such as ``2026-11-01T00:00:00Z``.
    """
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_data(data: dict[str, Any], output: Path) -> None:
    """Write the data as a JavaScript file, so the page works opened from disk.

    Parameters
    ----------
    data : dict[str, Any]
        Data of the dashboard.
    output : Path
        Destination file.

    Returns
    -------
    None
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    output.write_text(f"window.VERCEL_DATA = {body};\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Collect the Vercel data and write the dashboard file.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    int
        0 on success, 1 when the settings or the projects cannot be read.
    """
    options = parse_args(argv)
    try:
        client = VercelClient(load_vercel_settings(options.env))
    except (KeyError, FileNotFoundError) as error:
        print(f"Erro ao ler a configuração da Vercel: {error}")
        return 1
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=options.days)
    try:
        projects = client.projects()
        deployments = client.deployments(int(start.timestamp() * 1000))
    except VercelError as error:
        print(str(error))
        return 1
    charges, charges_error = read_charges(client, start, now)
    data = build_vercel_data(
        projects=projects,
        deployments=deployments,
        charges=charges,
        charges_error=charges_error,
        start=start.date(),
        end=now.date(),
        generated_at=now,
    )
    write_data(data, options.output)
    summary = data["summary"]
    print(
        f"Dados gravados em {options.output}: {summary['applications']} aplicações, "
        f"{summary['deploys']} deploys no período."
    )
    if charges_error:
        print(f"Aviso: cobrança não lida ({charges_error})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
