"""Local server that shows the conversations of the students, read on demand."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from dashboard.conversations import detail, summarize
from dashboard.langfuse_client import LangfuseClient, LangfuseError
from dashboard.settings import load_settings
from dashboard.students import StudentsError, fetch_student_names, load_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "dashboard"
DEFAULT_ENV = PROJECT_ROOT / ".env_proxy"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_LIMIT = 100
MAX_DAYS = 90
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


class ViewerState:
    """Connections shared by the request handlers.

    Parameters
    ----------
    client : LangfuseClient
        Client of the proxy's Langfuse project.
    student_names : dict[str, str]
        Name of each registration number.
    """

    def __init__(self, client: LangfuseClient, student_names: dict[str, str]) -> None:
        self.client = client
        self.student_names = student_names


def list_conversations(
    state: ViewerState,
    days: int,
    user: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Recent generations, newest first, optionally of one user.

    Parameters
    ----------
    state : ViewerState
        Connections of the viewer.
    days : int
        Length of the window, in days.
    user : str | None
        Registration number to filter by; None lists every user.
    limit : int
        Maximum number of conversations.

    Returns
    -------
    list[dict[str, Any]]
        One summary per generation.
    """
    now = datetime.now(timezone.utc)
    params: dict[str, Any] = {
        "fromStartTime": (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "toStartTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": "GENERATION",
        "fields": "core,basic,io",
        "limit": limit,
    }
    if user:
        params["userId"] = user
    rows = state.client.observations(params)
    return [summarize(row, state.student_names) for row in rows]


def get_conversation(state: ViewerState, observation_id: str) -> dict[str, Any] | None:
    """Full conversation of one generation.

    Parameters
    ----------
    state : ViewerState
        Connections of the viewer.
    observation_id : str
        Id of the generation.

    Returns
    -------
    dict[str, Any] | None
        Messages and answer, or None when the generation is not found.
    """
    params = {"observationId": observation_id, "fields": "core,io", "limit": 1}
    rows = state.client.observations(params)
    return detail(rows[0]) if rows else None


def make_handler(state: ViewerState) -> type[BaseHTTPRequestHandler]:
    """Build the request handler bound to the viewer state.

    Parameters
    ----------
    state : ViewerState
        Connections of the viewer.

    Returns
    -------
    type[BaseHTTPRequestHandler]
        Handler class for the HTTP server.
    """

    class Handler(BaseHTTPRequestHandler):
        """Serves the static page and the two JSON routes."""

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            """Send one complete response.

            Parameters
            ----------
            status : int
                HTTP status code.
            content_type : str
                Value of the Content-Type header.
            body : bytes
                Response body.

            Returns
            -------
            None
            """
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            """Send a JSON response.

            Parameters
            ----------
            status : int
                HTTP status code.
            payload : Any
                Value to encode as JSON.

            Returns
            -------
            None
            """
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, "application/json; charset=utf-8", body)

        def do_GET(self) -> None:  # noqa: N802
            """Route a GET request to the static page or to the JSON API.

            Returns
            -------
            None
            """
            parts = urlsplit(self.path)
            query = {key: values[0] for key, values in parse_qs(parts.query).items()}
            try:
                if parts.path == "/api/conversations":
                    days = min(max(int(query.get("days", 30)), 1), MAX_DAYS)
                    limit = min(max(int(query.get("limit", 50)), 1), MAX_LIMIT)
                    rows = list_conversations(state, days, query.get("user") or None, limit)
                    self._json(200, rows)
                elif parts.path == "/api/conversation":
                    found = get_conversation(state, query.get("id", ""))
                    if found:
                        self._json(200, found)
                    else:
                        self._json(404, {"error": "Conversa não encontrada."})
                else:
                    self._static(parts.path)
            except LangfuseError as error:
                self._json(502, {"error": str(error)})
            except ValueError:
                self._json(400, {"error": "Parâmetro inválido."})

        def _static(self, path: str) -> None:
            """Serve a file of the dashboard folder.

            Parameters
            ----------
            path : str
                Request path.

            Returns
            -------
            None
            """
            name = "conversas.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC_DIR / name).resolve()
            if STATIC_DIR.resolve() not in target.parents or not target.is_file():
                self._json(404, {"error": "Não encontrado."})
                return
            content_type = STATIC_TYPES.get(target.suffix, "application/octet-stream")
            self._send(200, content_type, target.read_bytes())

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Keep the server quiet.

            Parameters
            ----------
            format : str
                Log format, not used.
            *args : Any
                Log arguments, not used.

            Returns
            -------
            None
            """

    return Handler


def build_state(env_path: Path) -> ViewerState:
    """Create the viewer connections from the proxy .env file.

    Parameters
    ----------
    env_path : Path
        .env file with the Langfuse keys and the database URL of the proxy.

    Returns
    -------
    ViewerState
        Connections ready to serve requests; names are empty if the database fails.
    """
    client = LangfuseClient(load_settings(env_path))
    try:
        names = fetch_student_names(load_database_url(env_path))
    except StudentsError as error:
        print(f"Aviso: {error} Os nomes não serão exibidos.")
        names = {}
    return ViewerState(client, names)


def main(argv: list[str] | None = None) -> int:
    """Start the local viewer on 127.0.0.1.

    Parameters
    ----------
    argv : list[str] | None
        Arguments without the program name; None reads ``sys.argv``.

    Returns
    -------
    int
        0 when the server stops normally, 1 when the settings cannot be read.
    """
    parser = argparse.ArgumentParser(description="Local viewer of the student conversations.")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="Proxy .env file.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port on 127.0.0.1.")
    options = parser.parse_args(argv)
    try:
        state = build_state(options.env)
    except (KeyError, FileNotFoundError) as error:
        print(f"Erro ao ler {options.env.name}: {error}")
        return 1
    server = ThreadingHTTPServer((HOST, options.port), make_handler(state))
    print(f"Visualizador em http://{HOST}:{options.port}/ (Ctrl+C para parar)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
