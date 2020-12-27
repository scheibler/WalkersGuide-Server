#!/usr/bin/python
# -*- coding: utf-8 -*-

import json, logging, re, time
from psycopg2 import sql

from . import constants, geometry
from .config import Config
from .constants import ReturnCode
from .db_control import DBControl
from .helper import WebserverException
from .poi import POI
from .translator import Translator


class PedestrianRoute:

    def __init__(self, map_id, session_id, user_language,
            way_class_name_and_weight_map, way_ids_to_exclude):
        self.selected_db = DBControl(map_id)
        self.session_id = session_id
        self.translator = Translator(user_language)
        self.poi = POI(map_id, session_id, user_language)
        self.routing_table_name = Config().database.get("routing_table")
        self.temp_routing_table_name = "tmp_routing_%s" \
                % re.sub(r'[^a-zA-Z0-9]', '', self.session_id)
        # way class weights
        self.way_class_id_and_weight_map = {}
        for way_class in constants.supported_way_class_list:
            # way class id
            if way_class == "big_streets":
                way_class_id = 1
            elif way_class == "small_streets":
                way_class_id = 2
            elif way_class == "paved_ways":
                way_class_id = 3
            elif way_class == "unpaved_ways":
                way_class_id = 4
            elif way_class == "unclassified_ways":
                way_class_id = 5
            elif way_class == "steps":
                way_class_id = 6
            else:
                continue
            # way class weight
            try:
                weight = way_class_name_and_weight_map.get(way_class, 0.0)
            except Exception:
                weight = 0.0
            finally:
                if weight == 0.0:
                    # set to default
                    weight = 1.0
            # add to map
            self.way_class_id_and_weight_map[way_class_id] = weight
        logging.info(self.way_class_id_and_weight_map)
        # exclude the following way ids from routing
        self.way_ids_to_exclude = []
        if type(way_ids_to_exclude) is list:
            for way_id in way_ids_to_exclude:
                if type(way_id) is int:
                    self.way_ids_to_exclude.append(way_id)
        logging.info("exclude: {}".format(self.way_ids_to_exclude))


    def calculate_route(self, point_list):
        # validate point_list param
        if not point_list:
            raise WebserverException(ReturnCode.BAD_REQUEST, "no point list")
        elif type(point_list) is not list:
            raise WebserverException(ReturnCode.BAD_REQUEST, "invalid point list")
        for point in point_list:
            if type(point) is not dict \
                    or "type" not in point or point.get('type') not in constants.supported_route_point_object_list \
                    or "lat" not in point or type(point.get("lat")) is not float \
                    or point.get("lat") < -90.0 or point.get("lat") > 90.0 \
                    or "lon" not in point or type(point.get("lon")) is not float \
                    or point.get("lon") < -180.0 or point.get("lon") > 180.0:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "point {} is invalid".format(point))
        if len(point_list) < 2:
            raise WebserverException(ReturnCode.START_OR_DESTINATION_MISSING)

        # calculate route sections
        route = []
        for i in range(1, len(point_list)):
            section = self.calculate_route_section(point_list[i-1], point_list[i])
            # some via point corrections
            if route:
                # prevent via point duplication
                del route[-1]
                # append via point label
                section[0]['name'] = self.translator.translate(
                        "footway_creator", "via_point_label") % ((i-1), section[0]['name'])
            route += section
        # delete start point and first route segment, if it's a nameless one, just added as place holder
        if not route[1].get("sub_type"):
            route.__delitem__(0)        # start point
            route.__delitem__(0)        # placeholder segment
        # add missing turn values (via points)
        for i in range(0, len(route), 2):
            if "turn" not in route[i]:
                try:
                    route[i]['turn'] = geometry.turn_between_two_segments(
                            route[i+1]['bearing'], route[i-1]['bearing'])
                except (IndexError, KeyError):
                    route[i]['turn'] = -1
        logging.debug(json.dumps(route, indent=4))
        return route


    def calculate_route_section(self, start_point, dest_point):
        # temp routing database table
        #
        # prepare
        minimum_radius = 750        # in meters
        distance_between_start_and_destination = geometry.distance_between_two_points(
                start_point['lat'], start_point['lon'],
                dest_point['lat'], dest_point['lon'])
        logging.info("distance_between_start_and_destination = {}".format(distance_between_start_and_destination))
        if distance_between_start_and_destination > constants.max_distance_between_start_and_destination_in_meters:
            raise WebserverException(
                    ReturnCode.START_AND_DESTINATION_TOO_FAR_AWAY,
                    "Distance: {}".format(distance_between_start_and_destination))
        center_point = geometry.get_center_point(
                start_point['lat'], start_point['lon'],
                dest_point['lat'], dest_point['lon'])
        boundaries = geometry.get_boundary_box(center_point['lat'], center_point['lon'],
                minimum_radius + int(distance_between_start_and_destination / 2))

        # delete old table if it exists
        self.delete_temp_routing_database()
        # create
        self.selected_db.edit_database(
                sql.SQL(
                    """
                    CREATE TABLE {i_temp_routing_table} AS
                        SELECT * FROM {i_routing_table} LIMIT 0
                    """
                    ).format(
                        i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                        i_routing_table=sql.Identifier(self.routing_table_name)))
        # fill
        self.selected_db.edit_database(
                sql.SQL(
                    """
                    INSERT INTO {i_temp_routing_table}
                        SELECT * from {i_routing_table}
                        WHERE geom_way && ST_MakeEnvelope(
                                {p_b_left}, {p_b_bottom}, {p_b_right}, {p_b_top})
                    """
                    ).format(
                        i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                        i_routing_table=sql.Identifier(self.routing_table_name),
                        p_b_left=sql.Placeholder(name='b_left'),
                        p_b_bottom=sql.Placeholder(name='b_bottom'),
                        p_b_right=sql.Placeholder(name='b_right'),
                        p_b_top=sql.Placeholder(name='b_top')),
                    {'b_left':boundaries['left'], 'b_bottom':boundaries['bottom'],
                        'b_right':boundaries['right'], 'b_top':boundaries['top']})

        # update routing table cost column
        for way_class_id, weight in self.way_class_id_and_weight_map.items():
            self.selected_db.edit_database(
                    sql.SQL(
                        """
                        UPDATE {i_temp_routing_table}
                            SET cost = km * {p_weight}
                            WHERE kmh = {p_way_class_id}
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                            p_weight=sql.Placeholder(name='weight'),
                            p_way_class_id=sql.Placeholder(name='way_class_id')),
                        {'weight':weight, "way_class_id":way_class_id})
        # ways to be excluded from routing
        if self.way_ids_to_exclude:
            self.selected_db.edit_database(
                    sql.SQL(
                        """
                        UPDATE {i_temp_routing_table}
                            SET cost = -1
                            WHERE osm_id = ANY({p_way_id_list})
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                            p_way_id_list=sql.Placeholder(name='way_id_list')),
                        {'way_id_list':self.way_ids_to_exclude})
        # column index
        self.selected_db.edit_database(
                sql.SQL(
                    """
                    ALTER TABLE ONLY {i_temp_routing_table}
                        ADD CONSTRAINT {i_primary_key} PRIMARY KEY (id);
                    CREATE INDEX {i_source_index} ON {i_temp_routing_table} USING btree (source);
                    CREATE INDEX {i_target_index} ON {i_temp_routing_table} USING btree (target);
                    CREATE INDEX {i_osm_source_id_index} ON {i_temp_routing_table} USING btree (osm_source_id);
                    CREATE INDEX {i_osm_target_id_index} ON {i_temp_routing_table} USING btree (osm_target_id);
                    CREATE INDEX {i_geom_way_index} ON {i_temp_routing_table} USING gist (geom_way);
                    ALTER TABLE {i_temp_routing_table} CLUSTER ON {i_geom_way_index};
                    SELECT recreate_vertex_of_routing_table({l_temp_routing_table});
                    ANALYZE {i_temp_routing_table};
                    """
                    ).format(
                        i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                        l_temp_routing_table=sql.Literal(self.temp_routing_table_name),
                        i_primary_key=sql.Identifier("pkey_{}".format(self.temp_routing_table_name)),
                        i_source_index=sql.Identifier("idx_{}_source".format(self.temp_routing_table_name)),
                        i_target_index=sql.Identifier("idx_{}_target".format(self.temp_routing_table_name)),
                        i_osm_source_id_index=sql.Identifier("idx_{}_osm_source_id".format(self.temp_routing_table_name)),
                        i_osm_target_id_index=sql.Identifier("idx_{}_osm_target_id".format(self.temp_routing_table_name)),
                        i_geom_way_index=sql.Identifier("idx_{}_geom_way".format(self.temp_routing_table_name))))

        # check if table is empty
        try:
            self.selected_db.fetch_one(
                    sql.SQL(
                        """
                        SELECT * FROM {i_temp_routing_table} LIMIT 1
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name)))
        except DBControl.DatabaseResultEmptyError as e:
            raise WebserverException(ReturnCode.WRONG_MAP_SELECTED)
        else:
            if Config().has_session_id_to_remove(self.session_id):
                raise WebserverException(ReturnCode.CANCELLED_BY_CLIENT)

        # get start and destination vertex
        start_vertex_list = self.get_closest_vertex_list(start_point['lat'], start_point['lon'])
        logging.info("{} / {} -- sv_list: {}".format(
            start_point['lat'], start_point['lon'], start_vertex_list))
        dest_vertex_list = self.get_closest_vertex_list(dest_point['lat'], dest_point['lon'])
        logging.info("{} / {} -- dv_list: {}".format(
            dest_point['lat'], dest_point['lon'], dest_vertex_list))
        if Config().has_session_id_to_remove(self.session_id):
            raise WebserverException(ReturnCode.CANCELLED_BY_CLIENT)

        # route calculation
        best_route = None
        if len(start_vertex_list) < len(dest_vertex_list):
            max_vertex_list_length = len(dest_vertex_list)
        else:
            max_vertex_list_length = len(start_vertex_list)
        for x in range(0, max_vertex_list_length):
            for y in range(0, x+1):
                if x < len(start_vertex_list) and y < len(dest_vertex_list):
                    logging.info("{} / {}".format(x,y))
                    result = self.selected_db.fetch_all(
                            sql.SQL(
                                """
                                SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(
                                    'SELECT id, source, target, cost from {i_temp_routing_table}',
                                    {p_start_vertex}, {p_dest_vertex}, false, false)
                                """
                                ).format(
                                    i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                                    p_start_vertex=sql.Placeholder(name='start_vertex'),
                                    p_dest_vertex=sql.Placeholder(name='dest_vertex')),
                                {"start_vertex":start_vertex_list[x].point_id,
                                    "dest_vertex":dest_vertex_list[y].point_id})
                    if result:
                        best_route = PedestrianRoute.RawRoute(result, start_vertex_list[x], dest_vertex_list[y])
                        break
                if y < len(start_vertex_list) and x < len(dest_vertex_list) and x != y:
                    logging.info("{} / {}".format(y,x))
                    result = self.selected_db.fetch_all(
                            sql.SQL(
                                """
                                SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(
                                    'SELECT id, source, target, cost from {i_temp_routing_table}',
                                    {p_start_vertex}, {p_dest_vertex}, false, false)
                                """
                                ).format(
                                    i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                                    p_start_vertex=sql.Placeholder(name='start_vertex'),
                                    p_dest_vertex=sql.Placeholder(name='dest_vertex')),
                                {"start_vertex":start_vertex_list[y].point_id,
                                    "dest_vertex":dest_vertex_list[x].point_id})
                    if result:
                        best_route = PedestrianRoute.RawRoute(result, start_vertex_list[y], dest_vertex_list[x])
                        break
                # cancel
                if Config().has_session_id_to_remove(self.session_id):
                    raise WebserverException(ReturnCode.CANCELLED_BY_CLIENT)
            # break outer loop
            if best_route:
                break
        # error handling
        if not best_route:
            result = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        SELECT seq, id1 AS node, id2 AS edge_id, cost FROM pgr_dijkstra(
                            'SELECT id, source, target, km AS cost from {i_temp_routing_table}',
                            {p_start_vertex}, {p_dest_vertex}, false, false)
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                            p_start_vertex=sql.Placeholder(name='start_vertex'),
                            p_dest_vertex=sql.Placeholder(name='dest_vertex')),
                        {"start_vertex":start_vertex_list[0].point_id,
                            "dest_vertex":dest_vertex_list[0].point_id})
            if result:
                raise WebserverException(ReturnCode.TOO_MANY_WAY_CLASSES_IGNORED)
            else:
                raise WebserverException(ReturnCode.NO_ROUTE_BETWEEN_START_AND_DESTINATION)

        route = []
        last_target_id = -1
        reverse = False
        for r in best_route.route:
            if r['edge_id'] == -1:
                continue
            part = self.selected_db.fetch_one(
                    sql.SQL(
                        """
                        SELECT * FROM {i_temp_routing_table} WHERE id={p_edge_id}
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                            p_edge_id=sql.Placeholder(name='edge_id')),
                        {"edge_id":r['edge_id']})

            # exception for the first route segment
            # add start point of route first
            if part['source'] == best_route.start_vertex_tuple.point_id:
                logging.info("start point added")
                # check if current point is an intersection
                next_point = self.poi.create_intersection_by_id(part['osm_source_id'])
                if not next_point:
                    next_point = self.poi.create_way_point_by_id(part['osm_source_id'])
                route.append(next_point)
                last_target_id = part['source']
            elif part['target'] == best_route.start_vertex_tuple.point_id:
                logging.info("target point added")
                # check if current point is an intersection
                next_point = self.poi.create_intersection_by_id(part['osm_target_id'])
                if not next_point:
                    next_point = self.poi.create_way_point_by_id(part['osm_target_id'])
                route.append(next_point)
                last_target_id = part['target']

            # create next point
            if last_target_id == part['source']:
                next_point = self.poi.create_intersection_by_id(part['osm_target_id'])
                if not next_point:
                    next_point = self.poi.create_way_point_by_id(part['osm_target_id'])
                reverse = False
                last_target_id = part['target']
            else:
                next_point = self.poi.create_intersection_by_id(part['osm_source_id'])
                if not next_point:
                    next_point = self.poi.create_way_point_by_id(part['osm_source_id'])
                reverse = True
                last_target_id = part['source']

            # extract points of a curved graph edge
            coordinates_list = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon
                        FROM (
                            SELECT ST_PointN(geom_way, generate_series(1, ST_NPoints(geom_way))) AS geom
                            FROM {i_temp_routing_table}
                            WHERE id = {p_routing_table_id}) AS points
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                            p_routing_table_id=sql.Placeholder(name='routing_table_id')),
                        {"routing_table_id":part['id']})
            if reverse:
                coordinates_list = coordinates_list[::-1]
            next_point_list = []
            last_accepted_bearing = geometry.bearing_between_two_points(
                        coordinates_list[0]['lat'], coordinates_list[0]['lon'],
                        coordinates_list[1]['lat'], coordinates_list[1]['lon'])
            for i in range(1, len(coordinates_list)-1):
                new_bearing = geometry.bearing_between_two_points(
                        coordinates_list[i]['lat'], coordinates_list[i]['lon'],
                        coordinates_list[i+1]['lat'], coordinates_list[i+1]['lon'])
                turn = geometry.turn_between_two_segments(
                        new_bearing, last_accepted_bearing)
                if turn > 22 and turn < 338:
                    last_accepted_bearing = new_bearing
                    next_point_list.append(
                            self.poi.create_way_point(
                                -1, coordinates_list[i]['lat'], coordinates_list[i]['lon'], {}))
            next_point_list.append(next_point)

            # create next segment
            next_segment = self.poi.create_way_segment_by_id(part['osm_id'], reverse )
            next_segment['way_class'] = part['kmh']
            # add next points to route
            for point in next_point_list:
                route = self.add_point_to_route(route, point, next_segment.copy())
            # check cancel state
            if Config().has_session_id_to_remove(self.session_id):
                raise WebserverException(ReturnCode.CANCELLED_BY_CLIENT)

        # add start point
        first_segment = None
        distance_start_p0 = geometry.distance_between_two_points(
                start_point['lat'], start_point['lon'], route[0]['lat'], route[0]['lon'])
        bearing_start_p0 = geometry.bearing_between_two_points(
                start_point['lat'], start_point['lon'], route[0]['lat'], route[0]['lon'])
        turn = geometry.turn_between_two_segments(route[1]['bearing'], bearing_start_p0)
        logging.info("start: turn = %d, distance = %d" % (turn, distance_start_p0))
        if distance_start_p0 <= 5:
            route[0] = start_point
        elif best_route.start_vertex_tuple.way_distance <= 5 \
                or (best_route.start_vertex_tuple.way_class in [1,2] and best_route.start_vertex_tuple.way_distance <= 15):
            if turn >= 158 and turn <= 202:
                route[1]['distance'] -= distance_start_p0
                route[0] = start_point
            elif not self.important_intersection(route[0]) \
                    and (turn <= 22 or turn >= 338):
                route[1]['distance'] += distance_start_p0
                route[0] = start_point
            else:
                first_segment = self.poi.create_way_segment_by_id(
                        best_route.start_vertex_tuple.way_id)
        else:
            first_segment = {"name":self.translator.translate("footway_creator", "first_segment"),
                    "type":"footway", "sub_type":"", "way_id":-1, "pois":[]}
        # add first way segment
        if first_segment:
            route[0]['turn'] = turn
            first_segment['type'] = "footway_route"
            first_segment['bearing'] = bearing_start_p0
            first_segment['distance'] = distance_start_p0
            route.insert(0, first_segment)
            route.insert(0, start_point)

        # destination point
        distance_plast_dest = geometry.distance_between_two_points(
                route[-1]['lat'], route[-1]['lon'], dest_point['lat'], dest_point['lon'])
        bearing_plast_dest = geometry.bearing_between_two_points(
                route[-1]['lat'], route[-1]['lon'], dest_point['lat'], dest_point['lon'])
        turn = geometry.turn_between_two_segments(bearing_plast_dest, route[-2]['bearing'])
        logging.info("destination: turn = %d, distance = %d" % (turn, distance_plast_dest))
        if distance_plast_dest <= 5:
            route[-1] = dest_point
        elif best_route.dest_vertex_tuple.way_distance <= 5 \
                or (best_route.dest_vertex_tuple.way_class in [1,2] and best_route.dest_vertex_tuple.way_distance <= 15):
            if turn >= 158 and turn <= 202:
                # turn around
                route[-2]['distance'] -= distance_plast_dest
                route[-1] = dest_point
            elif not self.important_intersection(route[-1]) \
                    and (turn <= 22 or turn >= 338):
                # streight ahead
                route[-2]['distance'] += distance_plast_dest
                route[-1] = dest_point
            else:
                dest_segment = self.poi.create_way_segment_by_id(
                        best_route.dest_vertex_tuple.way_id)
                route = self.add_point_to_route(route, dest_point, dest_segment.copy())
        else:
            dest_segment = {"name":self.translator.translate("footway_creator", "last_segment"),
                    "type":"footway", "sub_type":"", "way_id":-1, "pois":[]}
            route = self.add_point_to_route(route, dest_point, dest_segment.copy())

        # part of route parameters
        for i in range(0, len(route), 2):
            if route[i].get("type") == "intersection":
                intersection = route[i]
                # previous route segment
                minimal_bearing_difference_previous = 180
                index_of_previous = -1
                bearing_of_previous_route_segment = None
                if (i-1) > 0 \
                        and route[i-1].get("bearing"):
                    bearing_of_previous_route_segment = route[i-1].get("bearing")
                # next route segment
                minimal_bearing_difference_next = 180
                index_of_next = -1
                bearing_of_next_route_segment = None
                if (i+1) < len(route) \
                        and route[i+1].get("bearing"):
                    bearing_of_next_route_segment = route[i+1].get("bearing")
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
                route[i] = intersection

        # return route section
        return route


