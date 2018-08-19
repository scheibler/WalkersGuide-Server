#!/usr/bin/python
# -*- coding: utf-8 -*-

# singleton code comes from:
# http://code.activestate.com/recipes/52558/#as_content

import configobj
import logging
import os
import sys
import time

import constants
from helper import exit


class Config:
    """ A python singleton """

    class __impl:
        """ Implementation of the singleton interface """
        def __init__(self):
            # empty session id map
            self.session_ids = {}
            # system wide default language
            self.default_language = constants.supported_language_list[0]

            # some paths
            self.paths = {}
            self.paths['project_root'] = os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__)))
            # config folder
            self.paths['config_folder'] = os.path.join(
                    self.paths.get("project_root"), "config")
            if not os.path.exists(self.paths.get("config_folder")):
                os.makedirs(self.paths.get("config_folder"))
            # wg-server config file
            self.paths['wg_server_config'] = os.path.join(
                    self.paths.get("config_folder"), "wg_server.conf")
            if not os.path.exists(self.paths.get("wg_server_config")):
                exit("Config file %s not available" % self.paths.get("wg_server_config"))
            # log folders
            self.paths['log_folder'] = os.path.join(
                    self.paths.get("project_root"), "logs")
            if not os.path.exists(self.paths.get("log_folder")):
                os.makedirs(self.paths.get("log_folder"))
            self.paths['maps_log_folder'] = os.path.join(
                    self.paths.get("log_folder"), "maps")
            if not os.path.exists(self.paths.get("maps_log_folder")):
                os.makedirs(self.paths.get("maps_log_folder"))
            self.paths['routes_log_folder'] = os.path.join(
                    self.paths.get("log_folder"), "routes")
            if not os.path.exists(self.paths.get("routes_log_folder")):
                os.makedirs(self.paths.get("routes_log_folder"))
            # maps folder
            self.paths['maps_folder'] = os.path.join(
                    self.paths.get("project_root"), "maps")
            if not os.path.exists(self.paths.get("maps_folder")):
                os.makedirs(self.paths.get("maps_folder"))
            # public_transport_library folder and files
            self.paths['public_transport_library_folder'] = os.path.join(
                    self.paths.get("project_root"), "public_transport_library")
            if not os.path.exists(self.paths.get("public_transport_library_folder")):
                exit("Public transport library folder not found.")
            self.paths['public_transport_library_executable'] = os.path.join(
                    self.paths.get("public_transport_library_folder"), "dist", "PublicTransportInterface.jar")
            # shell folder and files
            self.paths['shell_folder'] = os.path.join(
                    self.paths.get("project_root"), "shell")
            if not os.path.exists(self.paths.get("shell_folder")):
                exit("Shell folder not found.")
            self.paths['shell_config'] = os.path.join(
                    self.paths.get("shell_folder"), "configuration.sh")
            self.paths['shell_create_map_database'] = os.path.join(
                    self.paths.get("shell_folder"), "create_complete_database.sh")
            self.paths['shell_lock_file'] = os.path.join(
                    self.paths.get("project_root"), ".in_progress")
            # sql_functions folder
            self.paths['sql_files_folder'] = os.path.join(
                    self.paths.get("project_root"), "sql_functions")
            if not os.path.exists(self.paths.get("sql_files_folder")):
                exit("SQL functions folder not found.")
            # temp folder
            self.paths['temp_folder'] = os.path.join(
                    self.paths.get("project_root"), "tmp")
            if not os.path.exists(self.paths.get("temp_folder")):
                os.makedirs(self.paths.get("temp_folder"))
            # tools folder
            self.paths['tools_folder'] = os.path.join(
                    os.path.dirname(self.paths.get("project_root")), "tools")
            if not os.path.exists(self.paths.get("tools_folder")):
                exit("Tools folder not found.")

            # load config file
            self.config = None
            try:
                self.config = configobj.ConfigObj(
                        self.paths.get("wg_server_config"), interpolation=False)
            except configobj.ParseError as err:
                exit(str(err))

            # general settings
            if "general" not in self.config:
                exit('Missing main section "[general]".')
            # server name
            self.server_name = self.config["general"].get("server_name", "")
            if not self.server_name:
                exit('Missing server name.')
            # debug
            self.debug = self._convert_boolean_config_value(
                    "debug", self.config["general"].get("debug"), False)
            if self.debug:
                logging.basicConfig(level=logging.DEBUG)
            else:
                logging.basicConfig(level=logging.WARNING)
            # status email
            self.status_email = self.config["general"].get("status_email", "")
            if not self.status_email:
                logging.warning("No status email address found.")
            # support email
            self.support_email = self.config["general"].get("support_email", "")
            if not self.support_email:
                logging.warning("No support email address found.")

            # database settings
            if "database" not in self.config:
                exit('Missing main section "[database]".')
            self.database = {}
            # host name
            self.database['host_name'] = self.config["database"].get("host_name", "")
            if not self.database.get("host_name"):
                exit('Database: Missing host_name.')
            # port
            try:
                self.database['port'] = int(self.config["database"].get("port", 0))
            except ValueError:
                exit('Database: Missing or invalid port.')
            else:
                if self.database.get("port") <= 0 \
                        or self.database.get("port") >= 65536:
                    exit('Database: Missing or invalid port.')
            # database user
            self.database['user'] = self.config["database"].get("user", "")
            if not self.database.get("user"):
                exit('Database: Missing user.')
            # database password
            self.database['password'] = self.config["database"].get("password", "")
            if not self.database.get("password"):
                exit('Database: Missing password.')
            # self-created database names
            self.database['intersection_table'] = "intersections"
            self.database['intersection_data_table'] = "intersection_data"
            self.database['map_info'] = "map_info"
            self.database['routing_prefix'] = "routing"
            self.database['routing_table'] = "%s_2po_4pgr" % self.database.get("routing_prefix")
            self.database['way_class_weights'] = "way_class_weights"

            # webserver settings
            if "webserver" not in self.config:
                exit('Missing main section "[webserver]".')
            self.webserver = {}
            # host name
            self.webserver['host_name'] = self.config["webserver"].get("host_name", "")
            if not self.webserver.get("host_name"):
                exit('webserver: Missing host_name.')
            # port
            try:
                self.webserver['port'] = int(self.config["webserver"].get("port", 0))
            except ValueError:
                exit('webserver: Missing or invalid port.')
            else:
                if self.webserver.get("port") <= 0 \
                        or self.webserver.get("port") >= 65536:
                    exit('webserver: Missing port.')
            # thread_pool
            try:
                self.webserver['thread_pool'] = int(self.config["webserver"].get("thread_pool", 0))
            except ValueError:
                exit('webserver: Invalid thread_pool.')
            else:
                if self.webserver.get("thread_pool") == 0:
                    self.webserver['thread_pool'] = 10
                    logging.warning("No thread_pool param found. Using default of 10.")

            # java settings
            if "java" not in self.config:
                exit('Missing main section "[java]".')
            self.java = {}
            # gateway_port
            try:
                self.java['gateway_port'] = int(self.config["java"].get("gateway_port", 0))
            except ValueError:
                exit('java: Invalid gateway_port.')
            else:
                if self.java.get("gateway_port") <= 0 \
                        or self.java.get("gateway_port") >= 65536:
                    exit('java: Missing or invalid gateway_port.')
            # ram
            self.java['ram'] = self.config["java"].get("ram", "")
            if not self.java.get("ram"):
                self.java['ram'] = "8G"
                logging.warning("No java ram param found. Using default of 8G.")

            # maps
            if "maps" not in self.config:
                exit('Missing main section "[maps]".')
            self.maps = {}
            for map_id, map_data in self.config["maps"].items():
                # name and description
                if not map_data.get("name"):
                    exit('map %s: Missing name.' % map_id)
                if not map_data.get("description"):
                    exit('map %s: Missing description.' % map_id)
                # url or url list devided by ;
                if not map_data.get("urls"):
                    exit('map %s: Missing urls.' % map_id)
                # optional parameters
                # development flag
                if not map_data.get("development"):
                    map_data['development'] = False
                    logging.warning("map %s: No development parameter found. Set to False" % map_id)
                else:
                    map_data['development'] = self._convert_boolean_config_value(
                            "development", map_data.get("development"), False)
                # add to maps dict
                self.maps[map_id] = map_data


        @staticmethod
        def _convert_boolean_config_value(name, value, default=True):
            """Convert the yes/no value from the config file into the corresponding 
            boolean. If value is None, use the default.
            :param name: config parameter name
            :type name: str
            :param value: yes, no or None
            :type value: str
            :param default: the default value to use if the option is None
            :type default: bool
            :returns: converted boolean value
            :rtype: bool
            """
            if not value:
                return default
            elif value == "yes":
                return True
            elif value == "no":
                return False
            else:
                exit("Invalid value for %s parameter\nPossible values: yes, no" % name)


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

