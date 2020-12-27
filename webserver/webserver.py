#!/usr/bin/python
# -*- coding: utf-8 -*-

import cherrypy
import datetime
import json
import logging
import time
import traceback

from . import constants
from .config import Config
from .constants import ReturnCode
from .db_control import DBControl
from .helper import WebserverException, send_email
from .poi import POI
from .pedestrian_route import PedestrianRoute


class RoutingWebService():
    email_resend_delay = 60*60

    def __init__(self):
        self.last_map_exception_email_sent = 0
        logging.info("Webserver initialized: {}".format(json.dumps(self.get_status(), indent=4)))


    @cherrypy.expose
    def index(self):
        map_list = []
        for map_id, map_data in self.get_status().get("maps").items():
            map_creation_date = datetime.datetime.fromtimestamp(
                    map_data.get("created")/1000)
            map_list.append(
                    "            <li>%s: Created at %04d-%02d-%02d<br />%s</li>" \
                            % (map_data.get("name"), map_creation_date.year,
                                map_creation_date.month, map_creation_date.day,
                                map_data.get("description")))
        return """
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="author" content="Eric Scheibler" />
        <title>WalkersGuide API status page</title>
        <style>
            body {{font: normal 100.01% Helvetica, Arial, sans-serif;}}
            h1   {{font-size: 1.2em;}}
        </style>
    </head>
    <body>
        <h1>{}</h1>
        <p>Version: {}</p>
        <p>Available maps:</p>
        <ul>
{}
        </ul>
        <p>Mor information at <a href="https://www.walkersguide.org">www.walkersguide.org</a></p>
    </body>
</html>
""".format(Config().server_name, constants.server_version, '\n'.join(map_list))


    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def get_route(self):
        # parse json encoded input
        try:
            input = cherrypy.request.json
        except AttributeError as e:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error(e)
            return
        else:
            logging.info("Query: get_route\nParams: {}".format(input))
        # create session id
        try:
            session_id = self.create_session_id(input)
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
            return
        else:
            Config().add_session_id(session_id)
        # get route
        result = { "route":[], "description":"" }
        try:
            pedestrian_route = PedestrianRoute(
                    input.get("map_id"), session_id, input.get("language"),
                    input.get("allowed_way_classes"), input.get("blocked_ways"))
            result['route'] = pedestrian_route.calculate_route(input.get("source_points"))
        except WebserverException as e:
            pedestrian_route = None
            cherrypy.response.status = e.return_code
            logging.error(e)
        except Exception as e:
            pedestrian_route = None
            cherrypy.response.status = ReturnCode.INTERNAL_SERVER_ERROR
            logging.critical(e, exc_info=True)
            send_email(
                    "Error in function get_route", traceback.format_exc())
        else:
            result['description'] = pedestrian_route.create_description_for_route(result.get("route"))
        finally:
            if pedestrian_route:
                pedestrian_route.delete_temp_routing_database()
            Config().confirm_removement_of_session_id(session_id)
        return result


    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def get_next_intersections_for_way(self):
        # parse json encoded input
        try:
            input = cherrypy.request.json
        except AttributeError as e:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error(e)
            return
        else:
            logging.info("Query: get_next_intersections_for_way\nParams: {}".format(input))
        # create session id
        try:
            session_id = self.create_session_id(input)
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
            return
        else:
            Config().add_session_id(session_id)
        # get next intersections
        result = {}
        try:
            poi = POI(
                    input.get("map_id"), session_id, input.get("language"))
            next_intersection_list = poi.next_intersections_for_way(
                    input.get("node_id"), input.get("way_id"), input.get("next_node_id"))
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
        except Exception as e:
            cherrypy.response.status = ReturnCode.INTERNAL_SERVER_ERROR
            logging.critical(e, exc_info=True)
            send_email(
                    "Error in function get_next_intersections_for_way", traceback.format_exc())
        else:
            result['next_intersections'] = next_intersection_list
        finally:
            Config().confirm_removement_of_session_id(session_id)
        return result


    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def get_poi(self):
        # parse json encoded input
        try:
            input = cherrypy.request.json
        except AttributeError as e:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error(e)
            return
        else:
            logging.info("Query: get_poi\nParams: {}".format(input))
        # create session id
        try:
            session_id = self.create_session_id(input)
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
            return
        else:
            Config().add_session_id(session_id)
        # get poi
        result = {}
        try:
            poi = POI(
                    input.get("map_id"), session_id, input.get("language"))
            poi_list = poi.get_poi(
                    input.get("lat"), input.get("lon"),
                    input.get("radius"), input.get("number_of_results"),
                    input.get("tags"), input.get("search"))
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
        except Exception as e:
            cherrypy.response.status = ReturnCode.INTERNAL_SERVER_ERROR
            logging.critical(e, exc_info=True)
            send_email(
                    "Error in function get_poi", traceback.format_exc())
        else:
            result['poi'] = poi_list
        finally:
            Config().confirm_removement_of_session_id(session_id)
        return result


    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def get_hiking_trails(self):
        # parse json encoded input
        try:
            input = cherrypy.request.json
        except AttributeError as e:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error(e)
            return
        else:
            logging.info("Query: get_hiking_trails\nParams: {}".format(input))
        # create session id
        try:
            session_id = self.create_session_id(input)
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
            return
        else:
            Config().add_session_id(session_id)
        # get trails
        result = {}
        try:
            poi = POI(
                    input.get("map_id"), session_id, input.get("language"))
            trail_list = poi.get_hiking_trails(
                    input.get("lat"), input.get("lon"), input.get("radius"))
        except WebserverException as e:
            cherrypy.response.status = e.return_code
            logging.error(e)
        except Exception as e:
            cherrypy.response.status = ReturnCode.INTERNAL_SERVER_ERROR
            logging.critical(e, exc_info=True)
            send_email(
                    "Error in function get_hiking_trails", traceback.format_exc())
        else:
            result['hiking_trails'] = trail_list
        finally:
            Config().confirm_removement_of_session_id(session_id)
        return result


    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def send_feedback(self):
        # parse json encoded input
        try:
            input = cherrypy.request.json
        except AttributeError as e:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error(e)
            return
        else:
            logging.info("Query: send_feedback\nParams: {}".format(input))
        # check for message and token
        if not input.get("message"):
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error("Missing message. Email not sent.")
        elif not input.get("token"):
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error("Missing token. Email not sent.")
        elif input.get("token") not in constants.supported_feedback_token_list:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error("Unsupported token: {}. Email not sent.".format(input.get("token")))
        else:
            send_email(
                    "User request: {}".format(input.get("token")),
                    "Token: {}\nSender: {}\n\n{}".format(
                        input.get("token"), input.get("sender"), input.get("message")))
        return


    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def cancel_request(self):
        # parse json encoded input
        try:
            input = cherrypy.request.json
        except AttributeError as e:
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error(e)
            return
        else:
            logging.info("Query: cancel_request\nParams: {}".format(input))
        # session id
        if not input.get("session_id"):
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error("No session_id")
        elif not isinstance(input.get("session_id"), str):
            cherrypy.response.status = ReturnCode.BAD_REQUEST
            logging.error("Invalid session_id")
        else:
            Config().query_removement_of_session_id(input.get("session_id"))
        return


    @cherrypy.expose
    @cherrypy.tools.json_out()
    def get_status(self):
        result = {}
        # server params
        result['server_name'] = Config().server_name
        result['server_version'] = constants.server_version
        result['supported_api_version_list'] = constants.supported_api_version_list
        result['supported_map_version_list'] = constants.supported_map_version_list
        # supported poi categories and languages
        result['supported_poi_category_list'] = constants.supported_poi_category_listp
        result['supported_language_list'] = constants.supported_language_list
        # maps
        result['maps'] = {}
        for map_id, map_data in Config().maps.items():
            try:
                db = DBControl(map_id)
            except Exception as e:
                logging.critical(e, exc_info=True)
                if int(time.time()) - self.last_map_exception_email_sent > self.email_resend_delay:
                    send_email(
                            "Map initialization failed for {}".format(map_id),
                            traceback.format_exc())
                    self.last_map_exception_email_sent = int(time.time())
            else:
                # extend with map version and creation date from the database table "map_info"
                result['maps'][map_id] = {
                        **map_data, **{"version":db.map_version, "created":db.map_created}}
        return result


    def create_session_id(self, input):
        session_id = input.get("session_id")
        if not session_id:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "No session_id")
        elif type(session_id) is not str:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "Invalid session_id")
        # check for old sessions and max session limit
        if not Config().clean_old_session(session_id):
            raise WebserverException(
                    ReturnCode.REQUEST_IN_PROGRESS,
                    "Process with session_id {} already running".format(session_id))
        if Config().number_of_session_ids() == Config().webserver.get("thread_pool") - 1:
            raise WebserverException(
                    ReturnCode.SERVICE_UNAVAILABLE, "Webserver unavailable or busy")
        return session_id



###################
### start webserver

def start():
    # configure cherrypy webservice
    cherrypy.config.update(
            {
                'server.socket_host'    : Config().webserver.get("host_name"),
                'server.socket_port'    : Config().webserver.get("port"),
                'server.thread_pool'    : Config().webserver.get("thread_pool"),
                'log.screen'            : False,
                'log.access_file'       : '',
                'log.error_file'        : '',
                'tools.encode.on'       : True,
                'tools.encode.encoding' : 'utf-8',
                'tools.gzip.on'         : True,
                'tools.gzip.mime_types' : ['text/*', 'application/*']
            })
    cherrypy.engine.unsubscribe('graceful', cherrypy.log.reopen_files)
    cherrypy.quickstart(RoutingWebService())



if __name__ == '__main__':
    start()