### hiking trails begin
#    def calculate_route(self, relation_id, direction_forwards=True):
#        # get relation members
#        relation_members = self.selected_db.fetch_all(
#                sql.SQL(
#                    """
#                    SELECT * FROM {i_table_name}
#                        WHERE relation_id = {p_relation_id} AND member_role = ''
#                        ORDER BY sequence_id {l_ASC_OR_DESC}
#                    """
#                    ).format(
#                            i_table_name=sql.Identifier("relation_members"),
#                            p_relation_id=sql.Placeholder(name='relation_id'),
#                            l_ASC_OR_DESC=sql.Literal("ASC" if direction_forwards else "DESC")),
#                    { "relation_id":relation_id})
#
#        way_node_map = {}
#        for member in relation_members:
#            if member.get("member_type").lower() == "n":
#                way_node_map[None] = member.get(member_id")
#
#            elif member.get("member_type").lower() == "w":
#                way_nodes = self.selected_db.fetch_all(
#                        sql.SQL(
#                            """
#                            SELECT * FROM {i_table_name}
#                                WHERE way_id = {p_way_id}
#                                ORDER BY sequence_id {l_ASC_OR_DESC}
#                            """
#                            ).format(
#                                    i_table_name=sql.Identifier("way_nodes"),
#                                    p_way_id=sql.Placeholder(name='way_id'),
#                                    l_ASC_OR_DESC=sql.Literal("ASC" if direction_forwards else "DESC")),
#                            { "way_id":member.get("member_id")})
### hiking trails end


    def create_description_for_route(self, route):
        route_length = 0
        number_of_intersections = 0
        number_of_transport_segments = 0
        transport_seg_index = 0
        for index in range(1, len(route)-1):
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
                if route[index]['type'] == "footway_route":
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


    def delete_temp_routing_database(self):
        try:
            self.selected_db.edit_database(
                    sql.SQL(
                        """
                        DROP TABLE IF EXISTS {i_temp_routing_table}
                        """
                        ).format(
                            i_temp_routing_table=sql.Identifier(self.temp_routing_table_name)))
        except DBControl.DatabaseError as e:
            pass


    def get_closest_vertex_list(self, lat, lon):
        tuple_list = []
        # get closest edges from graph
        edge_list = self.selected_db.fetch_all(
                sql.SQL(
                    """
                    SELECT id, osm_id, osm_name, osm_source_id, osm_target_id,
                            source, target, kmh as type, x1, y1, x2, y2,
                            ST_Distance(geom_way::geography, 'POINT({p_lon} {p_lat})'::geography) as way_distance
                        FROM {i_temp_routing_table}
                        WHERE kmh != 7
                        ORDER BY ST_Distance(geom_way::geography, 'POINT({p_lon} {p_lat})'::geography)
                        LIMIT 20
                    """
                    ).format(
                        i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                        p_lon=sql.Placeholder(name='lon'),
                        p_lat=sql.Placeholder(name='lat')),
                    {"lat":lat, "lon":lon})
        # insert into tuple vertex_list
        for edge in edge_list:
            # check, if source or target vertex of found edge is closer
            source_dist = geometry.distance_between_two_points_as_float(
                    edge['y1'], edge['x1'], lat, lon)
            target_dist = geometry.distance_between_two_points_as_float(
                    edge['y2'], edge['x2'], lat, lon)
            if source_dist < target_dist:
                tuple_list.append(
                        PedestrianRoute.VertexTuple(
                            edge['source'], source_dist, edge['osm_id'],
                            edge['type'], edge['way_distance'], edge['osm_name']))
            else:
                tuple_list.append(
                        PedestrianRoute.VertexTuple(
                            edge['target'], target_dist, edge['osm_id'], 
                            edge['type'], edge['way_distance'], edge['osm_name']))
        return tuple_list


    def add_point_to_route(self, route, next_point, next_segment, add_all_intersections=False):
        # calculate distance and bearing of new segment
        try:
            next_segment['bearing'] = geometry.bearing_between_two_points(
                    route[-1]['lat'], route[-1]['lon'],
                    next_point['lat'], next_point['lon'])
            next_segment['distance'] = geometry.distance_between_two_points(
                    route[-1]['lat'], route[-1]['lon'],
                    next_point['lat'], next_point['lon'])
            if next_segment['distance'] == 0 and next_point['type'] == "intersection":
                # replace last point
                route[-1] = next_point
                return route
        except IndexError as e:
            # if the route is still empty, add the next route point and exit
            route.append(next_point)
            return route
        # try to find and delete unimportant intersections and way points
        try:
            turn = geometry.turn_between_two_segments(
                    next_segment['bearing'], route[-2]['bearing'])
            if (not add_all_intersections \
                        or (add_all_intersections and route[-1]['type'] != "intersection")) \
                    and (turn <= 22 or turn >= 338) \
                    and route[-2]['name'] == next_segment['name'] \
                    and route[-2]['sub_type'] == next_segment['sub_type'] \
                    and not self.important_intersection(route[-1], route[-2]):
                # delete unimportant waypoint or intersection
                del route[-2:]
        except IndexError as e:
            pass
        # find and delete zigzag
        try:
            turn = geometry.turn_between_two_segments(
                    next_segment['bearing'], route[-4]['bearing'])
            if not add_all_intersections \
                    and (turn <= 22 or turn >= 338) \
                    and route[-2]['distance'] < 4 \
                    and not self.important_intersection(route[-1], route[-2]) \
                    and not self.important_intersection(route[-3], route[-4]):
                del route[-4:]
        except IndexError as e:
            pass
        # delete double train intersection but leave first of two intersections
        try:
            turn = geometry.turn_between_two_segments(
                    next_segment['bearing'], route[-4]['bearing'])
            if not add_all_intersections \
                    and (turn <= 22 or turn >= 338) \
                    and route[-2]['distance'] < 5 \
                    and ( \
                        self.translator.translate("railway", "tram") in route[-1]['name'] \
                        or self.translator.translate("railway", "rail") in route[-1]['name'] \
                        ) \
                    and ( \
                        self.translator.translate("railway", "tram") in route[-3]['name'] \
                        or self.translator.translate("railway", "rail") in route[-3]['name'] \
                        ):
                del route[-2:]
        except IndexError as e:
            pass
        # calculate the updated distance and bearing to the potentially new prev point
        next_segment['type'] = "footway_route"
        next_segment['bearing'] = geometry.bearing_between_two_points(
                route[-1]['lat'], route[-1]['lon'],
                next_point['lat'], next_point['lon'])
        next_segment['distance'] = geometry.distance_between_two_points(
                route[-1]['lat'], route[-1]['lon'],
                next_point['lat'], next_point['lon'])
        # update turn value
        try:
            if "turn" not in route[-1]:
                route[-1]['turn'] = geometry.turn_between_two_segments(
                        next_segment['bearing'], route[-2]['bearing'])
        except IndexError as e:
            pass
        # append new segment and point
        route.append(next_segment)
        route.append(next_point)
        return route


    def important_intersection(self, intersection, prev_segment={}):
        street_traffic_way_list = []
        impassable_way_list = []
        for way in intersection.get("way_list", {}):
            try:
                way_type = self.selected_db.fetch_one(
                        sql.SQL(
                            """
                            SELECT kmh AS type
                                FROM {i_temp_routing_table}
                                WHERE osm_id = {p_osm_id}
                                LIMIT 1
                            """
                            ).format(
                                i_temp_routing_table=sql.Identifier(self.temp_routing_table_name),
                                p_osm_id=sql.Placeholder(name='osm_id')),
                            {"osm_id":way.get("way_id", 0)}
                        ).get("type", 0)
            except DBControl.DatabaseResultEmptyError as e:
                impassable_way_list.append(way.get("name"))
            else:
                if way_type in [1,2] \
                        and way.get("name") \
                        and way.get("name") not in street_traffic_way_list:
                    street_traffic_way_list.append(way.get("name"))
                elif way_type in [7] \
                        and way.get("name") \
                        and way.get("name") not in impassable_way_list:
                    impassable_way_list.append(way.get("name"))
        if len(street_traffic_way_list) > 1:
            return True
        elif len(street_traffic_way_list) > 0 \
                and prev_segment.get("way_class", 0) in [3,4,5,6,7]:
            return True
        elif len(impassable_way_list) > 0:
            return True
        else:
            return False


    class VertexTuple:
        def __init__(self, point_id, point_distance, way_id, way_class, way_distance, way_name):
            self.point_id = point_id
            self.point_distance = point_distance
            self.way_id = way_id
            self.way_class = way_class
            self.way_distance = way_distance
            self.way_name = way_name


    class RawRoute:
        def __init__(self, route, start_vertex_tuple, dest_vertex_tuple):
            self.route = route
            self.start_vertex_tuple = start_vertex_tuple
            self.dest_vertex_tuple = dest_vertex_tuple

