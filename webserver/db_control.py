#!/usr/bin/python
# -*- coding: utf-8 -*-

# python sql tutorial: http://initd.org/psycopg/docs/sql.html

import logging

import psycopg2
import psycopg2.extras
from psycopg2 import sql

from . import constants
from .constants import ReturnCode
from .config import Config
from .helper import WebserverException


class DBControl():

    def __init__(self, map_id):
        # host and port
        self.host_name = Config().database.get("host_name")
        self.port = Config().database.get("port")
        # user and password
        self.user_name = Config().database.get("user")
        self.password = Config().database.get("password")
        # database name
        if not map_id:
            raise WebserverException(ReturnCode.MAP_LOADING_FAILED, 'No map id')
        self.db_name = map_id

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
            con = self.connect()
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
                con.close()
            if error:
                raise error
        return row


    def fetch_all(self, query, params={}):
        con = None
        row_list = None
        error = None
        try:
            con = self.connect()
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
                con.close()
            if error:
                raise error
        return row_list


    def edit_database(self, query, params={}):
        con = None
        error = None
        try:
            con = self.connect()
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
                con.close()
            if error:
                raise error


    class DatabaseError(Exception):
        """ root database error """

    class DatabaseResultEmptyError(DatabaseError):
        """ no query result """

    def connect(self):
        return psycopg2.connect(
                database=self.db_name, host=self.host_name, port=self.port,
                user=self.user_name, password=self.password)

