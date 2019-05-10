#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, logging, math, time
from datetime import datetime

import cherrypy, json
from py4j.java_gateway import JavaGateway, GatewayClient

from . import constants, geometry, helper
from .config import Config
from .db_control import DBControl
from .poi import POI
from .route_footway_creator import RouteFootwayCreator
from .wg_logger import WGLogger
from .station_finder import StationFinder
from .translator import Translator 


class RoutingWebService():

    def __init__(self):
        print("init")
        for map_id, map_data in self.get_compatible_maps().items():
            print("%s: %s" % (map_id, map_data))

    def index(self):
        return ''
    index.exposed = True


    @cherrypy.tools.json_in()
    def get_route(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['route'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().default_language)
        # parse json encoded input
        input = cherrypy.request.json
        print(input)

        # user language
        if input.get("language") in constants.supported_language_list:
            translator = Translator(input.get("language"))

        # selected map
        try:
            db = DBControl(input.get("map_id"))
        except (DBControl.DatabaseNameEmptyError, \
                DBControl.DatabaseNotExistError, \
                DBControl.DatabaseVersionIncompatibleError) as e:
            return_tuple['error'] = e
            return helper.zip_data(return_tuple)

        # logging allowed
        logging_allowed = False
        if input.get("logging_allowed"):
            logging_allowed = True

        # indirection factor
        indirection_factor = 2.0
        if "indirection_factor" in input \
                and input['indirection_factor'] in constants.supported_indirection_factor_list:
            indirection_factor = input['indirection_factor']

        # allowed way classes
        allowed_way_classes = []
        if "allowed_way_classes" in input and type(input['allowed_way_classes']) is list:
            for way_class in input['allowed_way_classes']:
                if way_class in constants.supported_way_class_list:
                    allowed_way_classes.append(way_class)
        if not allowed_way_classes:
            allowed_way_classes = constants.supported_way_class_list

        # blocked way ids
        blocked_ways = []
        if "blocked_ways" in input and type(input['blocked_ways']) is list:
            blocked_ways = input['blocked_ways']

        # source points
        if not "source_points" in input:
            return_tuple['error'] = translator.translate("message", "no_source_route")
            return helper.zip_data(return_tuple)
        elif type(input['source_points']) != type([]):
            return_tuple['error'] = translator.translate("message", "no_source_route")
            return helper.zip_data(return_tuple)
        elif len(input['source_points']) < 2:
            return_tuple['error'] = translator.translate("message", "source_route_incomplete")
            return helper.zip_data(return_tuple)
        else:
            # check if source points are valid
            for point in input['source_points']:
                if point.get('type') not in constants.supported_route_point_object_list:
                    return_tuple['error'] = translator.translate("message", "source_route_incomplete")
                    return helper.zip_data(return_tuple)
        source_points = input['source_points']

        # create session id
        if not "session_id" in input:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = input['session_id']
        # try to cancel prior request, if necessary
        if Config().clean_old_session(session_id) == False:
            return_tuple['error'] = translator.translate("message", "old_request_still_running")
            return helper.zip_data(return_tuple)
        # this code is onley reached, if the prior session was canceled successfully
        if Config().number_of_session_ids() == Config().webserver.get("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        # create route logger object
        route_logger = WGLogger(
                Config().paths.get("routes_log_folder"),
                "%s---%s" % (source_points[0]['name'], source_points[-1]['name']),
                logging_allowed)
        # and append the source points
        route_logger.append_to_log("\n----- start of source points -----")
        route_logger.append_to_log( json.dumps( source_points, indent=4) \
                + "\n----- end of source points -----\n")

        # get a route
        rfc = RouteFootwayCreator(
                db, session_id, route_logger, translator, indirection_factor, allowed_way_classes, blocked_ways)
        for i in range(1, len(source_points)):
            try:
                route_part = rfc.find_footway_route(
                        source_points[i-1], source_points[i])
            except RouteFootwayCreator.FootwayRouteCreationError as e:
                Config().confirm_removement_of_session_id(session_id)
                route_logger.append_to_log("\n----- result -----\ncanceled")
                return_tuple['route'] = []
                return_tuple['error'] = "%s" % e
                return helper.zip_data(return_tuple)
            if len(return_tuple['route']) > 0:
                route_part.__delitem__(0)
            return_tuple['route'] += route_part

        # delete start point and first route segment, if it's a nameless one, just added as place holder
        if len(return_tuple['route']) > 3 \
                and return_tuple['route'][1].get("sub_type") == "":
            return_tuple['route'].__delitem__(0)
            return_tuple['route'].__delitem__(0)

        # check for missing turn values at intersections and poi
        # for example this can happen, if an intersection is a intermediate destination of a source route
        for i in range(0, len(return_tuple['route']), 2):
            if not "turn" in return_tuple['route'][i]:
                try:
                    return_tuple['route'][i]['turn'] = geometry.turn_between_two_segments(
                            return_tuple['route'][i+1]['bearing'], return_tuple['route'][i-1]['bearing'])
                except (IndexError, KeyError):
                    return_tuple['route'][i]['turn'] = -1

        # part of route parameters
        for i in range(0, len(return_tuple['route']), 2):
            if return_tuple['route'][i] \
                    and return_tuple['route'][i].get("type") == "intersection":
                intersection = return_tuple['route'][i]
                # previous route segment
                minimal_bearing_difference_previous = 180
                index_of_previous = -1
                bearing_of_previous_route_segment = None
                if return_tuple['route'][i-1] \
                        and return_tuple['route'][i-1].get("bearing"):
                    bearing_of_previous_route_segment = return_tuple['route'][i-1].get("bearing")
                # next route segment
                minimal_bearing_difference_next = 180
                index_of_next = -1
                bearing_of_next_route_segment = None
                if return_tuple['route'][i+1] \
                        and return_tuple['route'][i+1].get("bearing"):
                    bearing_of_next_route_segment = return_tuple['route'][i+1].get("bearing")
                # walk through the intersection segment list
                for index, intersection_segment in enumerate(intersection.get("way_list")):
                    if bearing_of_previous_route_segment:
                        bearing_difference_previous = geometry.bearing_difference_between_two_segments(
                                (bearing_of_previous_route_segment + 180) % 360,
                                intersection_segment.get("bearing"))
                        if bearing_difference_previous < minimal_bearing_difference_previous:
                            minimal_bearing_difference_previous = bearing_difference_previous
                            index_of_previous = index
                    if bearing_of_next_route_segment:
                        bearing_difference_next = geometry.bearing_difference_between_two_segments(
                                bearing_of_next_route_segment,
                                intersection_segment.get("bearing"))
                        if bearing_difference_next < minimal_bearing_difference_next:
                            minimal_bearing_difference_next = bearing_difference_next
                            index_of_next = index
                # set values if available and reset in route
                if index_of_previous > -1:
                    intersection['way_list'][index_of_previous]['part_of_previous_route_segment'] = True
                if index_of_next > -1:
                    intersection['way_list'][index_of_next]['part_of_next_route_segment'] = True
                return_tuple['route'][i] = intersection

        # add route description
        return_tuple['description'] = rfc.get_route_description( return_tuple['route'] )
        # logging
        route_logger.append_to_log("\n----- start of result route -----")
        route_logger.append_to_log( json.dumps( return_tuple['route'], indent=4) \
                + "\n----- end of result route -----\n")
        # delete session id
        Config().confirm_removement_of_session_id(session_id)
        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_route.exposed = True


    @cherrypy.tools.json_in()
    def get_next_intersections_for_way(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['next_intersections'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().default_language)
        # parse json encoded input
        input = cherrypy.request.json
        print(input)

        # user language
        if input.get("language") in constants.supported_language_list:
            translator = Translator(input.get("language"))

        # selected map
        try:
            db = DBControl(input.get("map_id"))
        except (DBControl.DatabaseNameEmptyError, \
                DBControl.DatabaseNotExistError, \
                DBControl.DatabaseVersionIncompatibleError) as e:
            return_tuple['error'] = e
            return helper.zip_data(return_tuple)

        # node_id, way_id and next_node_id
        if not input.get("node_id"):
            return_tuple['error'] = translator.translate("message", "no_node_id")
        if not input.get("way_id"):
            return_tuple['error'] = translator.translate("message", "no_way_id")
        if not input.get("next_node_id"):
            return_tuple['error'] = translator.translate("message", "no_next_node_id")

        # create session id
        if not "session_id" in input:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = input['session_id']
        # try to cancel prior request, if necessary
        if Config().clean_old_session(session_id) == False:
            return_tuple['error'] = translator.translate("message", "old_request_still_running")
            return helper.zip_data(return_tuple)
        # this code is onley reached, if the prior session was canceled successfully
        if Config().number_of_session_ids() == Config().webserver.get("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        print("Next Intersections for node_id:%d, way_id:%d, next_node_id: %d" \
                % (input.get("node_id"), input.get("way_id"), input.get("next_node_id")))
        poi = POI(db, session_id, translator)
        try:
            next_intersection_list = poi.next_intersections_for_way(
                input.get("node_id"), input.get("way_id"), input.get("next_node_id"))
        except POI.POICreationError as e:
            Config().confirm_removement_of_session_id(session_id)
            return_tuple['next_intersections'] = []
            return_tuple['error'] = "%s" % e
            return helper.zip_data(return_tuple)
        # convert return_tuple to json and zip it, before returning
        return_tuple['next_intersections'] = next_intersection_list
        Config().confirm_removement_of_session_id(session_id)
        return helper.zip_data(return_tuple)
    get_next_intersections_for_way.exposed = True


    @cherrypy.tools.json_in()
    def get_poi(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['poi'] = []
        return_tuple['error'] = ""
        translator = Translator(Config().default_language)
        # parse json encoded input
        input = cherrypy.request.json
        print(input)

        # user language
        if input.get("language") in constants.supported_language_list:
            translator = Translator(input.get("language"))

        # selected map
        try:
            db = DBControl(input.get("map_id"))
        except (DBControl.DatabaseNameEmptyError, \
                DBControl.DatabaseNotExistError, \
                DBControl.DatabaseVersionIncompatibleError) as e:
            return_tuple['error'] = e
            return helper.zip_data(return_tuple)

        # check latitude, longitude and radius input
        try:
            lat = float(input['lat'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        try:
            lon = float(input['lon'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)
        try:
            radius = int(input['radius'])
            number_of_results = int(input['number_of_results'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_range_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_range_value")
            return helper.zip_data(return_tuple)

        # tags and search
        # tag list
        tag_list = []
        if input.get("tags") \
                and type(input.get("tags")) is list:
            for tag in input.get("tags"):
                if tag in constants.supported_poi_category_listp:
                    tag_list.append(tag)
        if not tag_list:
            return_tuple['error'] = translator.translate("message", "no_tags_value")
            return helper.zip_data(return_tuple)
        # search
        try:
            search = input['search']
        except KeyError as e:
            search = ""

        # create session id
        if not "session_id" in input:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = input['session_id']
        # try to cancel prior request
        if Config().clean_old_session(session_id) == False:
            return_tuple['error'] = translator.translate("message", "old_request_still_running")
            return helper.zip_data(return_tuple)
        if Config().number_of_session_ids() == Config().webserver.get("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        # get poi
        poi = POI(db, session_id, translator)
        poi_list = poi.get_poi(lat, lon, radius, number_of_results, tag_list, search)
        if poi_list == None:
            Config().confirm_removement_of_session_id(session_id)
            return_tuple['poi'] = []
            return_tuple['error'] = translator.translate("message", "process_canceled")
            return helper.zip_data(return_tuple)

        # convert return_tuple to json and zip it, before returning
        return_tuple['poi'] = poi_list
        Config().confirm_removement_of_session_id(session_id)
        return helper.zip_data(return_tuple)
    get_poi.exposed = True


    @cherrypy.tools.json_in()
    def get_departures(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['departures'] = []
        return_tuple['error'] = ""
        translator = Translator(Config().default_language)
        # parse json encoded input
        input = cherrypy.request.json

        # user language
        if input.get("language") in constants.supported_language_list:
            translator = Translator(input.get("language"))

        # selected map
        try:
            db = DBControl(input.get("map_id"))
        except (DBControl.DatabaseNameEmptyError, \
                DBControl.DatabaseNotExistError, \
                DBControl.DatabaseVersionIncompatibleError) as e:
            return_tuple['error'] = e
            return helper.zip_data(return_tuple)

        # public transport provider
        if input.get("public_transport_provider") not in constants.supported_public_transport_provider_list:
            return_tuple['error'] = translator.translate("message", "no_public_transport_provider")
            return helper.zip_data(return_tuple)
        public_transport_provider = input.get("public_transport_provider")

        # check latitude and longitude
        try:
            lat = float(input['lat'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        try:
            lon = float(input['lon'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)

        # vehicle list
        vehicle_list = []
        if "vehicles" in input and type(input['vehicles']) is list:
            vehicle_list = input['vehicles']

        # get the nearest stations for this coordinates and take the first one
        gateway = JavaGateway(GatewayClient(port=Config().java.get("gateway_port")), auto_field=True)
        main_point = gateway.entry_point
        closest_stations_result = main_point.getNearestStations(
                public_transport_provider,
                geometry.convert_coordinate_to_int(lat),
                geometry.convert_coordinate_to_int(lon))
        if not closest_stations_result:
            return_tuple['error'] = translator.translate("message", "no_station_for_this_coordinates")
            return helper.zip_data(return_tuple)
        elif closest_stations_result.status.toString() == "INVALID_STATION":
            return_tuple['error'] = translator.translate("message", "no_station_for_this_coordinates")
            return helper.zip_data(return_tuple)
        elif closest_stations_result.status.toString() == "SERVICE_DOWN":
            return_tuple['error'] = translator.translate("message", "bahn_server_down")
            return helper.zip_data(return_tuple)
        elif closest_stations_result.locations == None or len(closest_stations_result.locations) == 0:
            return_tuple['error'] = translator.translate("message", "no_station_for_this_coordinates")
            return helper.zip_data(return_tuple)

        # get departures for station
        sfinder = StationFinder(public_transport_provider)
        station = sfinder.select_station_by_vehicle_type(
                closest_stations_result.locations, lat, lon, vehicle_list)
        departures_result = main_point.getDepartures(
                public_transport_provider, station.id)
        for station_departure in departures_result.stationDepartures:
            for departure in station_departure.departures:
                try:
                    dep_entry = {}
                    dep_entry['nr'] = "%s%s" % (departure.line.product.code, departure.line.label)
                    dep_entry['to'] = departure.destination.name
                    dep_entry['time'] = departure.plannedTime.getTime()
                    return_tuple['departures'].append(dep_entry)
                except Exception as e:
                    pass

        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_departures.exposed = True


    @cherrypy.tools.json_in()
    def cancel_request(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['error'] = ""
        translator = Translator(Config().default_language)
        # parse json encoded input
        input = cherrypy.request.json
        # user language
        if input.get("language") in constants.supported_language_list:
            translator = Translator(input.get("language"))
        # create session id
        if not "session_id" in input:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        # request cancelling of running processes
        Config().query_removement_of_session_id(input['session_id'])
        print("cancel session id %s" % input['session_id'])
        return helper.zip_data(return_tuple)
    cancel_request.exposed = True


    def get_status(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        # server params
        return_tuple['server_name'] = Config().server_name
        return_tuple['server_version'] = constants.server_version
        return_tuple['supported_api_version_list'] = constants.supported_api_version_list
        return_tuple['supported_map_version_list'] = constants.supported_map_version_list
        # maps
        return_tuple['maps'] = self.get_compatible_maps()
        # supported poi categories, languages and public transport provider
        return_tuple['supported_poi_category_list'] = constants.supported_poi_category_listp
        return_tuple['supported_language_list'] = constants.supported_language_list
        return_tuple['supported_public_transport_provider_list'] = constants.supported_public_transport_provider_list
        # routing params
        return_tuple['supported_indirection_factor_list'] = constants.supported_indirection_factor_list
        return_tuple['supported_way_class_list'] = constants.supported_way_class_list
        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_status.exposed = True


    def get_compatible_maps(self):
        compatible_maps = {}
        for map_id, map_data in Config().maps.items():
            try:
                db = DBControl(map_id)
            except (DBControl.DatabaseNameEmptyError, \
                    DBControl.DatabaseNotExistError, \
                    DBControl.DatabaseVersionIncompatibleError) as e:
                logging.error(e)
            else:
                # extend with map version and creation date from the database table "map_info"
                map_data['version'] = db.map_version
                map_data['created'] = db.map_created
                compatible_maps[map_id] = map_data
        return compatible_maps


###################
### start webserver

def start():
    cherrypy.config['server.socket_host'] = Config().webserver.get("host_name")
    cherrypy.config['server.socket_port'] = Config().webserver.get("port")
    cherrypy.config['server.thread_pool'] = Config().webserver.get("thread_pool")
    cherrypy.config['tools.encode.on'] = True
    cherrypy.config['tools.encode.encoding'] = "utf-8"
    cherrypy.log.screen = False
    cherrypy.quickstart( RoutingWebService() )


if __name__ == '__main__':
    start()
