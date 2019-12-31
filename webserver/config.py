#!/usr/bin/python
# -*- coding: utf-8 -*-

# singleton code comes from:
# http://code.activestate.com/recipes/52558/#as_content

import configobj
import datetime
import logging, logging.handlers, logging.config
import os
import shutil
import sys
import time

from . import constants
from .helper import exit


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
                try:
                    os.makedirs(self.paths.get("config_folder"), exist_ok=True)
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("config_folder")))
            # wg-server config file
            self.paths['wg_server_config'] = os.path.join(
                    self.paths.get("config_folder"), "wg_server.conf")
            if not os.path.exists(self.paths.get("wg_server_config")):
                exit("WalkersGuide server config file %s not available" % self.paths.get("wg_server_config"))
            # log folders
            self.paths['log_folder'] = os.path.join(
                    self.paths.get("project_root"), "logs")
            if not os.path.exists(self.paths.get("log_folder")):
                try:
                    os.makedirs(self.paths.get("log_folder"), exist_ok=True)
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("log_folder")))
            self.paths['maps_log_folder'] = os.path.join(
                    self.paths.get("log_folder"), "maps", "%04d" % datetime.datetime.now().year)
            if not os.path.exists(self.paths.get("maps_log_folder")):
                try:
                    os.makedirs(self.paths.get("maps_log_folder"), exist_ok=True)
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("maps_log_folder")))
            self.paths['routes_log_folder'] = os.path.join(
                    self.paths.get("log_folder"), "routes")
            if not os.path.exists(self.paths.get("routes_log_folder")):
                try:
                    os.makedirs(self.paths.get("routes_log_folder"), exist_ok=True)
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("routes_log_folder")))
            self.paths['webserver_log_folder'] = os.path.join(
                    self.paths.get("log_folder"), "webserver")
            if not os.path.exists(self.paths.get("webserver_log_folder")):
                try:
                    os.makedirs(self.paths.get("webserver_log_folder"))
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("webserver_log_folder")))
            # maps folder
            self.paths['maps_folder'] = os.path.join(
                    self.paths.get("project_root"), "maps")
            if not os.path.exists(self.paths.get("maps_folder")):
                try:
                    os.makedirs(self.paths.get("maps_folder"), exist_ok=True)
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("maps_folder")))
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
                try:
                    os.makedirs(self.paths.get("temp_folder"), exist_ok=True)
                except OSError as e:
                    exit("Could not create folder {}".format(self.paths.get("temp_folder")))

            # check if osmconvert, osmfilter and osmosis are installed
            if not shutil.which("osmconvert"):
                exit("osmconvert is not installed\napt-get install osmctools")
            if not shutil.which("osmfilter"):
                exit("osmfilter is not installed\napt-get install osmctools")
            if not shutil.which("osmosis"):
                exit("osmosis is not installed\napt-get install osmosis")

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
                exit('General: Missing server name.')
            # debug
            self.debug = self._convert_boolean_config_value(
                    "debug", self.config["general"].get("debug"), False)
            # status email
            self.status_email = self.config["general"].get("status_email", "")
            if not self.status_email:
                exit('General: Missing status_email.')
            # support email
            self.support_email = self.config["general"].get("support_email", "")
            if not self.support_email:
                exit('General: Missing support_email.')

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
                if self.java.get("gateway_port") < 0 \
                        or self.java.get("gateway_port") >= 65536:
                    exit('java: Missing or invalid gateway_port.')
            # ram
            self.java['ram'] = self.config["java"].get("ram", "")
            if not self.java.get("ram"):
                exit('java: Missing java vm ram parameter.')
            # osm2po executable
            self.java['osm2po_executable'] = self.config["java"].get("osm2po_executable", "")
            if not self.java.get("osm2po_executable"):
                exit('java: Missing osm2po_executable.')
            elif not os.path.exists(self.java.get("osm2po_executable")):
                exit("osm2po executable %s not found." % self.java.get("osm2po_executable"))
            # osm2po config file
            self.java['osm2po_config'] = os.path.join(
                    self.paths.get("config_folder"), "osm2po.conf")
            if not os.path.exists(self.java.get("osm2po_config")):
                exit(
                        "osm2po config file %s not available\n" \
                        "cp config.example/osm2po_x.x.x.conf.example config/osm2po.conf" \
                        % self.java.get("osm2po_config"))

            # email settings
            if "email" not in self.config:
                exit('Missing main section "[email]".')
            self.email = {}
            # host name
            self.email['host_name'] = self.config["email"].get("host_name", "")
            if not self.email.get("host_name"):
                exit('email: Missing host_name.')
            # port
            try:
                self.email['port'] = int(self.config["email"].get("port", 0))
            except ValueError:
                exit('email: Missing or invalid port.')
            else:
                if self.email.get("port") <= 0 \
                        or self.email.get("port") >= 65536:
                    exit('email: Missing or invalid port.')
            # email user
            self.email['user'] = self.config["email"].get("user", "")
            if not self.email.get("user"):
                exit('email: Missing user.')
            # email password
            self.email['password'] = self.config["email"].get("password", "")
            if not self.email.get("password"):
                exit('email: Missing password.')

            # configure logging module
            logging.config.dictConfig(
                    {
                        'version': 1,
                        'formatters': {
                            'file': {
                                'format' : '%(asctime)s [%(filename)s, %(funcName)s, Line %(lineno)s]\n[%(levelname)s] %(message)s'
                            },
                            'tty': {
                                '()' : 'webserver.helper.TTYLogFormatter'
                            }
                        },
                        'handlers': {
                            'email': {
                                'level' : 'INFO',
                                'class' : 'webserver.helper.CustomSubjectSMTPHandler',
                                'formatter' : '',
                                'mailhost' : (self.email.get("host_name"), self.email.get("port")),
                                'credentials' : (self.email.get("user"), self.email.get("password")),
                                'fromaddr' : self.status_email,
                                'toaddrs' : self.status_email,
                                'subject' : '{}: %(email_subject)s'.format(self.server_name),
                                'secure' : ()
                            },
                            'file': {
                                'level' : 'DEBUG' if self.debug else 'INFO',
                                'class' : 'logging.handlers.TimedRotatingFileHandler',
                                'formatter' : 'file',
                                'filename' : os.path.join(self.paths.get("webserver_log_folder"), "walkersguide.log"),
                                'backupCount' : 10,
                                'when' : 'midnight',
                                'delay' : True,
                                'encoding' : 'utf8'
                            },
                            'tty': {
                                'level' : 'INFO',
                                'class' :'logging.StreamHandler',
                                'formatter' : 'tty',
                                'stream' : 'ext://sys.stdout'
                            },
                            'cherrypy_access': {
                                'level' : 'INFO',
                                'class' : 'logging.handlers.TimedRotatingFileHandler',
                                'formatter' : '',
                                'filename' : os.path.join(self.paths.get("webserver_log_folder"), "access.log"),
                                'backupCount' : 10,
                                'when' : 'midnight',
                                'delay' : True,
                                'encoding' : 'utf8'
                            },
                            'cherrypy_error': {
                                'level' : 'INFO',
                                'class' : 'logging.handlers.TimedRotatingFileHandler',
                                'formatter' : '',
                                'filename' : os.path.join(self.paths.get("webserver_log_folder"), "errors.log"),
                                'backupCount' : 10,
                                'when' : 'midnight',
                                'delay' : True,
                                'encoding' : 'utf8'
                            }
                        },
                        'loggers': {
                            '' : {
                                'handlers': ['file', 'tty'],
                                'level' : 'DEBUG' if self.debug else 'INFO'
                            },
                            'database' : {
                                'handlers': ['file'],
                                'level' : 'DEBUG' if self.debug else 'INFO',
                                'propagate': False
                            },
                            'email' : {
                                'handlers': ['email', 'tty'],
                                'level': 'INFO',
                                'propagate': False
                            },
                            'cherrypy.access': {
                                'handlers': ['cherrypy_access', 'tty'],
                                'level': 'INFO',
                                'propagate': False
                            },
                            'cherrypy.error': {
                                'handlers': ['cherrypy_error', 'tty'],
                                'level': 'INFO',
                                'propagate': False
                            },
                            'py4j': {
                                'handlers': ['file'],
                                'level': 'ERROR',
                                'propagate': False
                            }
                        }
                    })

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

