"""Settings of the Vercel API read from a local .env file."""

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

TOKEN_KEY = "VERCEL_TOKEN"
TEAM_KEY = "VERCEL_TEAM_ID"


@dataclass(frozen=True)
class VercelSettings:
    """Connection data of the Vercel account or team.

    Parameters
    ----------
    token : str
        Access token created in the Vercel account settings.
    team_id : str | None
        Team id when the projects belong to a team; None for a personal account.
    """

    token: str
    team_id: str | None


def load_vercel_settings(env_path: Path) -> VercelSettings:
    """Read the Vercel settings from a .env file.

    Parameters
    ----------
    env_path : Path
        Path of the .env file.

    Returns
    -------
    VercelSettings
        Token and optional team id.

    Raises
    ------
    KeyError
        When VERCEL_TOKEN is missing or empty.
    """
    values = dotenv_values(env_path)
    token = values.get(TOKEN_KEY)
    if not token:
        raise KeyError(TOKEN_KEY)
    team = values.get(TEAM_KEY)
    return VercelSettings(token=str(token), team_id=str(team) if team else None)
