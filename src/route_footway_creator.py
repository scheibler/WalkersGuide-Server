#!/usr/bin/python
# -*- coding: utf-8 -*-

from route_logger import RouteLogger
from db_control import DBControl
from translator import Translator
from config import Config
from poi import POI
import geometry
import time, json, operator, re

class RouteFootwayCreator:

    def __init__(self, session_id, route_logger_object, translator_object, indirection_factor, allowed_way_classes):
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
        #   4 = very, very, very bad way
        #   5 = impassable way
        weight_list = DBControl().fetch_data("SELECT %s as weight \
                    from way_class_weights;" % factor_column_name)
        # way classes: find them in the kmh column of the routing table
        #   wcw_id 2 -- list index 0 = class 1: big and unknown streets
        #   wcw_id 1 -- list index 1 = class 2: middle streets
        #   wcw_id 0 -- list index 2 = class 3: small streets
        #   wcw_id 1 -- list index 3 = class 4: paved ways
        #   wcw_id 2 -- list index 4 = class 5: unpaved ways
        #   wcw_id 2 -- list index 5 = class 6: steps
        #   wcw_id 3 -- list index 6 = class 7: unspecified cycleways
        #   wcw_id 4 -- list index 7 = class 8: impassable ways
        # initialize with all classes impassable
        self.way_class_weight_list = [ weight_list[4]['weight'] for x in range(8)]
        if allowed_way_classes.__contains__("big_streets"):
            # big streets: bad
            self.way_class_weight_list[0] = weight_list[2]['weight']
            # middle streets: neutral
            self.way_class_weight_list[1] = weight_list[1]['weight']
        if allowed_way_classes.__contains__("small_streets"):
            # small streets: good
            self.way_class_weight_list[2] = weight_list[0]['weight']
        if allowed_way_classes.__contains__("paved_ways"):
            # paved ways: neutral
            self.way_class_weight_list[3] = weight_list[1]['weight']
        if allowed_way_classes.__contains__("unpaved_ways"):
            # unpaved ways: bad
            self.way_class_weight_list[4] = weight_list[2]['weight']
            # unspecified cycleways: very, very, very bad
            self.way_class_weight_list[6] = weight_list[3]['weight']
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
        distance_between_start_and_dest = geometry.distance_between_two_points(
                start_point['lat'], start_point['lon'],
                dest_point['lat'], dest_point['lon'])
        center_point = {
                'lat' : (start_point['lat'] + dest_point['lat']) / 2,
                'lon' : (start_point['lon'] + dest_point['lon']) / 2 }
        # create temp table
        DBControl().send_data("" \
                "DROP TABLE IF EXISTS %s;" \
                "CREATE TABLE %s AS SELECT * FROM %s LIMIT 0;" \
                % (self.temp_routing_table_name, self.temp_routing_table_name, self.routing_table_name))
        # create row list array
        if distance_between_start_and_dest < 250:
            row_list = [1000, 3000]
        elif distance_between_start_and_dest < 500:
            row_list = [2500, 7500]
        elif distance_between_start_and_dest < 1000:
            row_list = [5000, 15000]
        elif distance_between_start_and_dest < 2000:
            row_list = [10000, 30000]
        elif distance_between_start_and_dest < 4000:
            row_list = [25000, 75000]
        else:
            row_list = [50000, 150000]
        # fill temp routing table
        for number_of_rows in row_list:
            t11 = time.time()
            DBControl().send_data("" \
                    "INSERT INTO %s " \
                        "SELECT * from %s " \
                        "ORDER BY geom_way <-> 'POINT(%f %f)'::geometry " \
                        "limit %d;" \
                    % (self.temp_routing_table_name, self.routing_table_name,
                        center_point['lon'], center_point['lat'], number_of_rows) )
            # get max distance from center
            t12 = time.time()
            result = DBControl().fetch_data("" \
                    "SELECT ST_DISTANCE(geom_way::geography, 'POINT(%f %f)'::geography)::integer AS distance " \
                        "from %s " \
                        "ORDER BY geom_way <-> 'POINT(%f %f)'::geometry DESC " \
                        "limit 1;" \
                    % (center_point['lon'], center_point['lat'],
                        self.temp_routing_table_name, center_point['lon'], center_point['lat']) )[0]
            t13 = time.time()
            self.route_logger.append_to_log(
                    "rows: %d;   distance: %d / %d;   time: %.2f (%.2f / %.2f)" \
                    % (number_of_rows, distance_between_start_and_dest,
                        result['distance'], t13-t11, t12-t11, t13-t12), True)
            if distance_between_start_and_dest < result['distance']:
                break
            # remove all lines from table
            DBControl().send_data("TRUNCATE  TABLE %s" \
                    % self.temp_routing_table_name)
            # check for cancel command
            if Config().has_session_id_to_remove(self.session_id):
                DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
                raise RouteFootwayCreator.FootwayRouteCreationError(
                    self.translator.translate("message", "process_canceled"))
        # check if temp routing table is empty
        number_of_table_rows = DBControl().fetch_data("SELECT count(*) from %s" \
                % self.temp_routing_table_name)[0]['count']
        if number_of_table_rows == 0:
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            self.route_logger.append_to_log("Routing table too small", True)
            raise RouteFootwayCreator.FootwayRouteCreationError(
                self.translator.translate("footway_creator", "foot_route_creation_failed"))
        # adapt cost column
        t14 = time.time()
        for index, weight in enumerate(self.way_class_weight_list):
            DBControl().send_data("" \
                    "UPDATE %s SET cost=km*%d where kmh = %d;" \
                    % (self.temp_routing_table_name, weight, (index+1)) )
        # add table index
        t15 = time.time()
        DBControl().send_data("" \
                "ALTER TABLE ONLY %s ADD CONSTRAINT pkey_%s PRIMARY KEY (id);" \
                "CREATE INDEX idx_%s_source ON %s USING btree (source);" \
                "CREATE INDEX idx_%s_target ON %s USING btree (target);" \
                "CREATE INDEX idx_%s_osm_source_id ON %s USING btree (osm_source_id);" \
                "CREATE INDEX idx_%s_osm_target_id ON %s USING btree (osm_target_id);" \
                "CREATE INDEX idx_%s_geom_way ON %s USING gist (geom_way);" \
                "ALTER TABLE %s CLUSTER ON idx_%s_geom_way;" \
                "ANALYZE %s;" \
                % (self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name, self.temp_routing_table_name,
                    self.temp_routing_table_name))
        t2 = time.time()
        self.route_logger.append_to_log("Temp table creation: %.2f (%.2f / %.2f / %.2f" \
                % (t2-t1, t14-t1, t15-t14, t2-t15), True)

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
        #self.route_logger.append_to_log(
        #        "start_vertex = %d, dest_vertex = %d, duration = %.2f" \
        #        % (start_vertex, dest_vertex, (t3-t2)), True)

        # route calculation
        raw_route = []
        max_vertex_list_length = start_vertex_list.__len__()
        if max_vertex_list_length < dest_vertex_list.__len__():
            max_vertex_list_length = dest_vertex_list.__len__()
        print "length = %d (%d / %d)" % (max_vertex_list_length, start_vertex_list.__len__(), dest_vertex_list.__len__())
        for x in range(0, max_vertex_list_length):
            for y in range(0, x+1):
                if x < start_vertex_list.__len__() and y < dest_vertex_list.__len__() \
                        and raw_route.__len__() == 0:
                    print "%d  %d" % (x, y)
                    raw_route = DBControl().fetch_data("" \
                            "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                                "'select id, source, target, cost from %s', %d, %d, false, false)" \
                            % (self.temp_routing_table_name,
                                start_vertex_list[x], dest_vertex_list[y]))
                    if raw_route.__len__() > 0:
                        start_vertex = start_vertex_list[x]
                        dest_vertex = dest_vertex_list[y]
                if y < start_vertex_list.__len__() and x < dest_vertex_list.__len__() \
                        and x != y and raw_route.__len__() == 0:
                    print "%d  %d ." % (y, x)
                    raw_route = DBControl().fetch_data("" \
                            "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                                "'select id, source, target, cost from %s', %d, %d, false, false)" \
                            % (self.temp_routing_table_name,
                                start_vertex_list[y], dest_vertex_list[x]))
                    if raw_route.__len__() > 0:
                        start_vertex = start_vertex_list[y]
                        dest_vertex = dest_vertex_list[x]
                if Config().has_session_id_to_remove(self.session_id):
                    DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
                    raise RouteFootwayCreator.FootwayRouteCreationError(
                            self.translator.translate("message", "process_canceled"))
        if raw_route.__len__() == 0:
            raw_route = DBControl().fetch_data("" \
                    "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                        "'select id, source, target, km AS cost from %s', %d, %d, false, false)" \
                    % (self.temp_routing_table_name,
                        start_vertex_list[0], dest_vertex_list[0]))
            DBControl().send_data("DROP TABLE %s;" % self.temp_routing_table_name)
            if raw_route.__len__() > 0:
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("footway_creator", "foot_route_creation_failed_way_classes_missing"))
            else:
                raise RouteFootwayCreator.FootwayRouteCreationError(
                        self.translator.translate("message", "foot_route_creation_failed_no_existing_way"))
        t4 = time.time()
        self.route_logger.append_to_log("routing algorithm: %.2f" % (t4-t3), True)

        for r in raw_route:
            if r['edge_id'] == -1:
                continue
            part = DBControl().fetch_data("SELECT * from %s where id=%d" \
                    % (self.temp_routing_table_name, r['edge_id']))[0]
    
            # exception for the first route segment
            # add start point of route first
            if part['source'] == start_vertex:
                print "start point added"
                # check if current point is an intersection
                next_point = self.poi.create_intersection_by_id(part['osm_source_id'])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(part['osm_source_id'])
                self.route.append(next_point)
                last_target_id = part['source']
            elif part['target'] == start_vertex:
                print "target point added"
                # check if current point is an intersection
                next_point = self.poi.create_intersection_by_id(part['osm_target_id'])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(part['osm_target_id'])
                self.route.append(next_point)
                last_target_id = part['target']
    
            # add target point
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
            self.add_point_to_route(next_point, part['osm_id'], reverse)
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

        # else add start and destination points
        # start
        distance_start_p0 = geometry.distance_between_two_points( start_point['lat'], start_point['lon'], self.route[0]['lat'], self.route[0]['lon'])
        if distance_start_p0 <= 5:
            self.route.__delitem__(0)
            self.route.insert(0, start_point)
        else:
            bearing_start_p0 = geometry.bearing_between_two_points( start_point['lat'], start_point['lon'], self.route[0]['lat'], self.route[0]['lon'])
            bearing_p0_p1 = self.route[1]['bearing']
            turn = bearing_p0_p1 - bearing_start_p0
            if turn < 0:
                turn += 360
            # find way id for first segment to the start point
            result = DBControl().fetch_data("\
                    WITH closest_ways AS ( \
                        SELECT id, tags->'highway' as highway, tags->'name' as name, bbox, linestring \
                        from ways ORDER BY linestring <-> 'POINT(%f %f)'::geometry \
                        LIMIT 5 \
                    ) \
                    SELECT id, highway, name, bbox, linestring from closest_ways \
                    where st_contains( bbox, ST_SETSRID(ST_Point(%f, %f),4326) ) = true \
                    and highway LIKE '%%' \
                    and ST_Distance(linestring::geography, 'POINT(%f %f)'::geography) < 10.0 \
                    ORDER BY ST_Distance(linestring::geography, 'POINT(%f %f)'::geography)" \
                    % (start_point['lon'], start_point['lat'], start_point['lon'], start_point['lat'],
                        start_point['lon'], start_point['lat'], start_point['lon'], start_point['lat']))
            if result.__len__() > 0:
                new_way_id = result[0]['id']
            else:
                new_way_id = -1
            collected_pois = []
            # maybe delete first route point, if...
            if turn > 150 and turn < 210:
                # turn around
                new_way_id = self.route[1]['way_id']
                collected_pois = self.route[1]['pois']
                self.route.__delitem__(0)
                self.route.__delitem__(0)
            if turn < 30 or turn > 330:
                if new_way_id == -1:
                    new_way_id = self.route[1]['way_id']
                if self.important_intersection(self.route[0]) == False:
                    # straightforward at the same way
                    collected_pois = self.route[1]['pois']
                    self.route.__delitem__(0)
                    self.route.__delitem__(0)
            if new_way_id > -1:
                first_segment = self.poi.create_way_segment_by_id( new_way_id )
            else:
                first_segment = {"name":self.translator.translate("footway_creator", "first_segment"),
                        "type":"footway", "sub_type":"", "way_id":-1}
            first_segment['bearing'] = geometry.bearing_between_two_points( start_point['lat'], start_point['lon'], self.route[0]['lat'], self.route[0]['lon'])
            first_segment['distance'] = geometry.distance_between_two_points( start_point['lat'], start_point['lon'], self.route[0]['lat'], self.route[0]['lon'])
            first_segment['pois'] = collected_pois
            # if the first route point is already the destination now, we need no turn value
            if self.route.__len__() > 1:
                turn = self.route[1]['bearing'] - first_segment['bearing']
                if turn < 0:
                    turn += 360
                self.route[0]['turn'] = turn
            self.route.insert(0, first_segment)
            self.route.insert(0, start_point)

        # destination
        distance_plast_dest = geometry.distance_between_two_points( self.route[-1]['lat'], self.route[-1]['lon'], dest_point['lat'], dest_point['lon'])
        print "distance last = %d" % distance_plast_dest
        if distance_plast_dest <= 5:
            self.route.__delitem__(-1)
            self.route.append(dest_point)
        else:
            bearing_plast_dest = geometry.bearing_between_two_points( self.route[-1]['lat'], self.route[-1]['lon'], dest_point['lat'], dest_point['lon'])
            bearing_psecondlast_plast = self.route[-2]['bearing']
            turn = bearing_plast_dest - bearing_psecondlast_plast
            if turn < 0:
                turn += 360
            # find way id for last segment to the destination point
            result = DBControl().fetch_data("\
                    WITH closest_ways AS ( \
                        SELECT id, tags->'highway' as highway, tags->'name' as name, bbox, linestring \
                        from ways ORDER BY linestring <-> 'POINT(%f %f)'::geometry \
                        LIMIT 5 \
                    ) \
                    SELECT id, highway, name, bbox, linestring from closest_ways \
                    where st_contains( bbox, ST_SETSRID(ST_Point(%f, %f),4326) ) = true \
                    and highway LIKE '%%' \
                    and ST_Distance(linestring::geography, 'POINT(%f %f)'::geography) < 10.0 \
                    ORDER BY ST_Distance(linestring::geography, 'POINT(%f %f)'::geography)" \
                    % (dest_point['lon'], dest_point['lat'], dest_point['lon'], dest_point['lat'],
                        dest_point['lon'], dest_point['lat'], dest_point['lon'], dest_point['lat']))
            if result.__len__() > 0:
                new_way_id = result[0]['id']
            else:
                new_way_id = -1
            collected_pois = []
            # maybe delete last route point, if...
            if turn > 150 and turn < 210:
                # turn around
                new_way_id = self.route[-2]['way_id']
                collected_pois = self.route[-2]['pois']
                self.route.__delitem__(-1)
                self.route.__delitem__(-1)
            if turn < 30 or turn > 330:
                if new_way_id == -1:
                    new_way_id = self.route[-2]['way_id']
                if self.important_intersection(self.route[-1]) == False:
                    # straightforward at the same way
                    collected_pois = self.route[-2]['pois']
                    self.route.__delitem__(-1)
                    self.route.__delitem__(-1)
            # add last segment and destination point
            if new_way_id > -1:
                last_segment = self.poi.create_way_segment_by_id( new_way_id )
            else:
                last_segment = {"name":self.translator.translate("footway_creator", "last_segment"),
                        "type":"footway", "sub_type":"", "way_id":-1}
            last_segment['bearing'] = geometry.bearing_between_two_points( self.route[-1]['lat'], self.route[-1]['lon'], dest_point['lat'], dest_point['lon'])
            last_segment['distance'] = geometry.distance_between_two_points( self.route[-1]['lat'], self.route[-1]['lon'], dest_point['lat'], dest_point['lon'])
            last_segment['pois'] = collected_pois
            # if the first foute point is already the start now, we need no turn value
            if self.route.__len__() > 1:
                turn = last_segment['bearing'] - self.route[-2]['bearing']
                if turn < 0:
                    turn += 360
                self.route[-1]['turn'] = turn
            self.route.append(last_segment)
            self.route.append(dest_point)
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
                self.add_point_to_route(next_point, way_id, False, add_all_intersections)
            last_node_id = way['nodes'][-1]
        else:
            for index in range( id_index, -1, -1):
                next_point = self.poi.create_intersection_by_id(way['nodes'][index])
                if next_point == {}:
                    next_point = self.poi.create_way_point_by_id(way['nodes'][index])
                self.add_point_to_route(next_point, way_id, True, add_all_intersections)
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
                        self.add_point_to_route(next_point, last_way_properties['way_id'], False, add_all_intersections)
                    last_node_id = way['nodes'][-1]
                    last_way_properties = next_way_properties
                    found_next_part = True
                    break
                if last_node_id == way['nodes'][-1]:
                    for index in range( way['nodes'].__len__()-2, -1, -1):
                        next_point = self.poi.create_intersection_by_id(way['nodes'][index])
                        if next_point == {}:
                            next_point = self.poi.create_way_point_by_id(way['nodes'][index])
                        self.add_point_to_route(next_point, last_way_properties['way_id'], True, add_all_intersections)
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

    def add_point_to_route(self, next_point, way_id, reverse, add_all_intersections=False):
        # add new point to the route array
        if self.route.__len__() == 0:
            self.route.append(next_point)
        elif self.route.__len__() == 1:
            prev_point = self.route[-1]
            next_segment = self.poi.create_way_segment_by_id( way_id, reverse )
            next_segment['bearing'] = geometry.bearing_between_two_points( prev_point['lat'], prev_point['lon'], next_point['lat'], next_point['lon'])
            next_segment['distance'] = geometry.distance_between_two_points( prev_point['lat'], prev_point['lon'], next_point['lat'], next_point['lon'])
            self.route.append(next_segment)
            self.route.append(next_point)
        else:
            prev_segment = self.route[-2]
            prev_point = self.route[-1]
            next_segment = self.poi.create_way_segment_by_id( way_id, reverse )
            next_segment['bearing'] = geometry.bearing_between_two_points( prev_point['lat'], prev_point['lon'], next_point['lat'], next_point['lon'])
            next_segment['distance'] = geometry.distance_between_two_points( prev_point['lat'], prev_point['lon'], next_point['lat'], next_point['lon'])
            # get turn between last and next segment in degree
            turn = next_segment['bearing'] - prev_segment['bearing']
            if turn < 0:
                turn += 360
            self.route[-1]['turn'] = turn
            # decide, if the previous point is important for routing
            point_is_important = False
            if next_segment['distance'] < 1:
                point_is_important = False
            elif turn > 22 and turn < 338:
                point_is_important = True
            elif prev_segment['name'] != next_segment['name'] or prev_segment['sub_type'] != next_segment['sub_type']:
                # print "%s - %s;     %s - %s" % (prev_segment['name'], next_segment['name'], prev_segment['sub_type'], next_segment['sub_type'])
                point_is_important = True
            elif prev_point.has_key("sub_points") == True:
                if add_all_intersections == True:
                    point_is_important = True
                else:
                    # check for a bigger street
                    point_is_important = self.important_intersection( prev_point )
            ######
            if point_is_important == False:
                collected_pois = prev_segment['pois']
                if prev_point['type'] == "intersection":
                    collected_pois.append(prev_point)
                self.route.__delitem__(-1)
                self.route.__delitem__(-1)
                prev_point = self.route[-1]
                next_segment = self.poi.create_way_segment_by_id( way_id, reverse )
                next_segment['bearing'] = geometry.bearing_between_two_points( prev_point['lat'], prev_point['lon'], next_point['lat'], next_point['lon'])
                next_segment['distance'] = geometry.distance_between_two_points( prev_point['lat'], prev_point['lon'], next_point['lat'], next_point['lon'])
                next_segment['pois'] = collected_pois
            self.route.append(next_segment)
            self.route.append(next_point)

    def important_intersection(self, intersection ):
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
        if big_streets.__len__() > 1 or tram_or_rail == True:
            return True
        return False

    def get_nearest_vertex(self, lat, lon):
        start = time.time()
        # get vertex of nearest big intersection
        intersection_vertex = DBControl().fetch_data("" \
                "SELECT source from %s " \
                "where EXISTS(" \
                    "select 1 from %s " \
                    "where (id = osm_source_id or id = osm_target_id) " \
                        "and number_of_streets_with_name > 1) = 't' " \
                "order by ST_DISTANCE(geom_way::geography, 'POINT(%f %f)'::geography) " \
                "limit 1;" \
                % (self.temp_routing_table_name, self.intersections_table_name,
                    lon, lat))[0]['source']
        # get nearest way segments
        tuple_list = []
        nearest_lines = DBControl().fetch_data("\
                SELECT id, osm_name, osm_source_id, osm_target_id, source, target, kmh as type, x1, y1, x2, y2 \
                from %s WHERE cost > 0 \
                ORDER BY ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography) LIMIT 50" \
                % (self.temp_routing_table_name, lon, lat))
        for line in nearest_lines:
            # check, if source or target vertex of found edge is closer
            source_dist = geometry.distance_between_two_points_as_float(
                    line['y1'], line['x1'], lat, lon)
            target_dist = geometry.distance_between_two_points_as_float(
                    line['y2'], line['x2'], lat, lon)
            if source_dist < target_dist:
                tuple_list.append(RouteFootwayCreator.VertexDistanceTuple(line['source'], source_dist, line['type']))
            else:
                tuple_list.append(RouteFootwayCreator.VertexDistanceTuple(line['target'], target_dist, line['type']))
            #print "index = %d, edge id = %d, source = %d, target = %d, type = %d, name = %s" \
            #        % (index, line['id'], line['source'], line['target'], line['type'], line['osm_name'])
            #print "distances: %f / %f" % (source_dist, target_dist)
        tuple_list.sort(key = operator.attrgetter('distance'))
        # filter duplicate vertex ids
        ids = []
        for index, tuple in enumerate(tuple_list):
            if tuple.id not in ids:
                #print "Tuple %d: id = %d" % (index+1, tuple.id)
                raw_route = DBControl().fetch_data("" \
                        "SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(" \
                            "'select id, source, target, km as cost from %s', %d, %d, false, false)" \
                        % (self.temp_routing_table_name, tuple.id, intersection_vertex))
                if raw_route.__len__() > 0:
                    ids.append(tuple.id)
            # break if the next point is more than 250 meters away or if you already have
            # at least 10 ids
            if tuple.distance > 250 or ids.__len__() > 9:
                break
        end = time.time()
        print "find vertex, time elapsed: %.2f" % (end-start)
        return ids

    class VertexDistanceTuple:
        def __init__(self, id, distance, type):
            self.id = id
            self.distance = distance
            self.type = type
        def __str__(self):
            return "ID = %d     dist = %d, type = %d" % (self.id, self.distance, self.type)

    class FootwayRouteCreationError(LookupError):
        """ is called, when the creation of the footway route failed """

