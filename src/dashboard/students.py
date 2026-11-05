"""Reads the names of the students from the proxy database (read only)."""

from pathlib import Path

import psycopg
from dotenv import dotenv_values

DATABASE_URL_KEY = "NEON_DATABASE_URL"
STUDENTS_QUERY = (
    "SELECT registration_number, full_name FROM pgl_proxy.students "
    "WHERE full_name IS NOT NULL"
)
CONNECT_TIMEOUT_SECONDS = 15


class StudentsError(RuntimeError):
    """The student names could not be read from the database."""


def load_database_url(env_path: Path) -> str:
    """Read the database connection URL from a .env file.

    Parameters
    ----------
    env_path : Path
        .env file that defines the database URL.

    Returns
    -------
    str
        Connection URL of the database.

    Raises
    ------
    StudentsError
        When the file does not define the database URL.
    """
    url = dotenv_values(env_path).get(DATABASE_URL_KEY)
    if not url:
        raise StudentsError(f"{DATABASE_URL_KEY} não está definido em {env_path.name}.")
    return str(url)


def fetch_student_names(database_url: str) -> dict[str, str]:
    """Read the name of each student, by registration number.

    The connection is opened in read-only mode, so this code cannot change the
    database.

    Parameters
    ----------
    database_url : str
        Connection URL of the database.

    Returns
    -------
    dict[str, str]
        Full name of each registration number.

    Raises
    ------
    StudentsError
        When the database cannot be reached or the query fails.
    """
    try:
        with psycopg.connect(
            database_url,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            options="-c default_transaction_read_only=on",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(STUDENTS_QUERY)
                return {str(number): str(name) for number, name in cursor.fetchall()}
    except psycopg.Error as error:
        raise StudentsError("Não foi possível ler os nomes no banco.") from error
