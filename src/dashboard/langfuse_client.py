"""Client of the Langfuse public API v2 (aggregated metrics)."""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from dashboard.settings import Settings

Opener = Callable[..., Any]
REQUEST_TIMEOUT_SECONDS = 60


class LangfuseError(RuntimeError):
    """The Langfuse API answered with an error or could not be reached."""


class LangfuseClient:
    """Reads aggregated metrics from the Langfuse public API.

    Parameters
    ----------
    settings : Settings
        Connection data of the Langfuse project.
    opener : Callable[..., Any]
        Function that performs HTTP requests, replaceable in tests.
    """

    def __init__(self, settings: Settings, opener: Opener = urllib.request.urlopen) -> None:
        self._settings = settings
        self._opener = opener

    def _auth_header(self) -> str:
        """Build the basic authentication header of the project.

        Returns
        -------
        str
            Value of the Authorization header.
        """
        token = f"{self._settings.public_key}:{self._settings.secret_key}".encode()
        return "Basic " + base64.b64encode(token).decode("ascii")

    def metrics(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Run one aggregated query on the observations.

        Parameters
        ----------
        query : dict[str, Any]
            Query in the format of the ``/api/public/v2/metrics`` endpoint.

        Returns
        -------
        list[dict[str, Any]]
            Rows of the answer, one per group.

        Raises
        ------
        LangfuseError
            When the request fails or the answer is not in the expected format.
        """
        encoded = urllib.parse.quote(json.dumps(query))
        url = f"{self._settings.host}/api/public/v2/metrics?query={encoded}"
        request = urllib.request.Request(url, headers={"Authorization": self._auth_header()})
        try:
            with self._opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise LangfuseError(f"Langfuse respondeu com status {error.code}.") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise LangfuseError("Não foi possível conectar ao Langfuse.") from error
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise LangfuseError("Resposta inesperada do Langfuse.")
        return rows

    def observations(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Read generations with their input and output from the v2 observations API.

        Parameters
        ----------
        params : dict[str, Any]
            Query parameters, such as the time window, the user and the limit.

        Returns
        -------
        list[dict[str, Any]]
            Observations in the answer, newest first.

        Raises
        ------
        LangfuseError
            When the request fails or the answer is not in the expected format.
        """
        query = urllib.parse.urlencode(params)
        url = f"{self._settings.host}/api/public/v2/observations?{query}"
        request = urllib.request.Request(url, headers={"Authorization": self._auth_header()})
        try:
            with self._opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise LangfuseError(f"Langfuse respondeu com status {error.code}.") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise LangfuseError("Não foi possível conectar ao Langfuse.") from error
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise LangfuseError("Resposta inesperada do Langfuse.")
        return rows
