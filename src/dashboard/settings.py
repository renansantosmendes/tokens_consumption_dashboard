"""Settings read from the local .env file."""

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

HOST_KEYS = ("LANGFUSE_HOST", "LANGFUSE_BASE_URL")
REQUIRED_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


@dataclass(frozen=True)
class Settings:
    """Connection data of the Langfuse project.

    Parameters
    ----------
    host : str
        Base URL of the Langfuse instance, without a trailing slash.
    public_key : str
        Public key of the project, used as the user of the basic authentication.
    secret_key : str
        Secret key of the project, used as the password of the basic authentication.
    """

    host: str
    public_key: str
    secret_key: str


def load_settings(env_path: Path) -> Settings:
    """Read the Langfuse settings from a .env file.

    Parameters
    ----------
    env_path : Path
        Path of the .env file.

    Returns
    -------
    Settings
        Langfuse connection data.

    Raises
    ------
    KeyError
        When one of the required variables is missing or empty.
    """
    values = dotenv_values(env_path)
    host = next((values.get(key) for key in HOST_KEYS if values.get(key)), None)
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if not host:
        missing.insert(0, " ou ".join(HOST_KEYS))
    if missing:
        raise KeyError(", ".join(missing))
    return Settings(
        host=str(host).rstrip("/"),
        public_key=str(values["LANGFUSE_PUBLIC_KEY"]),
        secret_key=str(values["LANGFUSE_SECRET_KEY"]),
    )
