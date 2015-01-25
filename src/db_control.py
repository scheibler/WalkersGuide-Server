#!/usr/bin/python
# -*- coding: utf-8 -*-

import psycopg2
import psycopg2.extras
import sys
from config import Config

class DBControl():

    def __init__(self, database_name = None):
        if database_name == None:
            self.db_name = Config().get_param("db_name")
        else:
            self.db_name = database_name
        self.host_name = Config().get_param("db_host_name")
        self.port = Config().get_param("db_port")
        self.user_name = Config().get_param("db_user")
        self.password = Config().get_param("db_password")

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
                sys.exit(1)
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

