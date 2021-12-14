# -*- coding: utf-8 -*-

import logging, time
from psycopg2 import sql

from .db_control import DBControl
from .config import Config


###
# access statistics
###

def get_access_statistics(db_instance : DBControl):
    result = db_instance.fetch_all(
            sql.SQL(
                """
                SELECT timestamp FROM {i_access_statistics_table}
                """
                ).format(
                    i_access_statistics_table=sql.Identifier(Config().database.get("access_statistics_table"))))
    return [ row['timestamp'] for row in result ]


def add_to_access_statistics(db_instance : DBControl, session_id : str):
    if db_instance and session_id:
        try:
            db_instance.edit_database(
                    sql.SQL(
                        """
                        INSERT INTO {i_access_statistics_table}
                            VALUES ({p_session_id}, {p_timestamp})
                            ON CONFLICT (session_id) DO UPDATE SET timestamp={p_timestamp}
                        """
                        ).format(
                            i_access_statistics_table=sql.Identifier(Config().database.get("access_statistics_table")),
                            p_session_id=sql.Placeholder(name='session_id'),
                            p_timestamp=sql.Placeholder(name='timestamp')),
                        { 'session_id':session_id, "timestamp":int(time.time()) })
        except DBControl.DatabaseError as e:
            logging.warning(
                    "add to statistics failed for session id {}. Error: {}".format(session_id, e))

