#!/usr/bin/python
# -*- coding: utf-8 -*-

import math, time

from . import geometry
from .config import Config


class POI:

    def __init__(self, db, session_id, translator_object, hide_log_messages=False):
        self.selected_db = db
        self.session_id = session_id
        self.translator = translator_object
        self.hide_log_messages = hide_log_messages


    def get_poi(self, lat, lon, radius, number_of_results, tag_list, search=""):
        ts = time.time()
        poi_list = []

        # tags, boundary box and search strings
        tags = self.create_tags(tag_list)
        boundaries = geometry.get_boundary_box(lat, lon, radius)
        if search != "":
            # prepare search strings
            search = search.replace(" ", "%").lower()
            # entrances, intersections and crossings
            search_entrances = "LOWER(label) LIKE '%%%s%%'" % search
            search_intersections = "LOWER(name) LIKE '%%%s%%'" % search
            search_pedestrian_crossings = "LOWER(crossing_street_name) LIKE '%%%s%%'" % search
            # poi
            search_poi = "("
            search_poi += "LOWER(tags->'name') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'amenity') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'cuisine') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'addr:street') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'street') LIKE '%%%s%%'" % search
            search_poi += ")"
            # stations
            search_stations = "("
            search_stations += "LOWER(tags->'name') LIKE '%%%s%%'" % search
            search_stations += ")"
        else:
            search_entrances = ""
            search_intersections = ""
            search_pedestrian_crossings = ""
            search_poi = ""
            search_stations = ""

        # intersections
        if tags['intersection'] != "":
            t1 = time.time()
            where_clause = "geom && ST_MakeEnvelope(%f, %f, %f, %f)" \
                    % (boundaries['left'], boundaries['bottom'], boundaries['right'], boundaries['top'])
            if tags['intersection'] == "name":
                # only bigger intersections
                where_clause += " AND number_of_streets_with_name > 1"
            elif tags['intersection'] == "other":
                # only smaller intersections
                where_clause += " AND number_of_streets_with_name <= 1"
            # search for something?
            if search_intersections != "":
                where_clause += " AND %s" % search_intersections
            # query data
            result = self.selected_db.fetch_data("" \
                    "WITH closest_points AS (" \
                        "SELECT * FROM %s WHERE %s" \
                    ")" \
                    "SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, name, tags, number_of_streets, " \
                            "number_of_streets_with_name, number_of_traffic_signals " \
                        "FROM closest_points " \
                        "ORDER BY ST_Distance(geom::geography, 'POINT(%f %f)'::geography) " \
                        "LIMIT %d" \
                    % (Config().database.get("intersection_table"), where_clause,
                        lon, lat, number_of_results))
            t2 = time.time()
            for row in result:
                intersection_id = int(row['id'])
                intersection_tags = self.parse_hstore_column(row['tags'])
                intersection = self.create_intersection(intersection_id, row['lat'], row['lon'], row['name'], intersection_tags, row['number_of_streets'],
                        row['number_of_streets_with_name'], row['number_of_traffic_signals'])
                poi_list = self.insert_into_poi_list(poi_list, intersection, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print("intersection gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))

        # stations
        if tags['station'] != "":
            t1 = time.time()
            where_clause = "geom && ST_MakeEnvelope(%f, %f, %f, %f) AND %s" \
                    % (boundaries['left'], boundaries['bottom'], boundaries['right'],
                        boundaries['top'], tags['station'])
            if search_stations != "":
                where_clause += " AND %s" % search_stations
            result = self.selected_db.fetch_data("" \
                    "WITH closest_points AS (" \
                        "SELECT * FROM stations WHERE %s" \
                    ")" \
                    "SELECT id, osm_id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, " \
                            "outer_building_id, number_of_entrances, number_of_lines " \
                        "FROM closest_points " \
                        "ORDER BY ST_Distance(geom::geography, 'POINT(%f %f)'::geography) " \
                        "LIMIT %d" \
                    % (where_clause, lon, lat, number_of_results))
            t2 = time.time()
            for row in result:
                station_id = int(row['id'])
                osm_id = int(row['osm_id'])
                outer_building_id = int(row['outer_building_id'])
                station_tags = self.parse_hstore_column(row['tags'])
                if "name" not in station_tags:
                    # a station without a name is not very usefull
                    continue
                if "public_transport" not in station_tags:
                    # legacy mode for stations without stop_position
                    existance_check = self.selected_db.fetch_data("" \
                            "SELECT exists(SELECT 1 FROM stations WHERE %s " \
                                "and tags->'name' = '%s' and tags ? 'public_transport') as exists" \
                            % (where_clause, station_tags['name']))[0]
                    if existance_check['exists']:
                        # the station already is represented by another one with the same name
                        # and a stop_position tag, so skip this one
                        continue
                station = self.create_station(station_id, osm_id, row['lat'], row['lon'], station_tags, outer_building_id,
                        row['number_of_entrances'], row['number_of_lines'])
                poi_list = self.insert_into_poi_list(poi_list, station, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print("station gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))

        # poi
        if tags['poi'] != "":
            t1 = time.time()
            where_clause = "geom && ST_MakeEnvelope(%f, %f, %f, %f) AND %s" \
                    % (boundaries['left'], boundaries['bottom'], boundaries['right'],
                        boundaries['top'], tags['poi'])
            if search_poi != "":
                where_clause += " AND %s" % search_poi
            result = self.selected_db.fetch_data("" \
                    "WITH closest_points AS (" \
                        "SELECT * FROM poi WHERE %s" \
                    ")" \
                    "SELECT id, osm_id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, " \
                            "outer_building_id, number_of_entrances " \
                        "FROM closest_points " \
                        "ORDER BY ST_Distance(geom::geography, 'POINT(%f %f)'::geography) " \
                        "LIMIT %d" \
                    % (where_clause, lon, lat, number_of_results))
            t2 = time.time()
            for row in result:
                poi_id = int(row['id'])
                osm_id = int(row['osm_id'])
                poi_tags = self.parse_hstore_column(row['tags'])
                outer_building_id = int(row['outer_building_id'])
                poi = self.create_poi(poi_id, osm_id, row['lat'], row['lon'], poi_tags, outer_building_id, row['number_of_entrances'])
                poi_list = self.insert_into_poi_list(poi_list, poi, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print("poi gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))

        # entrances
        if tags['entrance'] != "":
            t1 = time.time()
            where_clause = "geom && ST_MakeEnvelope(%f, %f, %f, %f)" \
                    % (boundaries['left'], boundaries['bottom'], boundaries['right'], boundaries['top'])
            if search_entrances != "":
                where_clause += " AND %s" % search_entrances
            result = self.selected_db.fetch_data("" \
                    "WITH closest_points AS (" \
                        "SELECT * FROM entrances WHERE %s" \
                    ")" \
                    "SELECT entrance_id, ST_X(geom) as lon, ST_Y(geom) as lat, label, tags " \
                        "FROM closest_points " \
                        "ORDER BY ST_Distance(geom::geography, 'POINT(%f %f)'::geography) " \
                        "LIMIT %d" \
                    % (where_clause, lon, lat, number_of_results))
            t2 = time.time()
            for row in result:
                entrance = self.create_entrance(int(row['entrance_id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['label'])
                poi_list = self.insert_into_poi_list(poi_list, entrance, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print("entrances gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))

        # pedestrian crossings
        if tags['pedestrian_crossings'] != "":
            t1 = time.time()
            where_clause = "geom && ST_MakeEnvelope(%f, %f, %f, %f)" \
                    % (boundaries['left'], boundaries['bottom'], boundaries['right'], boundaries['top'])
            if search_pedestrian_crossings != "":
                where_clause += " AND %s" % search_pedestrian_crossings
            result = self.selected_db.fetch_data("" \
                    "WITH closest_points AS (" \
                        "SELECT * FROM pedestrian_crossings WHERE %s" \
                    ")" \
                    "SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, crossing_street_name " \
                        "FROM closest_points " \
                        "ORDER BY ST_Distance(geom::geography, 'POINT(%f %f)'::geography) " \
                        "LIMIT %d" \
                    % (where_clause, lon, lat, number_of_results))
            t2 = time.time()
            for row in result:
                signal = self.create_pedestrian_crossing(int(row['id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['crossing_street_name'])
                poi_list = self.insert_into_poi_list(poi_list, signal, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print("pedestrian crossings gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))

        # filter out entries above given radius
        thrown_away = 0
        filtered_poi_list = []
        for entry in poi_list:
            if entry['distance'] < radius and len(filtered_poi_list) < number_of_results:
                filtered_poi_list.append(entry)
            else:
                thrown_away += 1
        print(thrown_away)

        te = time.time()
        if self.hide_log_messages == False:
            print("gesamtzeit: %.2f;   anzahl entries = %d" % ((te-ts), len(poi_list)))
        return filtered_poi_list


    def next_intersections_for_way(self, node_id, way_id, next_node_id):
        # get current way id and tags
        try:
            way_id = way_id
            way_tags = self.parse_hstore_column(
                    self.selected_db.fetch_data("SELECT tags from ways where id = %d" % way_id)[0]['tags'])
        except (IndexError, KeyError) as e:
            raise POI.POICreationError(
                    self.translator.translate("message", "way_id_invalid"))
        # get initial movement direction
        try:
            node_id_seq_nr = self.selected_db.fetch_data(
                    "SELECT sequence_id from way_nodes where way_id = %d AND node_id = %d" \
                            % (way_id, node_id))[0]['sequence_id']
            next_node_id_seq_nr = self.selected_db.fetch_data(
                    "SELECT sequence_id from way_nodes where way_id = %d AND node_id = %d" \
                            % (way_id, next_node_id))[0]['sequence_id']
        except (IndexError, KeyError) as e:
            raise POI.POICreationError(
                    self.translator.translate("message", "way_id_invalid"))
        else:
            if node_id_seq_nr < next_node_id_seq_nr:
                comparison_operator = ">"
                order_direction = "ASC"
            else:
                comparison_operator = "<"
                order_direction = "DESC"

        # create node list and add start intersection
        next_node_list = []
        first_node = self.create_intersection_by_id(node_id)
        if first_node:
            next_node_list.append(first_node)

        # collect next node id list
        next_node_id_list = []
        index = 0
        while True:
            index += 1
            next_node_id_list += self.selected_db.fetch_data(
                    "select node_id from way_nodes " \
                    "WHERE way_id = %d AND sequence_id %s %d ORDER BY sequence_id %s" \
                    % (way_id, comparison_operator, node_id_seq_nr, order_direction))
            # set on the start of the next potential way
            node_id = next_node_id_list[-1]['node_id']
            potential_next_way_list = []
            for potential_next_way in self.selected_db.fetch_data(
                    "SELECT wn.sequence_id AS sequence_id, w.id AS way_id, w.tags AS way_tags " \
                    "FROM way_nodes wn JOIN ways w ON wn.way_id = w.id " \
                    "WHERE wn.node_id = %d AND wn.way_id != %d" % (node_id, way_id)):
                potential_next_way_tags = self.parse_hstore_column(potential_next_way['way_tags'])
                if potential_next_way_tags.get("name") \
                        and potential_next_way_tags.get("name") == way_tags.get("name"):
                    potential_next_way_list.append(potential_next_way)
                elif potential_next_way_tags.get("surface") \
                        and potential_next_way_tags.get("surface") == way_tags.get("surface") \
                        and potential_next_way_tags.get("tracktype") \
                        and potential_next_way_tags.get("tracktype") == way_tags.get("tracktype"):
                    potential_next_way_list.append(potential_next_way)
                elif potential_next_way_tags.get("surface") \
                        and potential_next_way_tags.get("surface") == way_tags.get("surface") \
                        and potential_next_way_tags.get("smoothness") \
                        and potential_next_way_tags.get("smoothness") == way_tags.get("smoothness"):
                    potential_next_way_list.append(potential_next_way)
            if len(potential_next_way_list) == 1:
                way_id = potential_next_way_list[0]['way_id']
                way_tags = self.parse_hstore_column(
                        potential_next_way_list[0]['way_tags'])
                # comparison and order direction
                node_id_seq_nr = potential_next_way_list[0]['sequence_id']
                if node_id_seq_nr == 0:
                    comparison_operator = ">"
                    order_direction = "ASC"
                else:
                    comparison_operator = "<"
                    order_direction = "DESC"
            else:
                break

        # create point objects and return
        # walk through next_node_id_list and create intersections and way points
        for next_node_id in next_node_id_list:
            next_node = self.create_intersection_by_id(
                    next_node_id.get("node_id"))
            if not next_node:
                next_node = self.create_way_point_by_id(
                        next_node_id.get("node_id"))
            next_node_list.append(next_node)
        return next_node_list


    #####
    # create the poi objects
    #####

    def create_way_point_by_id(self, osm_node_id):
        try:
            result = self.selected_db.fetch_data("SELECT ST_X(geom) as x, ST_Y(geom) as y, tags \
                    from nodes where id = %d" % osm_node_id)[0]
        except IndexError as e:
            return {}
        osm_node_id = int(osm_node_id)
        lat = result['y']
        lon = result['x']
        tags = self.parse_hstore_column(result['tags'])
        return self.create_way_point(osm_node_id, lat, lon, tags)

    def create_way_point(self, osm_node_id, lat, lon, tags):
        point = {}
        if type(lat) is not float \
                or type(lon) is not float \
                or type(tags) is not dict:
            return point
        point['type'] = "point"
        point['sub_type'] = self.translator.translate("poi", "way_point")
        if "name" in tags:
            point['name'] = tags['name']
        else:
            point['name'] = point['sub_type']
        point['lat'] = lat
        point['lon'] = lon
        # optional attributes
        point['node_id'] = osm_node_id
        if "tactile_paving" in tags:
            if tags['tactile_paving'] == "no":
                point['tactile_paving'] = 0
            elif tags['tactile_paving'] in ["contrasted", "primitive", "yes"]:
                point['tactile_paving'] = 1
            elif tags['tactile_paving'] == "incorrect":
                point['tactile_paving'] = 2
        if "wheelchair" in tags:
            if tags['wheelchair'] == "no":
                point['wheelchair'] = 0
            elif tags['wheelchair'] == "limited":
                point['wheelchair'] = 1
            elif tags['wheelchair'] == "yes":
                point['wheelchair'] = 2
        return point

    def create_way_segment_by_id(self, osm_way_id, walking_reverse=False):
        try:
            result = self.selected_db.fetch_data("SELECT tags \
                    from ways where id = %d" % osm_way_id)[0]
        except IndexError as e:
            return {}
        osm_way_id = int(osm_way_id)
        tags = self.parse_hstore_column(result['tags'])
        return self.create_way_segment(osm_way_id, tags, walking_reverse)

    def create_way_segment(self, osm_way_id, tags, walking_reverse=False):
        segment = {}
        if type(tags) is not dict \
                or type(walking_reverse) is not bool:
            return segment
        # type and subtype
        segment['type'] = "footway"
        if "highway" in tags:
            segment['sub_type'] = self.translator.translate("highway", tags['highway'])
            if "railway" in tags and tags['railway'] == "tram":
                segment['tram'] = 1
            else:
                segment['tram'] = 0
        elif "railway" in tags:
            segment['sub_type'] = self.translator.translate("railway", tags['railway'])
        else:
            segment['sub_type'] = "unknown"
        # name
        if "name" in tags:
            segment['name'] = tags['name']
        elif "surface" in tags:
            segment['name'] = "%s (%s)" % (segment['sub_type'], tags['surface'])
        elif "tracktype" in tags:
            segment['name'] = "%s (%s)" % (segment['sub_type'], tags['tracktype'])
        else:
            segment['name'] = segment['sub_type']
        # optional attributes
        if "description" in tags:
            segment['description'] = tags['description']
        if "lanes" in tags:
            try:
                segment['lanes'] = int(tags['lanes'])
            except ValueError as e:
                pass
        if "maxspeed" in tags:
            try:
                segment['maxspeed'] = int(tags['maxspeed'])
            except ValueError as e:
                pass
        segment['pois'] = []
        if "segregated" in tags:
            if tags['segregated'] == "yes":
                segment['segregated'] = 1
            else:
                segment['segregated'] = 0
        if "sidewalk" in tags:
            if tags['sidewalk'] == "no" or tags['sidewalk'] == "none":
                segment['sidewalk'] = 0
            elif tags['sidewalk'] == "left":
                if walking_reverse == False:
                    segment['sidewalk'] = 1
                else:
                    segment['sidewalk'] = 2
            elif tags['sidewalk'] == "right":
                if walking_reverse == False:
                    segment['sidewalk'] = 2
                else:
                    segment['sidewalk'] = 1
            elif tags['sidewalk'] == "both":
                segment['sidewalk'] = 3
        if "smoothness" in tags:
            segment['smoothness'] = self.translator.translate("smoothness", tags['smoothness'])
        if "surface" in tags:
            segment['surface'] = self.translator.translate("surface", tags['surface'])
        if "tactile_paving" in tags:
            if tags['tactile_paving'] == "no":
                segment['tactile_paving'] = 0
            elif tags['tactile_paving'] in ["contrasted", "primitive", "yes"]:
                segment['tactile_paving'] = 1
            elif tags['tactile_paving'] == "incorrect":
                segment['tactile_paving'] = 2
        segment['way_id'] = osm_way_id
        if "wheelchair" in tags:
            if tags['wheelchair'] == "no":
                segment['wheelchair'] = 0
            elif tags['wheelchair'] == "limited":
                segment['wheelchair'] = 1
            elif tags['wheelchair'] == "yes":
                segment['wheelchair'] = 2
        if "width" in tags:
            try:
                segment['width'] = float(tags['width'])
            except ValueError as e:
                pass
        segment['bearing'] = -1
        return segment

    def create_intersection_by_id(self, osm_id):
        intersection_table = Config().database.get("intersection_table")
        try:
            result = self.selected_db.fetch_data("SELECT ST_X(geom) as x, ST_Y(geom) as y, name, tags, \
                    number_of_streets, number_of_streets_with_name, number_of_traffic_signals \
                    from %s where id = %d" % (intersection_table, osm_id))[0]
        except IndexError as e:
            return {}
        osm_id = int(osm_id)
        lat = result['y']
        lon = result['x']
        name = result['name']
        tags = self.parse_hstore_column(result['tags'])
        number_of_streets = result['number_of_streets']
        number_of_streets_with_name = result['number_of_streets_with_name']
        number_of_traffic_signals = result['number_of_traffic_signals']
        return self.create_intersection(osm_id, lat, lon, name, tags, number_of_streets, number_of_streets_with_name, number_of_traffic_signals)

    def create_intersection(self, osm_id, lat, lon, name, tags, number_of_streets, number_of_streets_with_name, number_of_traffic_signals):
        intersection_table = Config().database.get("intersection_table")
        intersection_table_data = Config().database.get("intersection_data_table")
        intersection = {}
        if type(osm_id) is not int \
                or type(lat) is not float \
                or type(lon) is not float \
                or type(name) is not str \
                or type(tags) is not dict \
                or type(number_of_streets) is not int \
                or type(number_of_streets_with_name) is not int \
                or type(number_of_traffic_signals) is not int:
            return intersection
        intersection = self.create_way_point(osm_id, lat, lon, tags)
        if intersection == {}:
            return intersection

        # type and subtype
        intersection['type'] = "intersection"
        if "highway" in tags and tags['highway'] == "mini_roundabout":
            intersection['sub_type'] = self.translator.translate("highway", "roundabout")
        elif "highway" in tags and tags['highway'] == "traffic_signals":
            intersection['sub_type'] = self.translator.translate("highway", "traffic_signals")
        elif "railway" in tags and tags['railway'] == "crossing":
            intersection['sub_type'] = self.translator.translate("railway", "crossing")
        else:
            intersection['sub_type'] = self.translator.translate("highway", "crossing")

        # translate name
        translated_street_name_list = []
        for street in [x.strip() for x in name.split(", ")]:
            if street != self.translator.translate("highway", street):
                translated_street_name_list.append(self.translator.translate("highway", street))
            elif street != self.translator.translate("railway", street):
                translated_street_name_list.append(self.translator.translate("railway", street))
            else:
                translated_street_name_list.append(street)
        intersection['name'] = ', '.join(translated_street_name_list)

        # optional attributes
        intersection['number_of_streets'] = number_of_streets
        intersection['number_of_streets_with_name'] = number_of_streets_with_name

        # ways
        intersection['way_list'] = []
        result = self.selected_db.fetch_data("\
                SELECT way_id, node_id, direction, way_tags, node_tags, \
                    ST_X(geom) as lon, ST_Y(geom) as lat \
                from %s where id = %d" % (intersection_table_data, osm_id))
        for street in result:
            sub_segment = self.create_way_segment(
                    street['way_id'],
                    self.parse_hstore_column(street['way_tags']),
                    street['direction'] == "B")
            sub_segment['next_node_id'] = street['node_id']
            sub_segment['type'] = "footway_intersection"
            sub_segment['intersection_name'] = intersection['name']
            sub_segment['bearing'] = geometry.bearing_between_two_points(
                    intersection['lat'], intersection['lon'], street['lat'], street['lon'])
            intersection['way_list'].append(sub_segment)

        # crossings
        intersection['pedestrian_crossing_list'] = []
        if number_of_traffic_signals > 0:
            result = self.selected_db.fetch_data("SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, crossing_street_name, tags \
                    from pedestrian_crossings where intersection_id = %d" % osm_id)
            for row in result:
                signal = self.create_pedestrian_crossing(int(row['id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['crossing_street_name'])
                intersection['pedestrian_crossing_list'].append(signal)
        return intersection


    def create_entrance(self, osm_id, lat, lon, tags, entrance_label):
        entrance = {}
        if type(lat) is not float \
                or type(lon) is not float \
                or type(tags) is not dict:
            return entrance
        entrance = self.create_way_point(osm_id, lat, lon, tags)
        if entrance == {}:
            return entrance
        # add entrance label
        entrance['label'] = entrance_label
        # parse address
        address_data = self.extract_address(tags)
        if address_data:
            entrance.update(address_data)
        # name
        if entrance.get("name") == entrance.get("sub_type"):
            if entrance.get("display_name"):
                entrance['name'] = entrance['display_name']
            else:
                entrance['name'] = self.translator.translate("entrance", entrance_label)
        # type and subtype
        entrance['type'] = "entrance"
        entrance['sub_type'] = self.translator.translate("entrance", entrance_label)
        return entrance


    def create_pedestrian_crossing(self, osm_id, lat, lon, tags, crossing_street_name):
        crossing = {}
        if type(lat) is not float \
                or type(lon) is not float \
                or type(tags) is not dict:
            return crossing
        crossing = self.create_way_point(osm_id, lat, lon, tags)
        if crossing == {}:
            return crossing
        crossing['type'] = "pedestrian_crossing"

        # sub type
        if "crossing" in tags:
            crossing['sub_type'] = self.translator.translate("crossing", tags['crossing'])
        elif "highway" in tags and tags['highway'] == "crossing" \
                and "crossing_ref" in tags and tags['crossing_ref'] in ["pelican", "toucan", "zebra"]:
            crossing['sub_type'] = self.translator.translate("crossing", tags['crossing_ref'])
        elif "highway" in tags and tags['highway'] == "traffic_signals":
            crossing['sub_type'] = self.translator.translate("highway", "traffic_signals")
        elif "railway" in tags and tags['railway'] == "crossing":
            crossing['sub_type'] = self.translator.translate("railway", "crossing")
        else:
            crossing['sub_type'] = self.translator.translate("crossing", "unknown")

        # name
        if crossing_street_name != None:
            crossing['name'] = crossing_street_name
        else:
            crossing['name'] = crossing['sub_type']

        # traffic signals attributes
        if "traffic_signals:sound" in tags:
            if tags['traffic_signals:sound'] == "no":
                crossing['traffic_signals_sound'] = 0
            elif tags['traffic_signals:sound'] in ["locate", "walk", "yes"]:
                crossing['traffic_signals_sound'] = 1
        if "traffic_signals:vibration" in tags:
            if tags['traffic_signals:vibration'] == "no":
                crossing['traffic_signals_vibration'] = 0
            elif tags['traffic_signals:vibration'] == "yes":
                crossing['traffic_signals_vibration'] = 1
        return crossing


    def create_poi(self, poi_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances):
        poi = {}
        if type(poi_id) is not int \
                or type(lat) is not float \
                or type(lon) is not float \
                or type(tags) is not dict \
                or type(outer_building_id) is not int \
                or type(number_of_entrances) is not int:
            return poi
        poi = self.create_way_point(osm_id, lat, lon, tags)
        if poi == {}:
            return poi

        # parse address
        address_data = self.extract_address(tags)
        if address_data:
            poi.update(address_data)

        # type and subtype
        poi['type'] = "poi"
        poi['sub_type'] = ""
        if "amenity" in tags:
            if "cuisine" in tags:
                poi['sub_type'] = "%s (%s)" % (self.translator.translate("amenity", tags['amenity']),
                        self.translator.translate("cuisine", tags['cuisine']))
            elif "vending" in tags:
                poi['sub_type'] = "%s (%s)" % (self.translator.translate("amenity", tags['amenity']),
                        self.translator.translate("vending", tags['vending']))
            else:
                poi['sub_type'] = self.translator.translate("amenity", tags['amenity'])
        elif "bridge" in tags:
            poi['sub_type'] = self.translator.translate("bridge", tags['bridge'])
        elif "tourism" in tags:
            poi['sub_type'] = self.translator.translate("tourism", tags['tourism'])
        elif "historic" in tags:
            poi['sub_type'] = self.translator.translate("historic", tags['historic'])
        elif "leisure" in tags:
            if "sport" in tags:
                poi['sub_type'] = "%s (%s)" % (self.translator.translate("leisure", tags['leisure']),
                        self.translator.translate("sport", tags['sport']))
            else:
                poi['sub_type'] = self.translator.translate("leisure", tags['leisure'])
        elif "man_made" in tags:
            poi['sub_type'] = self.translator.translate("man_made", tags['man_made'])
        elif "natural" in tags:
            poi['sub_type'] = self.translator.translate("natural", tags['natural'])
        elif "shop" in tags:
            poi['sub_type'] = self.translator.translate("shop", tags['shop'])
        elif "aeroway" in tags:
            poi['sub_type'] = self.translator.translate("aeroway", tags['aeroway'])
        elif "building" in tags:
            if tags['building'] == "yes":
                poi['sub_type'] = self.translator.translate("building", "building")
            else:
                poi['sub_type'] = self.translator.translate("building", tags['building'])
        elif "display_name" in poi:
            poi['type'] = "street_address"
            poi['sub_type'] = self.translator.translate("poi", "address")

        # name
        if "name" in tags:
            poi['name'] = tags['name']
        elif "description" in tags:
            poi['name'] = tags['description']
        elif "operator" in tags:
            poi['name'] = tags['operator']
        elif "ref" in tags:
            poi['name'] += " (%s)" % tags['ref']
        elif "display_name" in poi:
            poi['name'] = poi['display_name']
        else:
            poi['name'] = poi['sub_type']

        # contact
        if "contact:website" in tags:
            poi['website'] = tags['contact:website']
        elif "website" in tags:
            poi['website'] = tags['website']
        if "contact:email" in tags:
            poi['email'] = tags['contact:email']
        elif "email" in tags:
            poi['email'] = tags['email']
        if "contact:phone" in tags:
            poi['phone'] = tags['contact:phone']
        elif "phone" in tags:
            poi['phone'] = tags['phone']
        if "opening_hours" in tags:
            poi['opening_hours'] = tags['opening_hours']

        # outer building
        poi['is_inside'] = {}
        if outer_building_id > 0:
            try:
                result = self.selected_db.fetch_data("SELECT ST_X(geom) as x, ST_Y(geom) as y, tags \
                        from outer_buildings where id = %d" % outer_building_id)[0]
                lat = result['y']
                lon = result['x']
                tags = self.parse_hstore_column(result['tags'])
                poi['is_inside'] = self.create_poi(0, 0, lat, lon, tags, 0, 0)
            except IndexError as e:
                poi['is_inside'] = {}

        # entrances
        poi['entrance_list'] = []
        if number_of_entrances > 0:
            result = self.selected_db.fetch_data("SELECT entrance_id, ST_X(geom) as lon, ST_Y(geom) as lat, label, tags \
                    from entrances where poi_id = %d ORDER BY class" % poi_id)
            for row in result:
                entrance = self.create_entrance(row['entrance_id'], row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['label'])
                poi['entrance_list'].append(entrance)
        return poi


    def create_station(self, station_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances, number_of_lines):
        station = {}
        if type(station_id) is not int \
                or type(lat) is not float \
                or type(lon) is not float \
                or type(tags) is not dict \
                or type(outer_building_id) is not int \
                or type(number_of_entrances) is not int \
                or type(number_of_lines) is not int:
            return poi
        station = self.create_poi(station_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances)
        if station == {}:
            return station

        # parse tags
        station['type'] = "station"
        station['sub_type'] = self.translator.translate("public_transport", "unknown")
        station['vehicles'] = []
        if "highway" in tags and tags['highway'] == "bus_stop":
            if "bus" not in station['vehicles']:
                station['vehicles'].append("bus")
        if "railway" in tags and tags['railway'] == "tram_stop":
            if "tram" not in station['vehicles']:
                station['vehicles'].append("tram")
        if "train" in tags and tags['train'] == "yes":
            if "train" not in station['vehicles']:
                station['vehicles'].append("train")
        if "subway" in tags and tags['subway'] == "yes":
            if "subway" not in station['vehicles']:
                station['vehicles'].append("subway")
        if "monorail" in tags and tags['monorail'] == "yes":
            if "monorail" not in station['vehicles']:
                station['vehicles'].append("monorail")
        if "light_rail" in tags and tags['light_rail'] == "yes":
            if "light_rail" not in station['vehicles']:
                station['vehicles'].append("light_rail")
        if "bus" in tags and tags['bus'] == "yes":
            if "bus" not in station['vehicles']:
                station['vehicles'].append("bus")
        if "tram" in tags and tags['tram'] == "yes":
            if "tram" not in station['vehicles']:
                station['vehicles'].append("tram")
        if "aerialway" in tags and tags['aerialway'] == "yes":
            if "aerialway" not in station['vehicles']:
                station['vehicles'].append("aerialway")
        if "ferry" in tags and tags['ferry'] == "yes":
            if "ferry" not in station['vehicles']:
                station['vehicles'].append("ferry")
        if "railway" in tags and (tags['railway'] == "station" or tags['railway'] == "halt"):
            if "station" in tags and tags['station'] == "subway":
                if "subway" not in station['vehicles']:
                    station['vehicles'].append("subway")
            elif "station" in tags and tags['station'] == "light_rail":
                if "light_rail" not in station['vehicles']:
                    station['vehicles'].append("light_rail")
            else:
                if len(station['vehicles']) == 0:
                    station['vehicles'].append("train")
        if len(station['vehicles']) > 0:
            station['sub_type'] = ""
            for vehicle in station['vehicles']:
                station['sub_type'] += "%s, " % self.translator.translate("public_transport", vehicle)
            if station['sub_type'].endswith(", "):
                station['sub_type'] = station['sub_type'][0:station['sub_type'].__len__()-2]

        # transport lines
        station['lines'] = []
        if number_of_lines > 0:
            result = self.selected_db.fetch_data("SELECT DISTINCT line, direction, type \
                    from transport_lines where poi_id = %d ORDER BY type" % station_id)
            for row in result:
                if "line" not in row:
                    continue
                line = {"nr":row['line'], "to":""}
                if "direction" in row and row['direction'] != None:
                    line['to'] = row['direction']
                station['lines'].append(line)
        return station


    #####
    # some helper functions
    #####

    def parse_hstore_column(self, hstore_string):
        hstore = {}
        # cut the first and last "
        hstore_string = hstore_string[1:hstore_string.__len__()-1]
        for entry in hstore_string.split("\", \""):
            keyvalue = entry.split("\"=>\"")
            if len(keyvalue) != 2:
                continue
            hstore[keyvalue[0]] = keyvalue[1]
        return hstore



    def extract_address(self, tags):
        addr_dict = {}
        # street and house number
        house_number = tags.get("addr:housenumber")
        if house_number:
            addr_dict['house_number'] = house_number
        road = tags.get("addr:street")
        if road:
            addr_dict['road'] = road
        # suburb and district
        suburb = tags.get("addr:suburb")
        if suburb:
            addr_dict['suburb'] = suburb
        city_district = tags.get("addr:district")
        if city_district:
            addr_dict['city_district'] = city_district
        # postcode, city, state and country
        postcode = tags.get("addr:postcode")
        if postcode:
            addr_dict['postcode'] = postcode
        city = tags.get("addr:city")
        if city:
            addr_dict['city'] = city
        state = tags.get("addr:state")
        if state:
            addr_dict['state'] = state
        country = tags.get("addr:country")
        if country:
            addr_dict['country'] = country
        # display name
        if (road and house_number) or (road and city):
            addr_list = []
            if road and house_number:
                if self.translator.language == "de":
                    addr_list.append("%s %s" % (road, house_number))
                else:
                    addr_list.append(house_number)
                    addr_list.append(road)
            else:
                addr_list.append(road)
            if postcode:
                addr_list.append(postcode)
            if city:
                addr_list.append(city)
            addr_dict['display_name'] = ', '.join(addr_list)
        return addr_dict


    # function to group poi tags into categories
    # an overview over commonly used tags can be found at:
    # http://wiki.openstreetmap.org/wiki/Map_Features
    def create_tags(self, tag_list):
        tags = {}
        tags['intersection'] = ""
        tags['station'] = ""
        tags['poi'] = ""
        tags['entrance'] = ""
        tags['pedestrian_crossings'] = ""

        # prepare tag list
        if type(tag_list) != type([]):
            tag_list = [tag_list]

        for t in tag_list:
            if t == "transportation_class_1":
                tags['station'] += " or (" \
                        "tags->'amenity' = 'bus_station' or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'bus' = 'yes' or tags->'highway' = 'bus_stop')) or " \
                        "(tags->'highway' = 'bus_stop' and not tags ? 'public_transport') or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'tram' = 'yes' or tags->'railway' = 'tram_stop')) or " \
                        "(tags->'railway' = 'tram_stop' and not tags ? 'public_transport') or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'ferry' = 'yes' or tags->'amenity' = 'ferry_terminal')) or " \
                        "(tags->'amenity' = 'ferry_terminal' and not tags ? 'public_transport') or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'aerialway' = 'yes' or tags->'aerialway' = 'station')) or " \
                        "(tags->'aerialway' = 'station' and not tags ? 'public_transport')" \
                        ")"

            if t == "transportation_class_2":
                tags['station'] += " or (" \
                        "tags->'railway' = 'station' or " \
                        "tags->'railway' = 'halt'" \
                        ")"

            if t == "transport_bus_tram":
                tags['station'] += " or (" \
                        "tags->'amenity' = 'bus_station' or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'bus' = 'yes' or tags->'highway' = 'bus_stop')) or " \
                        "(tags->'highway' = 'bus_stop' and not tags ? 'public_transport') or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'tram' = 'yes' or tags->'railway' = 'tram_stop')) or " \
                        "(tags->'railway' = 'tram_stop' and not tags ? 'public_transport')" \
                        ")"

            if t == "transport_train_lightrail_subway":
                tags['station'] += " or (" \
                        "tags->'railway' = 'station' or " \
                        "tags->'railway' = 'halt'" \
                        ")"

            if t == "transport_airport_ferry_aerialway":
                tags['poi'] += " or (" \
                        "tags->'aeroway' = 'aerodrome' or " \
                        "tags->'aeroway' = 'terminal'" \
                        ")"
                tags['station'] += " or (" \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'ferry' = 'yes' or tags->'amenity' = 'ferry_terminal')) or " \
                        "(tags->'amenity' = 'ferry_terminal' and not tags ? 'public_transport') or " \
                        "(tags->'public_transport' = 'stop_position' and " \
                            "(tags->'aerialway' = 'yes' or tags->'aerialway' = 'station')) or " \
                        "(tags->'aerialway' = 'station' and not tags ? 'public_transport')" \
                        ")"

            if t == "transport_taxi":
                tags['poi'] += " or (" \
                        "tags->'amenity' = 'taxi'" \
                        ")"

            if t == "food":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"cafe\", \"bbq\", \"fast_food\", \"restaurant\", \"bar\", " \
                        "\"pub\", \"drinking_water\", \"biergarten\", \"ice_cream\"}')"

            if t == "entertainment":
                tags['poi'] += " or (" \
                        "tags->'amenity' = ANY('{" \
                            "\"arts_centre\", \"Brothel\", \"Casino\", \"Cinema\", \"community_centre\", " \
                            "\"fountain\", \"planetarium\", \"social_centre\", \"nightclub\", " \
                            "\"stripclub\", \"studio\", \"swingerclub\", \"theatre\", \"youth_centre\" " \
                        "}') or " \
                        "tags ? 'leisure'" \
                        ")"

            if t == "tourism":
                tags['poi'] += " or (" \
                        "tags->'amenity' = " \
                            "ANY('{\"crypt\", \"place_of_worship\", \"shelter\"}') or " \
                        "tags->'tourism' != '' or " \
                        "tags->'historic' != ''" \
                        ")"

            if t == "nature":
                tags['poi'] += " or (" \
                        "tags->'natural' = ANY('{" \
                            "\"water\", \"glacier\", \"beach\", \"spring\", " \
                            "\"volcano\", \"peak\", \"cave_entrance\", \"rock\", \"stone\"}')" \
                        ")"

            if t == "finance":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"atm\", \"bank\", \"bureau_de_change\"}')"

            if t == "shop":
                tags['poi'] += " or (" \
                        "tags->'amenity' = " \
                            "ANY('{\"fuel\", \"marketplace\", \"shop\", \"shopping\", \"pharmacy\", " \
                            "\"Supermarket\", \"post_office\", \"vending_machine\", \"veterinary\"}') or " \
                        "tags->'building' = 'shop' or " \
                        "tags->'craft' != '' or " \
                        "tags->'office' != '' or " \
                        "tags->'shop' != ''" \
                        ")"

            if t == "health":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"pharmacy\", \"doctors\", \"dentist\", \"hospital\", \"health_centre\", " \
                            "\"baby_hatch\", \"clinic\", \"nursing_home\", \"social_facility\", " \
                            "\"retirement_home\", \"sauna\", \"shower\", \"toilets\"}')"

            if t == "education":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"school\", \"college\", \"university\", \"library\", " \
                            "\"kindergarten\", \"Dormitory\", \"auditorium\", \"preschool\"}')" 

            if t == "public_service":
                tags['poi'] += " or (" \
                        "tags->'amenity' = " \
                            "ANY('{\"townhall\", \"public_building\", \"embassy\", \"courthouse\", " \
                            "\"police\", \"prison\", \"fire_station\", \"register_office\", " \
                            "\"shelter\", \"grave_yard\", \"crematorium\", \"village_hall\"}')" \
                        ")"

            if t == "all_buildings_with_name":
                tags['poi'] += " or (" \
                        "(tags ? 'building' and tags ? 'name')" \
                        ")"

            if t == "surveillance":
                tags['poi'] += " or (" \
                        "tags->'man_made' = 'surveillance'" \
                        ")"

            if t == "bench":
                tags['poi'] += " or (" \
                        "tags->'amenity' = 'bench'" \
                        ")"

            if t == "trash":
                tags['poi'] += " or (" \
                        "tags->'amenity' = ANY('{\"recycling\", \"waste_basket\", \"waste_disposal\"}')" \
                        ")"

            if t == "bridge":
                tags['poi'] += " or (" \
                        "(tags ? 'bridge' AND tags ? 'name')" \
                        ")"

        # clean strings
        if tags['station'].startswith(" or "):
            tags['station'] = "(%s)" % tags['station'][4:]
        if tags['poi'].startswith(" or "):
            tags['poi'] = "(%s)" % tags['poi'][4:]

        # intersections
        if "named_intersection" in tag_list and "other_intersection" in tag_list:
            tags['intersection'] = "all"
        elif "named_intersection" in tag_list:
            tags['intersection'] = "name"
        elif "other_intersection" in tag_list:
            tags['intersection'] = "other"

        # entrances and pedestrian crossings
        if "entrance" in tag_list:
            tags['entrance'] = "entrance"
        if "pedestrian_crossings" in tag_list:
            tags['pedestrian_crossings'] = "pedestrian_crossings"
        return tags


    def insert_into_poi_list(self, poi_list, entry, lat, lon):
        if not entry \
                or "name" not in entry \
                or "lat" not in entry \
                or "lon" not in entry:
            return poi_list
        entry['distance'] = geometry.distance_between_two_points(lat, lon, entry['lat'], entry['lon'])
        entry['bearing'] = geometry.bearing_between_two_points(lat, lon, entry['lat'], entry['lon'])
        # add in pois list sorted by distance
        if len(poi_list) == 0:
            poi_list.append(entry)
        else:
            inserted = False
            for index in range(0, len(poi_list)):
                if entry['distance'] < poi_list[index]['distance']:
                    poi_list.insert(index, entry)
                    inserted = True
                    break
            if inserted == False:
                poi_list.append(entry)
        return poi_list


    class POICreationError(LookupError):
        """ is called, when the creation of the next intersection list failed """

