#!/usr/bin/python
# -*- coding: utf-8 -*-

from route_logger import RouteLogger
from db_control import DBControl
from translator import Translator
from config import Config
from poi import POI
import geometry
import time, json, operator, re, math

class RouteFootwayCreator:

    def __init__(self, session_id, route_logger_object, translator_object,
            indirection_factor, allowed_way_classes, blocked_ways):
        self.session_id = session_id
        self.route_logger = route_logger_object
        self.translator = translator_object

        # routing parameters
        self.route = []
        self.routing_table_name = Config().get_param("routing_table")
        self.temp_routing_table_name = "tmp_routing_%s" \
                % re.sub(r'[^a-zA-Z0-9]', '', self.session_id)
        self.intersections_table_name = Config().get_param("intersection_table")
        self.poi = POI(session_id, translator_object)
        self.minimum_radius = 600
        self.blocked_ways = blocked_ways

        # table column name for given indirection factor
        factor_column_name = "x1"
        if indirection_factor == 4.0:
            factor_column_name = "x4"
        elif indirection_factor == 3.0:
            factor_column_name = "x3"
        elif indirection_factor == 2.0:
            factor_column_name = "x2"
        elif indirection_factor == 1.5:
            factor_column_name = "x1_5"

        # way class weights list
        # way_class_weights table id's:
        #   1 = good way
        #   2 = neutral way
        #   3 = bad way
        #   4 = impassable way
        weight_list = DBControl().fetch_data("SELECT %s as weight \
                    from way_class_weights;" % factor_column_name)
        # way classes: find them in the kmh column of the routing table
        #   wcw_id 1 -- list index 0 = class 1: big, middle and unknown streets
        #   wcw_id 0 -- list index 1 = class 2: small streets
        #   wcw_id 1 -- list index 2 = class 3: paved ways
        #   wcw_id 2 -- list index 3 = class 4: unpaved ways
        #   wcw_id 2 -- list index 4 = class 5: unclassified ways
        #   wcw_id 2 -- list index 5 = class 6: steps
        #   wcw_id 3 -- list index 6 = class 7: impassable ways
        # initialize with all classes impassable
        self.way_class_weight_list = [ weight_list[3]['weight'] for x in range(7)]
        if allowed_way_classes.__contains__("big_streets"):
            # big and middle streets: neutral
            self.way_class_weight_list[0] = weight_list[1]['weight']
        if allowed_way_classes.__contains__("small_streets"):
            # small streets: good
            self.way_class_weight_list[1] = weight_list[0]['weight']
        if allowed_way_classes.__contains__("paved_ways"):
            # paved ways: neutral
            self.way_class_weight_list[2] = weight_list[1]['weight']
        if allowed_way_classes.__contains__("unpaved_ways"):
            # unpaved ways: bad
            self.way_class_weight_list[3] = weight_list[2]['weight']
        if allowed_way_classes.__contains__("unclassified_ways"):
            # unclassified ways: bad
            self.way_class_weight_list[4] = weight_list[2]['weight']
        if allowed_way_classes.__contains__("steps"):
            # steps: bad
            self.way_class_weight_list[5] = weight_list[2]['weight']
        # multiplication factor for way segment length = 100 - weight
        for index, weight in enumerate(self.way_class_weight_list):
            self.way_class_weight_list[index] = 100 - weight
        self.route_logger.append_to_log(self.way_class_weight_list, True)

    def find_footway_route(self, start_point, dest_point):
        print "footway route creator"
        # a few helper variables
        t1 = time.time()
        self.route = []
        last_target_id = -1
        reverse = False
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))

        # create temporary routing table
        distance_between_start_and_destination = geometry.distance_between_two_points(
                start_point['lat'], start_point['lon'],
                dest_point['lat'], dest_point['lon'])
        print "radius = %d" % distance_between_start_and_destination
        center_point = geometry.get_center_point(
                start_point['lat'], start_point['lon'],
                dest_point['lat'], dest_point['lon'])
        boundaries = geometry.get_boundary_box(center_point['lat'], center_point['lon'],
                self.minimum_radius + int(distance_between_start_and_destination / 2))
        # create temp table
        DBControl().send_data("" \
                "DROP TABLE IF EXISTS %s;" \
                "CREATE TABLE %s AS SELECT * FROM %s LIMIT 0;" \
                "INSERT INTO %s " \
                    "SELECT * from %s " \
                    "WHERE geom_way && ST_MakeEnvelope(%f, %f, %f, %f);"
                % (self.temp_routing_table_name, self.temp_routing_table_name,
                    self.routing_table_name, self.temp_routing_table_name,
                    self.routing_table_name, boundaries['left'], boundaries['bottom'],
                    boundaries['right'], boundaries['top']))
        # check if temp routing table is empty
        number_of_table_rows = DBControl().fetch_data("SELECT count(*) from %s" \
                % self.temp_routing_table_name)[0]['count']
        if number_of_table_rows == 0:
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            self.route_logger.append_to_log("Routing table too small", True)
            raise RouteFootwayCreator.FootwayRouteCreationError(
                self.translator.translate("footway_creator", "foot_route_creation_failed"))
        # adapt cost column
        t11 = time.time()
        # weight list
        for index, weight in enumerate(self.way_class_weight_list):
            DBControl().send_data("" \
                    "UPDATE %s SET cost=km*%d where kmh = %d;" \
                    % (self.temp_routing_table_name, weight, (index+1)) )
        # blocked ways
        DBControl().send_data("" \
                "UPDATE %s SET cost=km*(-1) WHERE osm_id = ANY('{%s}');" \
                % (self.temp_routing_table_name, ','.join(str(x) for x in self.blocked_ways)) )
        # add table index and recreate source and target columns
        t12 = time.time()
        DBControl().send_data("" \
                "ALTER TABLE ONLY %s ADD CONSTRAINT pkey_%s PRIMARY KEY (id);" \
                "CREATE INDEX idx_%s_source ON %s USING btree (source);" \
                "CREATE INDEX idx_%s_target ON %s USING btree (target);" \
                "CREATE INDEX idx_%s_osm_source_id ON %s USING btree (osm_source_id);" \
                "CREATE INDEX idx_%s_osm_target_id ON %s USING btree (osm_target_id);" \
                "CREATE INDEX idx_%s_geom_way ON %s USING gist (geom_way);" \
                "ALTER TABLE %s CLUSTER ON idx_%s_geom_way;" \
                "SELECT recreate_vertex_of_routing_table('%s');" \
                "ANALYZE %s;" \
                % (self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name))
        t2 = time.time()
        self.route_logger.append_to_log("Temp table creation: %.2f (%.2f / %.2f / %.2f\nnumber of rows = %d" \
                % (t2-t1, t11-t1, t12-t11, t2-t12, number_of_table_rows), True)
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))

        # get start and destination vertex
        start_vertex_list = self.get_nearest_vertex( start_point['lat'], start_point['lon'])
        if start_vertex_list.__len__() == 0 or Config().has_session_id_to_remove(self.session_id):
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            if start_vertex_list.__len__() == 0:
                self.route_logger.append_to_log("Found no start vertex", True)
                raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("footway_creator", "foot_route_creation_failed"))
            else:
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("message", "process_canceled"))
        dest_vertex_list = self.get_nearest_vertex( dest_point['lat'], dest_point['lon'])
        if dest_vertex_list.__len__() == 0 or Config().has_session_id_to_remove(self.session_id):
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            if dest_vertex_list.__len__():
                self.route_logger.append_to_log("Found no destination vertex", True)
                raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("footway_creator", "foot_route_creation_failed"))
            else:
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("message", "process_canceled"))
        t3 = time.time()
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))

        # route calculation
        best_route = RouteFootwayCreator.RawRoute([], None, None)
        max_vertex_list_length = start_vertex_list.__len__()
        if max_vertex_list_length < dest_vertex_list.__len__():
            max_vertex_list_length = dest_vertex_list.__len__()
        print "length = %d (%d / %d)" % (max_vertex_list_length, start_vertex_list.__len__(), dest_vertex_list.__len__())
        for x in range(0, max_vertex_list_length):
            for y in range(0, x+1):
                if x < start_vertex_list.__len__() and y < dest_vertex_list.__len__() \
                        and best_route.cost == 1000000:
                    result = DBControl().fetch_data("" \
                            "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                                "'select id, source, target, cost from %s', %d, %d, false, false)" \
                            % (self.temp_routing_table_name,
                                start_vertex_list[x].point_id, dest_vertex_list[y].point_id))
                    if any(result):
                        best_route = RouteFootwayCreator.RawRoute(result, start_vertex_list[x], dest_vertex_list[y])
                        self.route_logger.append_to_log(
                                "%d  %d    Cost: %.2f\n    start: %s\n    dest: %s" % (x, y, best_route.cost,
                                    start_vertex_list[x].__str__(), dest_vertex_list[y].__str__()), True)
                if y < start_vertex_list.__len__() and x < dest_vertex_list.__len__() \
                        and x != y and best_route.cost == 1000000:
                    result = DBControl().fetch_data("" \
                            "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                                "'select id, source, target, cost from %s', %d, %d, false, false)" \
                            % (self.temp_routing_table_name,
                                start_vertex_list[y].point_id, dest_vertex_list[x].point_id))
                    if any(result):
                        best_route = RouteFootwayCreator.RawRoute(result, start_vertex_list[y], dest_vertex_list[x])
                        self.route_logger.append_to_log(
                                "%d  %d    Cost: %.2f\n    start: %s\n    dest: %s" % (y, x, best_route.cost,
                                    start_vertex_list[y].__str__(), dest_vertex_list[x].__str__()), True)
        if Config().has_session_id_to_remove(self.session_id):
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))
        if best_route.cost == 1000000:
            result = DBControl().fetch_data("" \
                    "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                        "'select id, source, target, km AS cost from %s WHERE kmh != 7', %d, %d, false, false)" \
                    % (self.temp_routing_table_name,
                        start_vertex_list[0].point_id, dest_vertex_list[0].point_id))
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            if any(result):
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("footway_creator", "foot_route_creation_failed_way_classes_missing"))
            else:
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("message", "foot_route_creation_failed_no_existing_way"))
        t4 = time.time()
        self.route_logger.append_to_log("routing algorithm: %.2f" % (t4-t3), True)

        for r in best_route.route:
            if r['edge_id'] == -1:
                continue
            part = DBControl().fetch_data("SELECT * from %s where id=%d" \
                    % (self.temp_routing_table_name, r['edge_id']))[0]
    
            # exception for the first route segment
            # add start point of route first
            if part['source'] == best_route.start_vertex_tuple.point_id:
                print "start point added"
                # check if current point is an intersection
                next_point = self.poi.create_intersection_by_id(part['osm_source_id'])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(part['osm_source_id'])
                self.route.append(next_point)
                last_target_id = part['source']
            elif part['target'] == best_route.start_vertex_tuple.point_id:
                print "target point added"
                # check if current point is an intersection
                next_point = self.poi.create_intersection_by_id(part['osm_target_id'])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(part['osm_target_id'])
                self.route.append(next_point)
                last_target_id = part['target']
    
            # create next point
            if last_target_id == part['source']:
                next_point = self.poi.create_intersection_by_id(part['osm_target_id'])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(part['osm_target_id'])
                reverse = False
                last_target_id = part['target']
            else:
                next_point = self.poi.create_intersection_by_id(part['osm_source_id'])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(part['osm_source_id'])
                reverse = True
                last_target_id = part['source']
            # create next segment
            next_segment = self.poi.create_way_segment_by_id(part['osm_id'], reverse )
            next_segment['way_class'] = part['kmh']
            for point in self.get_route_segment_sub_points(part['id'], reverse) + [next_point]:
                self.add_point_to_route(point, next_segment.copy())
            # check for cancel command
            if Config().has_session_id_to_remove(self.session_id):
                raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))
        t5 = time.time()
        self.route_logger.append_to_log( json.dumps( self.route, indent=4, encoding="utf-8") )
        self.route_logger.append_to_log("\n-------------\n")

        # if no route was found, just use the direct connection between start and destination
        if self.route.__len__() <= 1:
            segment = {"name":self.translator.translate("footway_creator", "direct_connection"),
                    "type":"footway", "sub_type":"", "way_id":-1}
            segment['bearing'] = geometry.bearing_between_two_points( start_point['lat'], start_point['lon'], dest_point['lat'], dest_point['lon'])
            segment['distance'] = geometry.distance_between_two_points( start_point['lat'], start_point['lon'], dest_point['lat'], dest_point['lon'])
            self.route.append(start_point)
            self.route.append(segment)
            self.route.append(dest_point)
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            return self.route

        # add start point
        first_segment = None
        distance_start_p0 = geometry.distance_between_two_points(
                start_point['lat'], start_point['lon'],
                self.route[0]['lat'], self.route[0]['lon'])
        bearing_start_p0 = geometry.bearing_between_two_points(
                start_point['lat'], start_point['lon'],
                self.route[0]['lat'], self.route[0]['lon'])
        bearing_p0_p1 = self.route[1]['bearing']
        turn = geometry.turn_between_two_segments(
                bearing_p0_p1, bearing_start_p0)
        print "start: turn = %d, distance = %d" % (turn, distance_start_p0)
        print "start tuple: %s" % best_route.start_vertex_tuple.__str__()
        if distance_start_p0 <= 5:
            print "small dist, replaced start point"
            self.route[0] = start_point
        elif best_route.start_vertex_tuple.way_distance <= 5 \
                or (best_route.start_vertex_tuple.way_class in [1,2] and best_route.start_vertex_tuple.way_distance <= 15):
            if turn >= 158 and turn <= 202:
                print "replaced first intersection with start point"
                self.route[1]['distance'] -= distance_start_p0
                self.route[0] = start_point
            elif self.important_intersection(self.route[0]) == False \
                    and (turn <= 22 or turn >= 338):
                print "deleted first intersection, not important + straight ahead"
                self.route[1]['distance'] += distance_start_p0
                self.route[0] = start_point
            else:
                print "added known first segment"
                first_segment = self.poi.create_way_segment_by_id(
                        best_route.start_vertex_tuple.way_id)
        else:
            print "added placeholder first segment"
            first_segment = {"name":self.translator.translate("footway_creator", "first_segment"),
                    "type":"footway", "sub_type":"", "way_id":-1, "pois":[]}
        # should we add a first segment?
        if first_segment != None:
            print "really added"
            self.route[0]['turn'] = turn
            first_segment['bearing'] = bearing_start_p0
            first_segment['distance'] = distance_start_p0
            self.route.insert(0, first_segment)
            self.route.insert(0, start_point)

        # destination point
        distance_plast_dest = geometry.distance_between_two_points(
                self.route[-1]['lat'], self.route[-1]['lon'],
                dest_point['lat'], dest_point['lon'])
        bearing_plast_dest = geometry.bearing_between_two_points(
                self.route[-1]['lat'], self.route[-1]['lon'],
                dest_point['lat'], dest_point['lon'])
        turn = geometry.turn_between_two_segments(
                bearing_plast_dest, self.route[-2]['bearing'])
        print "destination: turn = %d, distance = %d" % (turn, distance_plast_dest)
        print "dest tuple: %s" % best_route.dest_vertex_tuple.__str__()
        if distance_plast_dest <= 5:
            print "small dist, replaced dest point"
            self.route[-1] = dest_point
        elif best_route.dest_vertex_tuple.way_distance <= 5 \
                or (best_route.dest_vertex_tuple.way_class in [1,2] and best_route.dest_vertex_tuple.way_distance <= 15):
            if turn >= 158 and turn <= 202:
                # delete last route point, if you should turn around
                print "replaced last intersection with destination point, turn around"
                self.route[-2]['distance'] -= distance_plast_dest
                self.route[-1] = dest_point
            elif self.important_intersection(self.route[-1]) == False \
                    and (turn <= 22 or turn >= 338):
                print "deleted last intersection, not important + straight ahead"
                self.route[-2]['distance'] += distance_plast_dest
                self.route[-1] = dest_point
            else:
                print "added known last segment"
                dest_segment = self.poi.create_way_segment_by_id(
                        best_route.dest_vertex_tuple.way_id)
                self.add_point_to_route(dest_point, dest_segment)
        else:
            print "added placeholder last segment"
            dest_segment = {"name":self.translator.translate("footway_creator", "last_segment"),
                    "type":"footway", "sub_type":"", "way_id":-1, "pois":[]}
            self.add_point_to_route(dest_point, dest_segment)
        t6 = time.time()

        # print time overview
        DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
        self.route_logger.append_to_log(
                "1. temp table: %.2f\n" \
                "2. vertex calculation: %.2f\n" \
                "3. route calculation: %.2f\n" \
                "4. add route points: %.2f\n" \
                "5. add start and destination: %.2f\n" \
                "summary: %.2f" \
                % (t2-t1, t3-t2, t4-t3, t5-t4, t6-t5, t6-t1), True)
        return self.route

    def follow_this_way(self, start_point, way_id, bearing, add_all_intersections):
        self.route = []
        way = DBControl().fetch_data("SELECT nodes from ways where id = %d" % way_id)[0]
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))
        # find nearest way point
        min_dist = 1000000
        id_index = 0
        i = 0
        for id in way['nodes']:
            wp = DBControl().fetch_data("SELECT  ST_y(geom) as lat, ST_X(geom) as lon from nodes where id = %d" % id)[0]
            dist = geometry.distance_between_two_points(start_point['lat'], start_point['lon'], wp['lat'], wp['lon'])
            if dist < min_dist:
                min_dist = dist
                id_index = i
            i += 1
        if id_index == 0:
            prev = DBControl().fetch_data("SELECT  ST_y(geom) as lat, ST_X(geom) as lon from nodes where id = %d" % way['nodes'][id_index])[0]
            next = DBControl().fetch_data("SELECT  ST_y(geom) as lat, ST_X(geom) as lon from nodes where id = %d" % way['nodes'][id_index+1])[0]
        else:
            prev = DBControl().fetch_data("SELECT  ST_y(geom) as lat, ST_X(geom) as lon from nodes where id = %d" % way['nodes'][id_index-1])[0]
            next = DBControl().fetch_data("SELECT  ST_y(geom) as lat, ST_X(geom) as lon from nodes where id = %d" % way['nodes'][id_index])[0]
        bearing_difference = geometry.bearing_between_two_points(prev['lat'], prev['lon'], next['lat'], next['lon']) - bearing
        if bearing_difference < 0:
            bearing_difference += 360
        if bearing_difference < 90 or bearing_difference >= 270:
            for index in range( id_index, way['nodes'].__len__()):
                next_point = self.poi.create_intersection_by_id(way['nodes'][index])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(way['nodes'][index])
                next_segment = self.poi.create_way_segment_by_id(way_id)
                self.add_point_to_route(next_point, next_segment, add_all_intersections)
            last_node_id = way['nodes'][-1]
        else:
            for index in range( id_index, -1, -1):
                next_point = self.poi.create_intersection_by_id(way['nodes'][index])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(way['nodes'][index])
                next_segment = self.poi.create_way_segment_by_id(way_id, True)
                self.add_point_to_route(next_point, next_segment, add_all_intersections)
            last_node_id = way['nodes'][0]
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))

        last_way_properties = self.poi.create_way_segment_by_id(way_id)
        while True:
            found_next_part = False
            result = DBControl().fetch_data("SELECT  w.id, w.nodes \
                    from ways w join way_nodes wn on w.id = wn.way_id \
                    where wn.node_id = %d and wn.way_id != %d"
                    % (last_node_id, last_way_properties['way_id']))
            if result.__len__() == 0:
                break
            for way in result:
                next_way_properties = self.poi.create_way_segment_by_id(way['id'])
                if last_way_properties['name'] != next_way_properties['name']:
                    continue
                if last_node_id == way['nodes'][0]:
                    for index in range(1, way['nodes'].__len__()):
                        next_point = self.poi.create_intersection_by_id(way['nodes'][index])
                        if next_point == {}:
                            next_point = self.poi.create_way_point_by_id(way['nodes'][index])
                        next_segment = self.poi.create_way_segment_by_id(
                                last_way_properties['way_id'])
                        self.add_point_to_route(next_point, next_segment, add_all_intersections)
                    last_node_id = way['nodes'][-1]
                    last_way_properties = next_way_properties
                    found_next_part = True
                    break
                if last_node_id == way['nodes'][-1]:
                    for index in range( way['nodes'].__len__()-2, -1, -1):
                        next_point = self.poi.create_intersection_by_id(way['nodes'][index])
                        if next_point == {}:
                            next_point = self.poi.create_way_point_by_id(way['nodes'][index])
                        next_segment = self.poi.create_way_segment_by_id(
                                last_way_properties['way_id'], True)
                        self.add_point_to_route(next_point, next_segment, add_all_intersections)
                    last_node_id = way['nodes'][0]
                    last_way_properties = next_way_properties
                    found_next_part = True
                    break
            if found_next_part == False:
                break
            # check for cancel command
            if Config().has_session_id_to_remove(self.session_id):
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("message", "process_canceled"))
        return self.route

    def get_route_description(self, route):
        route_length = 0
        number_of_intersections = 0
        number_of_transport_segments = 0
        transport_seg_index = 0
        for index in range(1, route.__len__()-1):
            if index % 2 == 0:
                # route points
                if route[index]['type'] == "intersection":
                    number_of_intersections += 1
            else:
                # route segments
                if route[index]['type'] == "transport":
                    if transport_seg_index == 0:
                        transport_seg_index = index
                    number_of_transport_segments += 1
                if route[index]['type'] == "footway":
                    route_length += route[index]['distance']
        # return route description
        if number_of_transport_segments > 0:
            station = route[transport_seg_index-1]
            segment = route[transport_seg_index]
            time_till_departure = ((segment['departure_time_millis']/1000) - int(time.time())) / 60
            if number_of_transport_segments == 1:
                return self.translator.translate("footway_creator", "route_description_with_single_transport") \
                        % (route_length, number_of_intersections, time_till_departure,
                            station['name'], segment['line'], segment['direction'])
            else:
                return self.translator.translate("footway_creator", "route_description_with_multi_transport") \
                        % (route_length, number_of_intersections, number_of_transport_segments,
                            time_till_departure, station['name'], segment['line'], segment['direction'])
        else:
            return self.translator.translate("footway_creator", "route_description_without_transport") \
                    % (route_length, number_of_intersections)

    def add_point_to_route(self, next_point, next_segment, add_all_intersections=False):
        # calculate bearing of new segment
        try:
            next_segment['bearing'] = geometry.bearing_between_two_points(
                    self.route[-1]['lat'], self.route[-1]['lon'],
                    next_point['lat'], next_point['lon'])
        except IndexError as e:
            # if the route is still empty, add the next route point and exit
            self.route.append(next_point)
            return
        # try to find and delete unimportant intersections and way points
        try:
            turn = geometry.turn_between_two_segments(
                    next_segment['bearing'], self.route[-2]['bearing'])
            if (add_all_intersections == False \
                        or (add_all_intersections == True and self.route[-1]['type'] != "intersection")) \
                    and (turn <= 22 or turn >= 338) \
                    and self.route[-2]['name'] == next_segment['name'] \
                    and self.route[-2]['sub_type'] == next_segment['sub_type'] \
                    and self.important_intersection(self.route[-1], self.route[-2]) == False:
                # delete an unimportant waypoint or intersection
                del self.route[-2:]
        except IndexError as e:
            pass
        # find and delete zigzag
        try:
            turn = geometry.turn_between_two_segments(
                    next_segment['bearing'], self.route[-4]['bearing'])
            if add_all_intersections == False \
                    and (turn <= 22 or turn >= 338) \
                    and self.route[-2]['distance'] < 4 \
                    and self.important_intersection(self.route[-1], self.route[-2]) == False \
                    and self.important_intersection(self.route[-3], self.route[-4]) == False:
                del self.route[-4:]
        except IndexError as e:
            pass
        # delete double train intersection but leave first of two intersections
        try:
            turn = geometry.turn_between_two_segments(
                    next_segment['bearing'], self.route[-4]['bearing'])
            if add_all_intersections == False \
                    and (turn <= 22 or turn >= 338) \
                    and self.route[-2]['distance'] < 5 \
                    and ( \
                        self.translator.translate("railway", "tram") in self.route[-1]['name'] \
                        or self.translator.translate("railway", "rail") in self.route[-1]['name'] \
                        ) \
                    and ( \
                        self.translator.translate("railway", "tram") in self.route[-3]['name'] \
                        or self.translator.translate("railway", "rail") in self.route[-3]['name'] \
                        ):
                del self.route[-2:]
        except IndexError as e:
            pass
        # calculate the updated distance and bearing to the potentially new prev point
        next_segment['bearing'] = geometry.bearing_between_two_points(
                self.route[-1]['lat'], self.route[-1]['lon'],
                next_point['lat'], next_point['lon'])
        next_segment['distance'] = geometry.distance_between_two_points(
                self.route[-1]['lat'], self.route[-1]['lon'],
                next_point['lat'], next_point['lon'])
        # update turn value
        try:
            if "turn" not in self.route[-1]:
                self.route[-1]['turn'] = geometry.turn_between_two_segments(
                        next_segment['bearing'], self.route[-2]['bearing'])
        except IndexError as e:
            pass
        # append new segment and point
        self.route.append(next_segment)
        self.route.append(next_point)

    def important_intersection(self, intersection, prev_segment = {}):
        if intersection.has_key("sub_points") == False:
            return False
        classes = [ self.translator.translate("highway", "primary"), self.translator.translate("highway", "primary_link"),
            self.translator.translate("highway", "secondary"), self.translator.translate("highway", "secondary_link"),
            self.translator.translate("highway", "tertiary"), self.translator.translate("highway", "tertiary_link"),
            self.translator.translate("highway", "residential"), self.translator.translate("highway", "road"),
            self.translator.translate("highway", "unclassified"), self.translator.translate("highway", "living_street") ]
        big_streets = []
        tram_or_rail = False
        for sub_point in intersection['sub_points']:
            if sub_point['sub_type'] in classes and sub_point['name'] not in big_streets:
                big_streets.append(sub_point['name'])
            if sub_point['sub_type'] in [self.translator.translate("railway", "tram"), self.translator.translate("railway", "rail")]:
                tram_or_rail = True
        if big_streets.__len__() > 1:
            return True
        elif big_streets.__len__() > 0 \
                and prev_segment.has_key("sub_type") == True and prev_segment['sub_type'] not in classes:
            return True
        elif tram_or_rail == True:
            return True
        else:
            return False

    def get_route_segment_sub_points(self, routing_table_id, reverse):
        c_list = DBControl().fetch_data("" \
                "SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon " \
                "FROM (" \
                    "SELECT ST_PointN(geom_way, generate_series(1, ST_NPoints(geom_way))) AS geom " \
                    "FROM %s WHERE id = %d) AS points;" \
                % (self.temp_routing_table_name, routing_table_id))
        if reverse:
            c_list = c_list[::-1]
        point_list = []
        last_accepted_bearing = geometry.bearing_between_two_points(
                    c_list[0]['lat'], c_list[0]['lon'], c_list[1]['lat'], c_list[1]['lon'])
        for i in range(1, c_list.__len__()-1):
            new_bearing = geometry.bearing_between_two_points(
                    c_list[i]['lat'], c_list[i]['lon'], c_list[i+1]['lat'], c_list[i+1]['lon'])
            turn = geometry.turn_between_two_segments(
                    new_bearing, last_accepted_bearing)
            if turn > 22 and turn < 338:
                last_accepted_bearing = new_bearing
                point_list.append(self.poi.create_way_point(-1, c_list[i]['lat'], c_list[i]['lon'], {}))
        return point_list

    def get_nearest_vertex(self, lat, lon):
        start = time.time()
        # get vertex of nearest big street or -1 if noone is available
        try:
            big_street_vertex = DBControl().fetch_data("" \
                "SELECT source from %s " \
                        "WHERE kmh = ANY('{1,2}') AND osm_name != ''" \
                    "order by ST_DISTANCE(geom_way::geography, 'POINT(%f %f)'::geography) " \
                    "limit 1;" \
                    % (self.temp_routing_table_name, lon, lat))[0]['source']
        except IndexError as e:
            big_street_vertex = -1
        t1 = time.time()

        # get nearest way segments
        nearest_lines = DBControl().fetch_data("\
                SELECT id, osm_id, osm_name, osm_source_id, osm_target_id, source, target, kmh as type, x1, y1, x2, y2, \
                    ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) as way_distance \
                    from %s WHERE kmh != 7 AND get_bit(flags::bit(16), 5) = 0 \
                    ORDER BY ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) LIMIT 50" \
                % (lon, lat, self.temp_routing_table_name, lon, lat))
        # try to prefer railways if the user must cross them to reach destination
        if big_street_vertex > -1:
            try:
                nearest_railway = DBControl().fetch_data("\
                        SELECT id, osm_id, osm_name, osm_source_id, osm_target_id, source, target, kmh as type, x1, y1, x2, y2, \
                            ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) as way_distance \
                            from %s \
                            WHERE (clazz = 18 OR clazz = 19) \
                                AND ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) < 5.0 \
                            ORDER BY ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) LIMIT 1" \
                        % (lon, lat, self.temp_routing_table_name, lon, lat, lon, lat))[0]
                # which point of the closest way segment is closer to the given start point
                source_dist = geometry.distance_between_two_points_as_float(
                        nearest_lines[0]['y1'], nearest_lines[0]['x1'], lat, lon)
                target_dist = geometry.distance_between_two_points_as_float(
                        nearest_lines[0]['y2'], nearest_lines[0]['x2'], lat, lon)
                if source_dist < target_dist:
                    nearest_lat = nearest_lines[0]['y1']
                    nearest_lon = nearest_lines[0]['x1']
                else:
                    nearest_lat = nearest_lines[0]['y2']
                    nearest_lon = nearest_lines[0]['x2']
                # test for impassable railway, if exists, add priviously found way, else
                # catch IndexError exception
                nearest_intersecting = DBControl().fetch_data("\
                        SELECT * FROM %s \
                        WHERE (clazz = 18 OR clazz = 19)AND osm_id != %d \
                            AND ST_Intersects(geom_way, \
                                ST_SetSRID(ST_MakeLine(ST_MakePoint(%f, %f), ST_MakePoint(%f, %f)), 4326)) = 't'" \
                        % (self.temp_routing_table_name, nearest_railway['osm_id'],
                            lon, lat, nearest_lon, nearest_lat))[0]
                print "jup     %f   %f" % (nearest_lon, nearest_lat)
                nearest_lines.insert(0, nearest_railway)
            except IndexError as e:
                pass
        # try to prefer streets with a max distance of 10 meters
        try:
            nearest_street = DBControl().fetch_data("\
                    SELECT id, osm_id, osm_name, osm_source_id, osm_target_id, source, target, kmh as type, x1, y1, x2, y2, \
                        ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) as way_distance \
                        from %s \
                        WHERE kmh != 7 AND osm_name != '' \
                            AND ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) < 10.0 \
                        ORDER BY ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography)" \
                    % (lon, lat, self.temp_routing_table_name, lon, lat, lon, lat))[0]
            if nearest_lines[0]['type'] == 7:
                nearest_lines.insert(1, nearest_street)
            else:
                nearest_lines.insert(0, nearest_street)
        except IndexError as e:
            pass
        t2 = time.time()

        tuple_list = []
        for index, line in enumerate(nearest_lines):
            # check, if source or target vertex of found edge is closer
            source_dist = geometry.distance_between_two_points_as_float(
                    line['y1'], line['x1'], lat, lon)
            target_dist = geometry.distance_between_two_points_as_float(
                    line['y2'], line['x2'], lat, lon)
            if source_dist < target_dist:
                tuple = RouteFootwayCreator.VertexTuple(line['source'], source_dist,
                        line['osm_id'], line['type'], line['way_distance'], line['osm_name'])
            else:
                tuple = RouteFootwayCreator.VertexTuple(line['target'], target_dist,
                        line['osm_id'], line['type'], line['way_distance'], line['osm_name'])
            if index < 7:
                print "id = %d;   dist = %d: %d/%d,   %d / %s (%d)" % (tuple.point_id,
                        line['way_distance'], source_dist, target_dist, line['type'],
                        line['osm_name'], line['osm_id'])
            # add id to id list
            if not any(x for x in tuple_list if x.point_id == tuple.point_id):
                # check if the way is connected to the main street network
                # but only if we found a big intersection
                # otherwise thake the id without verification
                if big_street_vertex == -1:
                    tuple_list.append(tuple)
                else:
                    raw_route = DBControl().fetch_data("" \
                            "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                                "'select id, source, target, km as cost from %s WHERE kmh != 7', %d, %d, false, false)" \
                            % (self.temp_routing_table_name, tuple.point_id, big_street_vertex))
                    if any(raw_route):
                        tuple_list.append(tuple)
            # break if the next point is more than 100 meters away or if you already have
            # at least 15 ids
            if len(tuple_list) >= 5 \
                    and (line['way_distance'] > 100 or len(tuple_list) >= 15):
                break
        end = time.time()
        print "%.2f, %.2f, %.2f" % (t1-start, t2-t1, end-t2)
        print "find vertex, time elapsed: %.2f" % (end-start)
        return tuple_list

    class VertexTuple:
        def __init__(self, point_id, point_distance, way_id, way_class, way_distance, way_name):
            self.point_id = point_id
            self.point_distance = point_distance
            self.way_id = way_id
            self.way_class = way_class
            self.way_distance = way_distance
            self.way_name = way_name
        def __str__(self):
            return "Name: %s (wc=%d),     distance: p=%d w=%d,     Point ID: %d,     Way ID: %d" \
                    % (self.way_name, self.way_class, self.point_distance, self.way_distance, self.point_id, self.way_id)

    class RawRoute:
        def __init__(self, route, start_vertex_tuple, dest_vertex_tuple):
            self.route = route
            self.start_vertex_tuple = start_vertex_tuple
            self.dest_vertex_tuple = dest_vertex_tuple
            if self.route.__len__() == 0:
                self.cost = 1000000
            else:
                self.cost = 0
                if self.start_vertex_tuple != None:
                    self.cost += self.start_vertex_tuple.point_distance*0.2
                    self.cost += self.start_vertex_tuple.way_distance*0.2
                if self.dest_vertex_tuple != None:
                    self.cost += self.dest_vertex_tuple.point_distance*0.2
                    self.cost += self.dest_vertex_tuple.way_distance*0.2
                for line in self.route:
                    self.cost += line['cost']

    class FootwayRouteCreationError(LookupError):
        """ is called, when the creation of the footway route failed """

