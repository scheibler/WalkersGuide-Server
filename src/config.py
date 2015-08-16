#!/usr/bin/python
# -*- coding: utf-8 -*-

# singleton code comes from:
# http://code.activestate.com/recipes/52558/#as_content

# config parser
import configparser, os, sys, time

class Config:
    """ A python singleton """

    class __impl:
        """ Implementation of the singleton interface """
        def __init__(self):
            self.session_ids = {}
            self.config = configparser.ConfigParser()
            self.config.DEFAULT_TABLENAMES = {
                    'routing_table' : 'eu_2po_4pgr',
                    'intersection_table' : 'intersections',
                    'intersection_data_table' : 'intersection_data' }
            self.config.DEFAULT_DATABASE_SETTINGS = {
                    'db_name' : 'osm_europe',
                    'db_host_name' : '127.0.0.1',
                    'db_port' : '5432',
                    'db_user' : 'wgs_writer',
                    'db_password' : 'password' }
            self.config.DEFAULT_WEBSERVER_SETTINGS = {
                    'host' : 'example.org',
                    'port' : '23456',
                    'thread_pool' : '10' }
            self.config.DEFAULT_JAVAGATEWAY_SETTINGS = {
                    'gateway_port' : '25333' }
            self.config.DEFAULT_FOLDER = {
                    'logs_folder' : '/data/routing/WalkersGuide-Server/logs',
                    'maps_folder' : '/data/routing/WalkersGuide-Server/maps' }
            self.config.DEFAULT_EMAIL = {
                    'sender_mail_server_address' : 'smtp.example.org',
                    'sender_mail_server_port' : '587',
                    'sender_mail_server_login' : 'email@example.org',
                    'sender_mail_server_password' : 'password',
                    'recipient_address' : 'recipient@example.org' }
            self.config.DEFAULT_USER_LANGUAGE = {
                    'default_language' : 'en' }
            self.set_defaults()
            # read from config file and overwrite default options
            # if the file does not exist, create it with default values and exit
            self.config.CONF_FILE = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "configuration.rc")
            if os.path.exists(self.config.CONF_FILE) == True:
                self.config.read(self.config.CONF_FILE)
            else:
                with open(self.config.CONF_FILE, 'w') as configfile:
                    self.config.write(configfile)
                print "Created config file and exited"
                sys.exit(0)

        def set_defaults(self):
            self.config.add_section('table_names')
            for key, value in self.config.DEFAULT_TABLENAMES.items():
                self.config.set('table_names', key, value)
            self.config.add_section('database_settings')
            for key, value in self.config.DEFAULT_DATABASE_SETTINGS.items():
                self.config.set('database_settings', key, value)
            self.config.add_section('webserver_settings')
            for key, value in self.config.DEFAULT_WEBSERVER_SETTINGS.items():
                self.config.set('webserver_settings', key, value)
            self.config.add_section('javagateway_settings')
            for key, value in self.config.DEFAULT_JAVAGATEWAY_SETTINGS.items():
                self.config.set('javagateway_settings', key, value)
            self.config.add_section('folder')
            for key, value in self.config.DEFAULT_FOLDER.items():
                self.config.set('folder', key, value)
            self.config.add_section('email')
            for key, value in self.config.DEFAULT_EMAIL.items():
                self.config.set('email', key, value)
            self.config.add_section('user_language_settings')
            for key, value in self.config.DEFAULT_USER_LANGUAGE.items():
                self.config.set('user_language_settings', key, value)

        def get_param(self, key):
            value = None
            try:
                value = self.config.get('table_names', key)
            except configparser.NoOptionError:
                pass
            try:
                value = self.config.get('database_settings', key)
            except configparser.NoOptionError:
                pass
            try:
                value = self.config.get('webserver_settings', key)
            except configparser.NoOptionError:
                pass
            try:
                value = self.config.get('javagateway_settings', key)
            except configparser.NoOptionError:
                pass
            try:
                value = self.config.get('folder', key)
            except configparser.NoOptionError:
                pass
            try:
                value = self.config.get('email', key)
            except configparser.NoOptionError:
                pass
            try:
                value = self.config.get('user_language_settings', key)
            except configparser.NoOptionError:
                pass
            if value:
                try:
                    return int(value)
                except ValueError:
                    pass
                return value.encode("utf-8")

        def print_config(self):
            for section in self.config.sections():
                print "[%s]" % section
                for key in self.config.options(section):
                    print "%s = %s" % (key, self.config.get(section, key))

        # session id management functions
        def add_session_id(self, id):
            self.session_ids[id] = {"to_be_removed":False, "created_at":int(time.time())}

        def query_removement_of_session_id(self, id):
            if id in self.session_ids:
                self.session_ids[id]['to_be_removed'] = True

        def confirm_removement_of_session_id(self, id):
            if id in self.session_ids:
                self.session_ids.pop(id)

        def clean_old_session(self, id):
            # first clean all sessions, which are older then 3 minutes
            for old_id in self.session_ids.keys():
                delay = int(time.time()) - self.session_ids[old_id]['created_at']
                if delay > 180:
                    self.confirm_removement_of_session_id(old_id)
            # then try to remove prior session id of the particular user
            self.query_removement_of_session_id(id)
            # then give the server a few seconds to cancel that session
            check_counter = 0
            while id in self.session_ids:
                time.sleep(1)
                check_counter += 1
                if check_counter == 15:
                    return False
            return True

        def has_session_id_to_remove(self, id):
            if id in self.session_ids:
                return self.session_ids[id]['to_be_removed']
            return False

        def number_of_session_ids(self):
            return len(self.session_ids.keys())

    # storage for the instance reference
    __instance = None

    def __init__(self):
        """ Create singleton instance """
        # Check whether we already have an instance
        if Config.__instance is None:
            # Create and remember instance
            Config.__instance = Config.__impl()

        # Store instance reference as the only member in the handle
        self.__dict__['_Config__instance'] = Config.__instance

    def __getattr__(self, attr):
        """ Delegate access to implementation """
        return getattr(self.__instance, attr)

    def __setattr__(self, attr, value):
        """ Delegate access to implementation """
        return setattr(self.__instance, attr, value)

