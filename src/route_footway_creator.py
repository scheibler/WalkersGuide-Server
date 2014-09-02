#!/usr/bin/python
# -*- coding: utf-8 -*-

from route_logger import RouteLogger
from db_control import DBControl
from translator import Translator
from config import Config
from poi import POI
import geometry
import time, json, operator

class RouteFootwayCreator:

    def __init__(self, session_id, route_logger_object, translator_object):
        self.session_id = session_id
        self.route_logger = route_logger_object
        self.translator = translator_object
        # routing parameters
        self.route = []
        self.routing_table_name = Config().get_param("routing_table")
        self.intersections_table_name = Config().get_param("intersection_table")
        self.poi = POI(session_id, translator_object)

    def find_footway_route(self, start_point, dest_point, factor):
        print "footway route creator"
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            Config().confirm_removement_of_session_id(self.session_id)
            return
        self.route = []
        last_target_id = -1
        errors = 0
        reverse = False
        t1 = time.time()
        raw_route = []
        if factor == 4:
            factor_column = "x4"
        elif factor == 3:
            factor_column = "x3"
        elif factor == 2:
            factor_column = "x2"
        elif factor == 1.5:
            factor_column = "x1_5"
        else:
            factor_column = "x1"

        # get start and destination vertex and calculate a route
        # start vertex
        start_vertex = -1
        t11 = time.time()
        intersection_vertex = DBControl().fetch_data("select de.source as intersection_vertex \
                from %s i join %s de on i.id = de.osm_source_id \
                where i.number_of_streets_with_name  > 1 \
                order by i.geom <-> 'point(%f %f)'::geometry \
                limit 1"
                % (self.intersections_table_name, self.routing_table_name, start_point['lon'],
                    start_point['lat']))[0]['intersection_vertex']
        t12 = time.time()
        self.route_logger.append_to_log("intersection vertex = %d" % intersection_vertex)
        for vertex in self.get_nearest_vertex( start_point['lat'], start_point['lon']):
            raw_route = DBControl().fetch_data("\
                    CREATE TEMP TABLE tmp_routing AS SELECT * FROM %s LIMIT 0; \
                    INSERT INTO tmp_routing \
                        SELECT * from %s \
                        ORDER BY geom_way <-> 'POINT(%f %f)'::geometry \
                        LIMIT 250; \
                    SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra( \
                        'select id, source, target, km as cost from tmp_routing', \
                    %d, %d, false, false)"
                    % (self.routing_table_name, self.routing_table_name, start_point['lon'],
                        start_point['lat'], vertex, intersection_vertex))
            self.route_logger.append_to_log("vertex = %d" % vertex)
            if raw_route.__len__() > 0:
                start_vertex = vertex
                break
        t13 = time.time()
        print "start vertexs = %.2f,:   intersection = %.2f,   routing = %.2f" % ((t13-t11), (t12-t11), (t13-t12))
        self.route_logger.append_to_log("start vertex = %d,   dauer: %.2f" % (start_vertex, (t13-t11)) )
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            Config().confirm_removement_of_session_id(self.session_id)
            return

        # dest vertex
        dest_vertex = -1
        t11 = time.time()
        intersection_vertex = DBControl().fetch_data("select de.source as intersection_vertex \
                from %s i join %s de on i.id = de.osm_source_id \
                where i.number_of_streets_with_name  > 1 \
                order by i.geom <-> 'point(%f %f)'::geometry \
                limit 1"
                % (self.intersections_table_name, self.routing_table_name, dest_point['lon'],
                    dest_point['lat']))[0]['intersection_vertex']
        t12 = time.time()
        self.route_logger.append_to_log("intersection vertex = %d" % intersection_vertex)
        for vertex in self.get_nearest_vertex( dest_point['lat'], dest_point['lon']):
            raw_route = DBControl().fetch_data("\
                    CREATE TEMP TABLE tmp_routing AS SELECT * FROM %s LIMIT 0; \
                    INSERT INTO tmp_routing \
                        SELECT * from %s \
                        ORDER BY geom_way <-> 'POINT(%f %f)'::geometry \
                        LIMIT 250; \
                    SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra( \
                        'select id, source, target, km as cost from tmp_routing', \
                    %d, %d, false, false)"
                    % (self.routing_table_name, self.routing_table_name, dest_point['lon'],
                        dest_point['lat'], vertex, intersection_vertex))
            self.route_logger.append_to_log("vertex = %d" % vertex)
            if raw_route.__len__() > 0:
                dest_vertex = vertex
                break
        t13 = time.time()
        print "dest vertex = %.2f,:   intersection = %.2f,   routing = %.2f" % ((t13-t11), (t12-t11), (t13-t12))
        self.route_logger.append_to_log("dest vertex = %d,   dauer: %.2f" % (dest_vertex, (t13-t11)) )
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            Config().confirm_removement_of_session_id(self.session_id)
            return

        # route calculation
        print "start_vertex = %d, dest_vertex = %d" % (start_vertex, dest_vertex)
        t2 = time.time()
        for number_of_lines in [5000, 15000, 30000, 50000, 100000, 250000]:
            # algorithms: pgr_dijkstra or pgr_astar
            print "numlines = %d" % number_of_lines
            self.route_logger.append_to_log("numlines = %d" % number_of_lines)
            raw_route = DBControl().fetch_data("\
                    CREATE TEMP TABLE tmp_routing AS SELECT * FROM %s LIMIT 0; \
                    INSERT INTO tmp_routing \
                        SELECT * from %s \
                        ORDER BY geom_way <-> 'POINT(%f %f)'::geometry \
                        LIMIT %d; \
                    SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra( \
                        'select rg.id, rg.source, rg.target, rg.km*(100-w.%s) as cost from tmp_routing rg, way_class_weights w \
                        where rg.kmh = w.id', \
                    %d, %d, false, false)"
                    % (self.routing_table_name, self.routing_table_name, start_point['lon'], start_point['lat'],
                        number_of_lines, factor_column, start_vertex, dest_vertex))
            if raw_route.__len__() > 0:
                break
            # check for cancel command
            if Config().has_session_id_to_remove(self.session_id):
                Config().confirm_removement_of_session_id(self.session_id)
                return
        t3 = time.time()
        print "routing algorithm: %.2f, (%.1f, %s)" % (t3-t2, factor, factor_column)
        self.route_logger.append_to_log("routing algorithm: %.2f, (%.1f, %s)" % (t3-t2, factor, factor_column))

        for r in raw_route:
            if r['edge_id'] == -1:
                continue
            part = DBControl().fetch_data("SELECT * from %s where id=%d" \
                    % (self.routing_table_name, r['edge_id']))[0]
    
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
                Config().confirm_removement_of_session_id(self.session_id)
                return
        # if no route was found, just use the direct connection between start and destination
        if self.route.__len__() <= 1:
            segment = {"name":self.translator.translate("footway_creator", "direct_connection"),
                    "type":"footway", "sub_type":"", "way_id":-1}
            segment['bearing'] = geometry.bearing_between_two_points( start_point['lat'], start_point['lon'], dest_point['lat'], dest_point['lon'])
            segment['distance'] = geometry.distance_between_two_points( start_point['lat'], start_point['lon'], dest_point['lat'], dest_point['lon'])
            self.route.append(start_point)
            self.route.append(segment)
            self.route.append(dest_point)
            return self.route
        t4 = time.time()
        self.route_logger.append_to_log( json.dumps( self.route, indent=4, encoding="utf-8") )
        self.route_logger.append_to_log("\n-------------\n")

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
            # if the first foute point is already the destination now, we need no turn value
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
        t5 = time.time()
        print "foot1: %.2f" % (t2-t1)
        print "foot2: %.2f" % (t3-t2)
        print "foot3: %.2f" % (t4-t3)
        print "foot4: %.2f" % (t5-t4)
        print "foot gesamt: %.2f" % (t5-t1)
        return self.route

    def follow_this_way(self, start_point, way_id, bearing, add_all_intersections):
        self.route = []
        way = DBControl().fetch_data("SELECT nodes from ways where id = %d" % way_id)[0]
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            Config().confirm_removement_of_session_id(self.session_id)
            return
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
            Config().confirm_removement_of_session_id(self.session_id)
            return

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
                Config().confirm_removement_of_session_id(self.session_id)
                return
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
        classes = [ self.translator.translate("highway", "primary"), self.translator.translate("highway", "secondary"),
            self.translator.translate("highway", "residential"), self.translator.translate("highway", "tertiary"),
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
        result= DBControl().fetch_data("\
                WITH closest_ways AS ( \
                    SELECT id, osm_name, osm_source_id, osm_target_id, source, target, kmh as type, x1, y1, x2, y2, geom_way \
                    from %s ORDER BY geom_way <-> 'POINT(%f %f)'::geometry \
                    LIMIT 100 \
                ) \
                SELECT id, osm_name, osm_source_id, osm_target_id, source, target, type, x1, y1, x2, y2 \
                from closest_ways ORDER BY ST_Distance(geom_way::geography, 'POINT(%f %f)'::geography)" \
                % (self.routing_table_name, lon, lat, lon, lat))
        t2 = time.time()
        #print "query = %.2f" % (t2-start)
        if result.__len__() == 0:
            return None
        else:
            nearest_lines = result
        tuple_list = []
        index = 0
        for line in nearest_lines:
            index += 1
            #if index < 9:
            #    print "index = %d, edge id = %d, source = %d, target = %d, type = %d, name = %s" \
            #            % (index, line['id'], line['source'], line['target'], line['type'], line['osm_name'])
            # check, if source or target vertex of found edge is closer
            t3 = time.time()
            result = DBControl().fetch_data("SELECT \
                    ST_Distance('POINT(%f %f)'::geography, 'POINT(%f %f)'::geography) AS dist \
                    from %s where (source = %d or target = %d) and clazz != 17 and clazz != 18" \
                    % (line['x1'], line['y1'], lon, lat, self.routing_table_name, line['source'], line['source']))
            t4 = time.time()
            #print "start vertex time = %.2f" % (t4-t3)
            if result.__len__() > 0:
                source_dist = result[0]['dist']
            else:
                source_dist = -1
            #if index < 4:
            #    print "source dist = %d" % source_dist
            result = DBControl().fetch_data("SELECT \
                    ST_Distance('POINT(%f %f)'::geography, 'POINT(%f %f)'::geography) AS dist \
                    from %s where (source = %d or target = %d) and (clazz != 17 and clazz != 18)" \
                    % (line['x2'], line['y2'], lon, lat, self.routing_table_name, line['target'], line['target']))
            if result.__len__() > 0:
                target_dist = result[0]['dist']
            else:
                target_dist = -1
            #if index < 4:
            #    print "target dist = %d" % target_dist
            if source_dist == -1 and target_dist == -1:
                #if index < 9:
                #    print "skipped"
                continue
            elif source_dist == -1:
                tuple_list.append(RouteFootwayCreator.VertexDistanceTuple(line['target'], target_dist, line['type']))
                #if index < 9:
                #    print "target added, source = -1"
            elif target_dist == -1:
                tuple_list.append(RouteFootwayCreator.VertexDistanceTuple(line['source'], source_dist, line['type']))
                #if index < 9:
                #    print "source added, target = -1"
            else:
                if source_dist < target_dist:
                    tuple_list.append(RouteFootwayCreator.VertexDistanceTuple(line['source'], source_dist, line['type']))
                    #if index < 9:
                    #    print "source added"
                else:
                    tuple_list.append(RouteFootwayCreator.VertexDistanceTuple(line['target'], target_dist, line['type']))
                    #if index < 9:
                    #    print "target added"
            if tuple_list.__len__() >= 20:
                break
        tuple_list.sort(key = operator.attrgetter('distance'))
        ids = []
        for tuple in tuple_list:
            if tuple.id not in ids:
                #print tuple
                ids.append(tuple.id)
        end = time.time()
        print "find vertiex time elapsed: %.2f" % (end-start)
        return ids

    class VertexDistanceTuple:
        def __init__(self, id, distance, type):
            self.id = id
            self.distance = distance
            self.type = type
        def __str__(self):
            return "ID = %d     dist = %d, type = %d" % (self.id, self.distance, self.type)
