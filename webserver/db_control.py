#!/usr/bin/python
# -*- coding: utf-8 -*-

# python sql tutorial: http://initd.org/psycopg/docs/sql.html

import logging

import psycopg2
import psycopg2.extras
from psycopg2 import pool, sql

from . import constants
from .constants import ReturnCode
from .config import Config
from .helper import WebserverException


class DBControl():

    def __init__(self, map_id):
        if not map_id:
            raise WebserverException(
                    ReturnCode.MAP_LOADING_FAILED,
                    'No map id')
        elif map_id not in Config().maps.keys():
            raise WebserverException(
                    ReturnCode.MAP_LOADING_FAILED,
                    'Map not available')

        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                    1, 20,
                    host = Config().database.get("host_name"),
                    port = Config().database.get("port"),
                    user = Config().database.get("user"),
                    password = Config().database.get("password"),
                    database=map_id)
        except (Exception, psycopg2.DatabaseError) as error:
            raise WebserverException(
                    ReturnCode.MAP_LOADING_FAILED,
                    "Could not create database connection pool: {}".format(error))

        # create access statistics table, if it doesn't exist yet
        self.edit_database(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {i_access_statistics_table} (
                        session_id TEXT UNIQUE NOT NULL,
                        timestamp BIGINT NOT NULL)
                    """
                    ).format(
                        i_access_statistics_table=sql.Identifier(Config().database.get("access_statistics_table"))))

        # query map version and creation date from database
        map_info = self.fetch_one(
                sql.SQL(
                    """
                    SELECT version, created
                        FROM {i_map_info}
                        WHERE id = {p_map_id}
                    """
                    ).format(
                            i_map_info=sql.Identifier(Config().database.get("map_info")),
                            p_map_id=sql.Placeholder(name='map_id')),
                {'map_id':map_id})

        # version and creation date
        map_version = None
        try:
            if map_info.get("version") in constants.supported_map_version_list:
                map_version = map_info.get("version")
        except Exception as e:
            pass
        finally:
            if map_version:
                self.map_version = map_version
            else:
                raise WebserverException(
                        ReturnCode.MAP_LOADING_FAILED,
                        'The map {} is not compatible.\nMap version: {} not in {}'.format(
                            map_id, map_info.get("version"), constants.supported_map_version_list))
        # map creation
        map_created = None
        try:
            if map_info.get("created") > 1500000000000:
                map_created = map_info.get("created")
        except Exception as e:
            pass
        finally:
            if map_created:
                self.map_created = map_created
            else:
                raise WebserverException(
                        ReturnCode.MAP_LOADING_FAILED,
                        'Invalid creation date {} for map id {}'.format(
                            map_info.get("created"), map_id))


    def fetch_one(self, query, params={}):
        con = None
        row = None
        error = None
        try:
            con = self.connection_pool.getconn()
            cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(query, params)
            row = cursor.fetchone()
        except psycopg2.Error as e:
            logging.error(
                    'SQL single-row query: {} -- {}'.format(query, params))
            error = DBControl.DatabaseError(e)
        else:
            logging.getLogger("database").debug(
                    'SQL single-row query: {}'.format(cursor.query.decode("utf-8").strip()))
            if not row:
                error = DBControl.DatabaseResultEmptyError("No result for query")
        finally:
            if con:
                self.connection_pool.putconn(con)
            if error:
                raise error
        return row


    def fetch_all(self, query, params={}):
        con = None
        row_list = None
        error = None
        try:
            con = self.connection_pool.getconn()
            cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(query, params)
            row_list = cursor.fetchall()
        except psycopg2.Error as e:
            logging.error(
                    'Error: SQL multi-row query: {} -- {}'.format(query, params))
            error = DBControl.DatabaseError(e)
        else:
            logging.getLogger("database").debug(
                    'SQL multi-row query: {}'.format(cursor.query.decode("utf-8").strip()))
        finally:
            if con:
                self.connection_pool.putconn(con)
            if error:
                raise error
        return row_list


    def edit_database(self, query, params={}):
        con = None
        error = None
        try:
            con = self.connection_pool.getconn()
            cursor = con.cursor()
            cursor.execute(query, params)
            con.commit()
        except psycopg2.Error as e:
            logging.error(
                    'Error: edit_database: {} -- {}'.format(query, params))
            error = DBControl.DatabaseError(e)
            # roll back
            if con:
                con.rollback()
        else:
            logging.getLogger("database").debug(
                    'edit_database: {}'.format(cursor.query.decode("utf-8").strip()))
        finally:
            if con:
                self.connection_pool.putconn(con)
            if error:
                raise error


    def table_exists(self, table_name):
        con = None
        table_exists = False
        error = None
        try:
            con = self.connection_pool.getconn()
            cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(
                    sql.SQL(
                        """
                            SELECT EXISTS(
                                SELECT * FROM information_schema.tables
                                WHERE table_name = {p_table_name})
                        """
                        ).format(
                            p_table_name=sql.Placeholder(name='table_name')),
                        { "table_name" : table_name })
            table_exists = cursor.fetchone()[0]
        except psycopg2.Error as e:
            logging.error(
                    'SQL single-row query: {} -- {}'.format(query, params))
            error = DBControl.DatabaseError(e)
        finally:
            if con:
                self.connection_pool.putconn(con)
            if error:
                raise error
        return table_exists


    class DatabaseError(Exception):
        """ root database error """

    class DatabaseResultEmptyError(DatabaseError):
        """ no query result """

