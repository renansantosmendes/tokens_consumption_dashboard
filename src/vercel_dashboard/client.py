"""Read-only client of the Vercel REST API."""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from vercel_dashboard.settings import VercelSettings

API_URL = "https://api.vercel.com"
PROJECTS_PATH = "/v10/projects"
DEPLOYMENTS_PATH = "/v7/deployments"
CHARGES_PATH = "/v1/billing/charges"
PAGE_SIZE = 100
MAX_PAGES = 10
REQUEST_TIMEOUT_SECONDS = 60

Opener = Callable[..., Any]


class VercelError(RuntimeError):
    """The Vercel API answered with an error or could not be reached."""


def _items(payload: Any, key: str) -> list[dict[str, Any]]:
    """Find the list of items in a Vercel answer.

    Parameters
    ----------
    payload : Any
        Decoded JSON answer, a list or an object with the list under ``key``.
    key : str
        Name of the field that holds the list inside an object answer.

    Returns
    -------
    list[dict[str, Any]]
        The items that are objects; empty when the answer has no list.
    """
    if isinstance(payload, dict):
        payload = payload.get(key)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


class VercelClient:
    """Reads projects, deployments and billing charges from Vercel.

    Parameters
    ----------
    settings : VercelSettings
        Token and team of the Vercel account.
    opener : Callable[..., Any]
        Function that performs HTTP requests, replaceable in tests.
    """

    def __init__(
        self,
        settings: VercelSettings,
        opener: Opener = urllib.request.urlopen,
    ) -> None:
        self._settings = settings
        self._opener = opener

    def _read(self, path: str, params: dict[str, Any]) -> bytes:
        """Perform one GET request and return the raw body.

        Parameters
        ----------
        path : str
            Endpoint path, such as ``/v10/projects``.
        params : dict[str, Any]
            Query parameters; the team id is added when configured.

        Returns
        -------
        bytes
            Body of the answer.

        Raises
        ------
        VercelError
            When the request fails or the server cannot be reached.
        """
        query = dict(params)
        if self._settings.team_id:
            query["teamId"] = self._settings.team_id
        url = f"{API_URL}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._settings.token}",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise VercelError(
                f"A Vercel respondeu com status {error.code} em {path}."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise VercelError("Não foi possível conectar à Vercel.") from error

    def _read_json(self, path: str, params: dict[str, Any]) -> Any:
        """Perform one GET request and decode the JSON answer.

        Parameters
        ----------
        path : str
            Endpoint path.
        params : dict[str, Any]
            Query parameters.

        Returns
        -------
        Any
            Decoded JSON answer.

        Raises
        ------
        VercelError
            When the answer is not valid JSON.
        """
        try:
            return json.loads(self._read(path, params))
        except ValueError as error:
            raise VercelError(f"Resposta inválida da Vercel em {path}.") from error

    def projects(self) -> list[dict[str, Any]]:
        """List the projects of the account or team, one page of up to 100.

        Returns
        -------
        list[dict[str, Any]]
            Projects with id, name, framework and update time.
        """
        payload = self._read_json(PROJECTS_PATH, {"limit": PAGE_SIZE})
        return _items(payload, "projects")

    def deployments(self, since_ms: int) -> list[dict[str, Any]]:
        """List the deployments created since a moment, following the pages.

        Parameters
        ----------
        since_ms : int
            Start of the window, in milliseconds since the epoch.

        Returns
        -------
        list[dict[str, Any]]
            Deployments, newest first, up to ``MAX_PAGES`` pages.
        """
        collected: list[dict[str, Any]] = []
        until = None
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"since": since_ms, "limit": PAGE_SIZE}
            if until is not None:
                params["until"] = until
            payload = self._read_json(DEPLOYMENTS_PATH, params)
            collected.extend(_items(payload, "deployments"))
            pagination = payload.get("pagination") if isinstance(payload, dict) else None
            next_until = pagination.get("next") if isinstance(pagination, dict) else None
            if not next_until or next_until == until:
                break
            until = next_until
        return collected

    def charges(self, start: str, end: str) -> str:
        """Download the billing charges of a period, in FOCUS JSON lines.

        Parameters
        ----------
        start : str
            Start of the period, ISO 8601 in UTC.
        end : str
            End of the period, ISO 8601 in UTC.

        Returns
        -------
        str
            Raw text with one JSON charge per line.

        Raises
        ------
        VercelError
            When the account cannot read the billing, such as a member without
            the billing role, or the request fails.
        """
        raw = self._read(CHARGES_PATH, {"from": start, "to": end})
        return raw.decode("utf-8")
