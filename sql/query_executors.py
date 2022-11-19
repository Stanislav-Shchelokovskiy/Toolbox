import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterable, Optional, Union

from pandas import DataFrame, read_sql
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, Transaction
from toolbox.sql.sql_query import SqlQuery
from toolbox.sql.sqlite_data_base import get_or_create_db
from toolbox.logger import Logger


_engine = None


def _get_or_create_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(ConnectionParams().get_url())
    return _engine


class ConnectionParams:

    def __init__(
        self,
        user_env: str = 'SQL_USER',
        password_env: str = 'SQL_PASSWORD',
        server_env: str = 'SQL_SERVER',
        data_base_env: str = 'SQL_DATABASE',
    ):
        self.user = os.environ[user_env]
        self.password = os.environ[password_env]
        self.server = os.environ[server_env]
        self.data_base = os.environ[data_base_env]

    def get_url(self):
        return (
            'mssql+pyodbc://' + self.user + ':' + self.password + '@'
            + self.server + '/' + self.data_base
            + '?driver=ODBC Driver 17 for SQL Server'
        )


class ConnectionObject:

    def __get_or_create_engine(self) -> Engine:
        return _get_or_create_engine()

    def begin_transaction(self) -> Transaction:
        return self.__get_or_create_engine().begin()


class SqlQueryExecutorBase(ABC):
    """
    Executes and sql query passed to the execute method.
    """

    @abstractmethod
    def execute(
        self,
        sql_query: SqlQuery,
        kwargs: Dict[str, Any],
    ) -> Union[DataFrame, str, None]:
        pass

    def execute_many(
        self,
        prep_queries: Iterable[SqlQuery],
        main_query: SqlQuery,
        main_query_read_kwargs: Dict[str, Any] = {},
    ) -> Union[DataFrame, str]:
        pass

    def execute_many_main_queries(
        self,
        prep_queries: Iterable[SqlQuery],
        main_queries: Dict[str, SqlQuery],
        main_query_read_kwargs: Dict[str, Any] = {},
    ) -> Dict[str, Union[DataFrame, str]]:
        pass

    def _execute_sql_query(
        self,
        sql_query: SqlQuery,
        connection: Any,
        kwargs: Dict[str, Any],
    ) -> Union[DataFrame, str]:
        return read_sql(
            sql=sql_query.get_query(),
            con=connection,
            **kwargs,
        )


class SqlQueryExecutor(SqlQueryExecutorBase):

    def begin_transaction(self):
        return ConnectionObject().begin_transaction()

    def _execute_query_func(self, func: Callable[[Connection], Any]):
        with self.begin_transaction() as transaction:
            res = func(transaction)
        return res

    def execute(
        self,
        sql_query: SqlQuery,
        kwargs: Dict[str, Any] = {},
    ) -> DataFrame:

        def func(conn: Connection):
            return self._execute_sql_query(
                sql_query=sql_query,
                connection=conn,
                kwargs=kwargs,
            )

        return self._execute_query_func(func=func)

    def _execute_prep_queries(
        self,
        prep_queries: Iterable[SqlQuery],
        conn: Connection,
    ):
        for sql_query in prep_queries:
            Logger.debug(sql_query._query_file_path)
            conn.execute(sql_query.get_query())

    def execute_many(
        self,
        prep_queries: Iterable[SqlQuery],
        main_query: SqlQuery,
        main_query_read_kwargs: Dict[str, Any] = {},
    ) -> DataFrame:

        def func(conn: Connection):
            self._execute_prep_queries(prep_queries, conn)
            Logger.debug(main_query._query_file_path)
            return self._execute_sql_query(
                sql_query=main_query,
                connection=conn,
                kwargs=main_query_read_kwargs,
            )

        return self._execute_query_func(func=func)

    def execute_many_main_queries(
        self,
        prep_queries: Iterable[SqlQuery],
        main_queries: Dict[str, SqlQuery],
        main_query_read_kwargs: Dict[str, Any] = {},
    ) -> Dict[str, DataFrame]:

        def func(conn: Connection):
            self._execute_prep_queries(prep_queries, conn)
            res = {}
            for k, v in main_queries.items():
                Logger.debug(f'{k} : {v._query_file_path}')
                res[k] = self._execute_sql_query(
                    sql_query=v,
                    connection=conn,
                    kwargs=main_query_read_kwargs,
                )
            return res

        return self._execute_query_func(func=func)

    def _execute_sql_query(
        self,
        sql_query: SqlQuery,
        connection: Connection,
        kwargs: Dict[str, Any],
    ) -> DataFrame:
        return read_sql(
            sql=sql_query.get_query(),
            con=connection,
            **kwargs,
        )


class SqlPostQueryExecutor(SqlQueryExecutor):

    def execute(
        self,
        sql_query: SqlQuery,
        kwargs: Dict[str, Any] = None,
    ) -> str:

        def func(conn: Connection):
            self._execute_prep_queries(
                prep_queries=[sql_query],
                conn=conn,
            )

        self._execute_query_func(func=func)

    def execute_many(
        self,
        prep_queries: Iterable[SqlQuery],
        main_query: SqlQuery = None,
        main_query_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:

        def func(conn: Connection):
            self._execute_prep_queries(
                prep_queries=prep_queries,
                conn=conn,
            )

        self._execute_query_func(func=func)

    def execute_many_main_queries(
        self,
        prep_queries: Iterable[SqlQuery],
        main_queries: Dict[str, SqlQuery],
        main_query_read_kwargs: Dict[str, Any] = {},
    ) -> Dict[str, Union[DataFrame, str]]:
        raise NotImplementedError()


class JsonMSSqlReadQueryExecutor(SqlQueryExecutor):

    def _execute_sql_query(
        self,
        sql_query: SqlQuery,
        connection: Connection,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> str:
        res_raw = connection.execute(
            sql_query.get_query() + '\r\nFOR JSON AUTO, INCLUDE_NULL_VALUES'
        )
        res_json = ''.join(row[0] for row in res_raw.fetchall())
        return res_json


class SQLiteQueryExecutor(SqlQueryExecutorBase):

    def __init__(
        self,
        data_base: str = None,
    ):
        self.data_base = get_or_create_db(name=data_base)

    def execute(
        self,
        sql_query: SqlQuery,
        source_tables: Dict[str, DataFrame],
        kwargs: Dict[str, Any] = {},
    ) -> DataFrame:
        self.data_base.try_connect()
        self.data_base.save_tables(source_tables)

        query_result = self._execute_sql_query(
            sql_query=sql_query,
            connection=self.data_base.get_connection(),
            kwargs=kwargs,
        )

        self.data_base.try_disconnect()
        return query_result
