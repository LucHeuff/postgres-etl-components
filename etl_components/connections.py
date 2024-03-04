import sqlite3
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Union

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row

config = dotenv_values(".env")


SQLITE_INSERT_FORMAT = """
    INSERT INTO <table> (<column1>, <column2>, ...)
    VALUES (:<column1_source>, :<column2_source>, ...)
"""
SQLITE_VALUES_FORMAT = r":(\w+)"


POSTGRES_INSERT_FORMAT = """
    INSERT INTO <table> (<column1>, <column2>, ...)
    VALUES (%(<column1_source>)s, %(<column2_source>)s, ...)
"""
POSTGRES_VALUES_FORMAT = r"%\((\w+)\)s"
POSTGRES_COPY_FORMAT = """
    COPY <table> (<column1_source>, <column2_source>, ...)
(FROM is not necessary, this is taken care of for you 😊)
"""

# SQLite and PostgreSQL use the same format for retrieval
RETRIEVE_FORMAT = """
    SELECT id as <table>_id, <column1> as <alias1>, <column2> FROM <table>
"""
COMPARE_FORMAT = """
    SELECT 
        <table>.<column> as <alias>,
        <table>.<column>,
        <column>,
        ...
    FROM <table>
        JOIN <other_table> ON <other_table>.<table>_id = <table>.id
        JOIN ...
    ...
"""
NO_COPY_FORMAT = "COPY not available for this cursor."


@dataclass
class SQLFormat:
    """Stores formats and patterns of SQL queries."""

    insert_format: str
    values_pattern: str
    copy_available: bool
    copy_format: str
    retrieve_format: str = RETRIEVE_FORMAT
    compare_format: str = COMPARE_FORMAT


@dataclass
class SQLiteFormat(SQLFormat):
    """Format for SQLite interactions."""

    def __init__(self) -> None:
        """Add insert_format and values_format."""
        super().__init__(
            insert_format=SQLITE_INSERT_FORMAT,
            values_pattern=SQLITE_VALUES_FORMAT,
            copy_available=False,
            copy_format=NO_COPY_FORMAT,
        )


@dataclass
class PostgresFormat(SQLFormat):
    """Format for Postgres interactions."""

    def __init__(self) -> None:
        """Add insert_format and values_format."""
        super().__init__(
            insert_format=POSTGRES_INSERT_FORMAT,
            values_pattern=POSTGRES_VALUES_FORMAT,
            copy_available=True,
            copy_format=POSTGRES_COPY_FORMAT,
        )


Cursor = sqlite3.Cursor | psycopg.Cursor


def get_sql_format(cursor: Cursor) -> SQLFormat:
    """Get formats for this cursor.

    Essentially a helper function that figures out what database dialect this
    cursor belongs to and returns the corresponding formats.

    Args:
    ----
        cursor: active cursor

    Returns:
    -------
        SQLFormat

    """
    if isinstance(cursor, sqlite3.Cursor):
        return SQLiteFormat()
    if isinstance(cursor, psycopg.Cursor):
        return PostgresFormat()
    return None


def _dict_row(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict:
    """Row Factory that converts SQLite output into dictionaries.

    Args:
    ----
        cursor: SQLite cursor
        row: data row output

    Returns:
    -------
        data in dictionary format.

    """
    r = sqlite3.Row(cursor, row)
    return dict(zip(r.keys(), tuple(r)))


class SQLiteCursor:
    """Context manager for handling connections with PostgreSQL server.

    Assumes the following variables are set in .env:
        SQLITE_DB: filename to sqlite DB. If not available, defaults to in memory db.
    """

    def __init__(self, db: Union[str, None] = None) -> None:
        """Create a connection to SQLite database.

        Args:
        ----
            db: filename of SQLite database. If None, creates database in memory. (default: None)

        """
        db = ":memory:" if db is None else db
        self.connection = sqlite3.connect(db)
        self.connection.row_factory = _dict_row

    def __enter__(self) -> sqlite3.Cursor:
        """Enter by creating a cursor to interact with the SQLite database.

        Returns
        -------
            sqlite3 cursor.

        """
        return self.connection.cursor()

    def __exit__(
        self, exception: Exception, message: str, traceback: TracebackType
    ) -> None:
        """Exit by commiting and closing the connection, or rolling back on exception.

        Args:
        ----
            exception: raised exception in the context manager
            message: message the exception is raised with
            traceback: traceback for the exception

        Raises:
        ------
            RollbackCausedError: when an exception occurs within the context.

        """
        if exception:
            self.connection.rollback()
            self.connection.close()
        else:
            self.connection.commit()
            self.connection.close()


class PostgresCursor:
    """Context manager for handling connections with PostgreSQL server.

    Assumes the following variables are set in .env:
        HOST: database host ip to PostgreSQL server
        PORT: port to which PostgreSQL server listens (usually 5432)
        DB: name of database to connect to
        USER: username that has right on database
        PASSWORD: to authenticate user

    Attributes
    ----------
        connection: connection with the server, using dict_row row factory.

    """

    def __init__(self) -> None:
        """Create a connection with the PostgreSQL server."""
        host = config["HOST"]
        port = config["PORT"]
        database = config["DB"]
        user = config["USER"]
        password = config["PASSWORD"]

        credentials = f"dbname={database} user={user} password={password} host={host} port={port}"
        self.connection = psycopg.connect(credentials, row_factory=dict_row)

    def __enter__(self) -> psycopg.Cursor:
        """Enter by creating a cursor to interact with the PostgreSQL server.

        Returns
        -------
            psycopg cursor.

        """
        return self.connection.cursor()

    def __exit__(
        self, exception: Exception, message: str, traceback: TracebackType
    ) -> None:
        """Exit by commiting and closing the connection, or rolling back on exception.

        Args:
        ----
            exception: raised exception in the context manager
            message: message the exception is raised with
            traceback: traceback for the exception

        Raises:
        ------
            RollbackCausedError: when an exception occurs within the context.

        """
        if exception:
            self.connection.rollback()
            self.connection.close()
        else:
            self.connection.commit()
            self.connection.close()
