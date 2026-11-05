"""Command that collects the Langfuse metrics of each project and writes the dashboard data."""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dashboard import queries
from dashboard.exchange import ExchangeRateError, latest_usd_sell_rate
from dashboard.langfuse_client import LangfuseClient, LangfuseError
from dashboard.merge import merge_raw
from dashboard.settings import load_settings
from dashboard.students import StudentsError, fetch_student_names, load_database_url
from dashboard.summary import build_dashboard

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = (
    ("agente", PROJECT_ROOT / ".env"),
    ("proxy", PROJECT_ROOT / ".env_proxy"),
)
DEFAULT_OUTPUT = PROJECT_ROOT / "dashboard" / "data.js"


@dataclass(frozen=True)
class Source:
    """One Langfuse project to collect from.

    Parameters
    ----------
    label : str
        Name shown in the dashboard, such as ``proxy``.
    env_path : Path
        .env file with the keys of that project.
    """

    label: str
    env_path: Path


def parse_source(text: str) -> Source:
    """Read a ``ROTULO=CAMINHO`` source given on the command line.

    Parameters
    ----------
    text : str
        Text in the form ``ROTULO=CAMINHO_DO_ENV``.

    Returns
    -------
    Source
        The parsed source.

    Raises
    ------
    argparse.ArgumentTypeError
        When the text does not have the form ``ROTULO=CAMINHO``.
    """
    label, sep, path = text.partition("=")
    if not sep or not label or not path:
        raise argparse.ArgumentTypeError("use o formato ROTULO=CAMINHO_DO_ENV")
    return Source(label=label, env_path=Path(path))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Read the command line options.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    argparse.Namespace
        Options: source, days, output and usd_brl.
    """
    parser = argparse.ArgumentParser(
        description="Build the Langfuse token and cost dashboard data from one or more projects.",
    )
    parser.add_argument(
        "--source",
        type=parse_source,
        action="append",
        default=None,
        help="Project to collect, as ROTULO=CAMINHO_DO_ENV. Repeat for more projects. "
        "Default: agente=.env and proxy=.env_proxy.",
    )
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
    if options.source is None:
        options.source = [Source(label, path) for label, path in DEFAULT_SOURCES]
    if not 1 <= options.days <= 90:
        parser.error("--days deve estar entre 1 e 90.")
    return options


def collect_source(client: LangfuseClient, start: str, end: str) -> dict[str, Any]:
    """Run every query of the dashboard against one project.

    Parameters
    ----------
    client : LangfuseClient
        Client of the Langfuse project.
    start : str
        Start of the window, ISO timestamp.
    end : str
        End of the window, ISO timestamp.

    Returns
    -------
    dict[str, Any]
        Raw answers keyed by totals, models, daily, operations and users.
    """
    return {
        "totals": (client.metrics(queries.totals(start, end)) or [{}])[0],
        "models": client.metrics(queries.by_model(start, end)),
        "daily": client.metrics(queries.daily(start, end)),
        "operations": client.metrics(queries.latency_by_operation(start, end)),
        "users": client.metrics(queries.cost_by_user(start, end)),
    }


def load_names_or_warn(sources: list[Source]) -> dict[str, str]:
    """Read the student names from the first source that defines the database URL.

    Parameters
    ----------
    sources : list[Source]
        Projects, in order of preference.

    Returns
    -------
    dict[str, str]
        Name of each registration number; empty when no database can be read.
    """
    for source in sources:
        try:
            url = load_database_url(source.env_path)
        except StudentsError:
            continue
        try:
            return fetch_student_names(url)
        except StudentsError as error:
            print(f"Aviso: {error} Os nomes não serão exibidos.")
            return {}
    print("Aviso: nenhum .env define NEON_DATABASE_URL. Os nomes não serão exibidos.")
    return {}


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
    """Collect the data of every project and write the dashboard file.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    int
        0 on success, 1 when a project or a service cannot be used.
    """
    options = parse_args(argv)
    now = datetime.now(timezone.utc)
    start_text, end_text = queries.window(now, options.days)
    try:
        clients = [
            (source.label, LangfuseClient(load_settings(source.env_path)))
            for source in options.source
        ]
    except (KeyError, FileNotFoundError) as error:
        print(f"Erro ao ler o .env de um projeto: {error}")
        return 1
    try:
        if options.usd_brl is not None:
            usd_brl, rate_date = options.usd_brl, None
        else:
            usd_brl, rate_date = latest_usd_sell_rate(now.date())
        raw_sources = [
            collect_source(client, start_text, end_text) for _label, client in clients
        ]
    except (LangfuseError, ExchangeRateError) as error:
        print(str(error))
        return 1
    student_names = load_names_or_warn(options.source)
    data = build_dashboard(
        **merge_raw(raw_sources),
        sources=[label for label, _client in clients],
        student_names=student_names,
        usd_brl=usd_brl,
        rate_date=rate_date,
        start=datetime.strptime(start_text, "%Y-%m-%dT%H:%M:%SZ").date(),
        end=now.date(),
        generated_at=now,
    )
    write_data(data, options.output)
    totals = data["totals"]
    print(
        f"Dados gravados em {options.output} ({', '.join(data['sources'])}): "
        f"{totals['calls']} chamadas, R$ {totals['cost_brl']:.2f}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
