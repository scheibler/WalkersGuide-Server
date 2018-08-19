#!/usr/bin/python
# -*- coding: utf-8 -*-

import psycopg2
import psycopg2.extras
import sys

from config import Config
import constants


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
            raise DBControl.DatabaseNameEmptyError("The database name is empty")
        self.db_name = map_id
        # get databases map version and creation date
        try:
            map_info = self.fetch_data("SELECT version, created FROM %s WHERE id = '%s'" \
                    % (Config().database.get("map_info"), map_id))[0]
        except (psycopg2.DatabaseError, IndexError, KeyError) as e:
            raise DBControl.DatabaseNotExistError("The database %s does not exist" % map_id)
        # version and creation date
        self.map_version = map_info['version']
        if self.map_version not in constants.supported_map_version_list:
            raise DBControl.DatabaseVersionIncompatibleError("The database %s is not compatible.\n" \
                    "Map version: %d not in [%s]" % (map_id, self.map_version,
                        ','.join(constants.supported_map_version_list)))
        # map creation
        self.map_created = map_info['created']


    def fetch_data(self, query):
        con = None
        try:
            con = psycopg2.connect(database=self.db_name, host=self.host_name, port=self.port,
                    user=self.user_name, password=self.password)
            cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(query)
            rows = cursor.fetchall()
        except psycopg2.DatabaseError, e:
            if e.__str__().strip().endswith("vertex was not found.") == True:
                rows = []
            else:
                print e
                raise
        finally:
            if con:
                con.close()
        return rows


    def send_data(self, query):
        con = None
        try:
            con = psycopg2.connect(database=self.db_name, host=self.host_name, port=self.port,
                    user=self.user_name, password=self.password)
            cur = con.cursor()
            cur.execute(query)
            con.commit()
        except psycopg2.DatabaseError, e:
            print e
            if con:
                con.rollback()
            sys.exit(1)
        finally:
            if con:
                con.close()


    class DatabaseNameEmptyError(LookupError):
        """ database name is empty"""

    class DatabaseNotExistError(LookupError):
        """ database only defined in config file """

    class DatabaseVersionIncompatibleError(LookupError):
        """ databases map version is not supported by this server instance"""

