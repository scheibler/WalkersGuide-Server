#!/usr/bin/python
# -*- coding: utf-8 -*-

from db_control import DBControl
from translator import Translator
from config import Config
import geometry
import math, time

class POI:

    def __init__(self, session_id, translator_object, hide_log_messages=False):
        self.session_id = session_id
        self.translator = translator_object
        self.hide_log_messages = hide_log_messages

    def get_poi(self, lat, lon, radius, tag_list, search=""):
        # tags and limits
        tags = self.create_tags(tag_list)
        limits = {}
        limits['station'] = [25, 100, 250, 500, 1000]
        limits['intersection'] = [250, 1000, 2500, 5000, 10000]
        limits['poi'] = [500, 2500, 7500, 20000, 40000]
        limits['traffic_signals'] = [25, 100, 250, 500, 1000]
    
        # prepare search strings
        if search != "":
            search = search.replace(" ", "%").lower()
            search_poi = "("
            search_poi += "LOWER(tags->'name') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'amenity') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'cuisine') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'addr:street') LIKE '%%%s%%' or " % search
            search_poi += "LOWER(tags->'street') LIKE '%%%s%%'" % search
            search_poi += ")"
            search_traffic_signals = "LOWER(crossing_street_name) LIKE '%%%s%%'" % search
            search_other = "LOWER(name) LIKE '%%%s%%'" % search
        else:
            search_poi = ""
            search_traffic_signals = ""
            search_other = ""

        # start querys
        poi_list = []
        ts = time.time()
        # intersections
        if tags['intersection'] != "":
            t1 = time.time()
            if tags['intersection'] == "name":
                # all bigger intersections
                if search_poi != "":
                    where_clause = "number_of_streets_with_name > 1 and %s" % (search_other)
                else:
                    where_clause = "number_of_streets_with_name > 1 \
                            and ST_Distance(geom::geography, 'POINT(%f %f)'::geography) < %d" % (lon, lat, radius)
            elif tags['intersection'] == "other":
                # where clause for nameless intersections
                if search_poi != "":
                    where_clause = "number_of_streets_with_name <= 1 and %s" % (search_other)
                else:
                    where_clause = "number_of_streets_with_name <= 1 \
                            and ST_Distance(geom::geography, 'POINT(%f %f)'::geography) < %d" % (lon, lat, radius)
            else:
                # all intersections
                if search_poi != "":
                    where_clause = "%s" % (search_other)
                else:
                    where_clause = "ST_Distance(geom::geography, 'POINT(%f %f)'::geography) < %d" \
                            % (lon, lat, radius)
            # find the smallest limit for the given radius
            smallest_limit = limits['intersection'][-1]
            if search_poi == "":
                for limit in limits['intersection']:
                    result = DBControl().fetch_data("\
                            with closest_intersections as ( \
                                SELECT * from %s ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                                LIMIT %d \
                            ) \
                            SELECT round(st_distance(geom::geography, 'point(%f %f)'::geography)) AS distance \
                                from closest_intersections ORDER BY geom <-> 'point(%f %f)' DESC \
                                LIMIT 1" \
                            % (Config().get_param("intersection_table"), lon, lat, limit,
                                lon, lat, lon, lat))[0]
                    if result['distance'] > radius:
                        smallest_limit = limit
                        if self.hide_log_messages == False:
                            print "limit = %d, distance = %d" % (smallest_limit, result['distance'])
                        break
                    # check for cancel command
                    if Config().has_session_id_to_remove(self.session_id):
                        Config().confirm_removement_of_session_id(self.session_id)
                        return
            # query data
            # print "where = %s" % where_clause
            result = DBControl().fetch_data("\
                    WITH nearest_intersections AS( \
                        SELECT * from %s ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                        LIMIT %d \
                    ) \
                    SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, name, tags, number_of_streets, \
                        number_of_streets_with_name, number_of_traffic_signals \
                        from nearest_intersections where %s" \
                    % (Config().get_param("intersection_table"), lon, lat,
                        smallest_limit, where_clause))
            t2 = time.time()
            for row in result:
                intersection_id = int(row['id'])
                intersection_tags = self.parse_hstore_column(row['tags'])
                intersection = self.create_intersection(intersection_id, row['lat'], row['lon'], row['name'], intersection_tags, row['number_of_streets'],
                        row['number_of_streets_with_name'], row['number_of_traffic_signals'])
                poi_list = self.insert_into_poi_list(poi_list, intersection, lat, lon)
                # prevent accidental queries with more than 1000 results
                if poi_list.__len__() > 1000:
                    break
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print "intersection gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2))

        # stations
        if tags['station'] != "":
            t1 = time.time()
            smallest_limit = limits['station'][-1]
            if search_poi != "":
                where_clause = "%s and %s" % (tags['station'], search_poi)
            else:
                where_clause = "%s and ST_Distance(geom::geography, 'POINT(%f %f)'::geography) < %d" \
                        % (tags['station'], lon, lat, radius)
                # find the smallest limit for the given radius
                for limit in limits['station']:
                    result = DBControl().fetch_data("\
                            with closest_stations as ( \
                                SELECT * from stations ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                                LIMIT %d \
                            ) \
                            SELECT round(st_distance(geom::geography, 'point(%f %f)'::geography)) AS distance \
                                from closest_stations ORDER BY geom <-> 'point(%f %f)' DESC \
                                LIMIT 1" \
                            % (lon, lat, limit, lon, lat, lon, lat))[0]
                    if result['distance'] > radius:
                        smallest_limit = limit
                        if self.hide_log_messages == False:
                            print "limit = %d, distance = %d" % (smallest_limit, result['distance'])
                        break
                    # check for cancel command
                    if Config().has_session_id_to_remove(self.session_id):
                        Config().confirm_removement_of_session_id(self.session_id)
                        return
            # print "where = %s" % where_clause
            result = DBControl().fetch_data("\
                    WITH nearest_poi AS( \
                        SELECT * from stations \
                        ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                        LIMIT %d \
                    ) \
                    SELECT id, osm_id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, outer_building_id, \
                        number_of_entrances, number_of_lines from nearest_poi where %s" \
                    % (lon, lat, smallest_limit, where_clause))
            t2 = time.time()
            for row in result:
                station_id = int(row['id'])
                osm_id = int(row['osm_id'])
                station_tags = self.parse_hstore_column(row['tags'])
                outer_building_id = int(row['outer_building_id'])
                station = self.create_station(station_id, osm_id, row['lat'], row['lon'], station_tags, outer_building_id,
                        row['number_of_entrances'], row['number_of_lines'])
                poi_list = self.insert_into_poi_list(poi_list, station, lat, lon)
                # prevent accidental queries with more than 1000 results
                if poi_list.__len__() > 1000:
                    break
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print "station gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2))

        # poi
        if tags['poi'] != "":
            t1 = time.time()
            smallest_limit = limits['poi'][-1]
            if search_poi != "":
                where_clause = "%s and %s" % (tags['poi'], search_poi)
            else:
                where_clause = "%s and ST_Distance(geom::geography, 'POINT(%f %f)'::geography) < %d" \
                        % (tags['poi'], lon, lat, radius)
                for limit in limits['poi']:
                    result = DBControl().fetch_data("\
                            with closest_poi AS ( \
                                SELECT * from poi ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                                LIMIT %d \
                            ) \
                            SELECT round(st_distance(geom::geography, 'point(%f %f)'::geography)) AS distance \
                                from closest_poi ORDER BY geom <-> 'point(%f %f)' DESC \
                                LIMIT 1" \
                            % (lon, lat, limit, lon, lat, lon, lat))[0]
                    if result['distance'] > radius:
                        smallest_limit = limit
                        if self.hide_log_messages == False:
                            print "limit = %d, distance = %d" % (smallest_limit, result['distance'])
                        break
                    # check for cancel command
                    if Config().has_session_id_to_remove(self.session_id):
                        Config().confirm_removement_of_session_id(self.session_id)
                        return
            # print "where = %s" % where_clause
            result = DBControl().fetch_data("\
                    WITH nearest_poi AS( \
                        SELECT * from poi \
                        ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                        LIMIT %d \
                    ) \
                    SELECT id, osm_id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, outer_building_id, \
                        number_of_entrances from nearest_poi where %s" \
                    % (lon, lat, smallest_limit, where_clause))
            t2 = time.time()
            for row in result:
                poi_id = int(row['id'])
                osm_id = int(row['osm_id'])
                poi_tags = self.parse_hstore_column(row['tags'])
                outer_building_id = int(row['outer_building_id'])
                poi = self.create_poi(poi_id, osm_id, row['lat'], row['lon'], poi_tags, outer_building_id, row['number_of_entrances'])
                poi_list = self.insert_into_poi_list(poi_list, poi, lat, lon)
                # prevent accidental queries with more than 1000 results
                if poi_list.__len__() > 1000:
                    break
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print "poi gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2))

        # traffic signals
        if tags['traffic_signals'] != "":
            t1 = time.time()
            smallest_limit = limits['traffic_signals'][-1]
            if search_traffic_signals != "":
                where_clause = search_traffic_signals
            else:
                where_clause = "ST_Distance(geom::geography, 'POINT(%f %f)'::geography) < %d" \
                        % (lon, lat, radius)
                for limit in limits['traffic_signals']:
                    result = DBControl().fetch_data("\
                            with closest_traffic_signals AS ( \
                                SELECT * from traffic_signals ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                                LIMIT %d \
                            ) \
                            SELECT round(st_distance(geom::geography, 'point(%f %f)'::geography)) AS distance \
                                from closest_traffic_signals ORDER BY geom <-> 'point(%f %f)' DESC \
                                LIMIT 1" \
                            % (lon, lat, limit, lon, lat, lon, lat))[0]
                    if result['distance'] > radius:
                        smallest_limit = limit
                        if self.hide_log_messages == False:
                            print "limit = %d, distance = %d" % (smallest_limit, result['distance'])
                        break
                    # check for cancel command
                    if Config().has_session_id_to_remove(self.session_id):
                        Config().confirm_removement_of_session_id(self.session_id)
                        return
            result = DBControl().fetch_data("\
                    WITH nearest_traffic_signals AS( \
                        SELECT * from traffic_signals \
                        ORDER BY geom <-> 'POINT(%f %f)'::geometry \
                        LIMIT %d \
                    ) \
                    SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, crossing_street_name \
                    from nearest_traffic_signals where %s" \
                    % (lon, lat, smallest_limit, where_clause))
            t2 = time.time()
            for row in result:
                signal = self.create_poi(0, int(row['id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), 0, 0)
                signal['name'] = self.translator.translate("highway", "traffic_signals")
                if row['crossing_street_name'] != "":
                    signal['name'] += ": %s" % row['crossing_street_name']
                poi_list = self.insert_into_poi_list(poi_list, signal, lat, lon)
                # prevent accidental queries with more than 1000 results
                if poi_list.__len__() > 1000:
                    break
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return
            t3 = time.time()
            if self.hide_log_messages == False:
                print "traffic signals gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2))

        te = time.time()
        if self.hide_log_messages == False:
            print "gesamtzeit: %.2f;   anzahl entries = %d" % ((te-ts), poi_list.__len__())
        return poi_list

    #####
    # create the poi objects
    #####

    def create_way_point_by_id(self, osm_node_id):
        try:
            result = DBControl().fetch_data("SELECT ST_X(geom) as x, ST_Y(geom) as y, tags \
                    from nodes where id = %d" % osm_node_id)[0]
        except IndexError as e:
            return {}
        osm_node_id = int(osm_node_id)
        lat = result['y']
        lon = result['x']
        tags = self.parse_hstore_column(result['tags'])
        return self.create_way_point(osm_node_id, lat, lon, tags)

    def create_way_point(self, osm_node_id, lat, lon, tags):
        way_point = {}
        if type(lat) is not float or type(lon) is not float or type(tags) is not dict:
            return way_point
        way_point['lat'] = lat
        way_point['lon'] = lon
        way_point['node_id'] = osm_node_id
        way_point['type'] = "way_point"
        way_point['sub_type'] = self.translator.translate("poi", "way_point")
        if tags.has_key("name"):
            way_point['name'] = tags['name']
        else:
            way_point['name'] = way_point['sub_type']
        if tags.has_key("tactile_paving"):
            if tags['tactile_paving'] == "yes":
                way_point['tactile_paving'] = 1
            if tags['tactile_paving'] == "no":
                way_point['tactile_paving'] = 0
        if tags.has_key("wheelchair"):
            if tags['wheelchair'] == "no":
                way_point['wheelchair'] = 0
            if tags['wheelchair'] == "limited":
                way_point['wheelchair'] = 1
            if tags['wheelchair'] == "yes":
                way_point['wheelchair'] = 2
        return way_point

    def create_way_segment_by_id(self, osm_way_id, walking_reverse=False):
        try:
            result = DBControl().fetch_data("SELECT tags \
                    from ways where id = %d" % osm_way_id)[0]
        except IndexError as e:
            return {}
        osm_way_id = int(osm_way_id)
        tags = self.parse_hstore_column(result['tags'])
        return self.create_way_segment(osm_way_id, tags, walking_reverse)

    def create_way_segment(self, osm_way_id, tags, walking_reverse=False):
        segment = {}
        if type(tags) is not dict or type(walking_reverse) is not bool:
            return segment
        segment['pois'] = []
        segment['way_id'] = osm_way_id
        segment['type'] = "footway"
        segment['sub_type'] = ""
        if tags.has_key("highway"):
            segment['sub_type'] = self.translator.translate("highway", tags['highway'])
            if tags.has_key("railway") and tags['railway'] == "tram":
                segment['tram'] = 1
        elif tags.has_key("railway"):
            segment['sub_type'] = self.translator.translate("railway", tags['railway'])
        if tags.has_key("surface"):
            segment['surface'] = self.translator.translate("surface", tags['surface'])
        if tags.has_key("lanes"):
            segment['lanes'] = tags['lanes']
        if tags.has_key("tracktype"):
            segment['tracktype'] = tags['tracktype']
        if tags.has_key("sidewalk"):
            if tags['sidewalk'] == "no" or tags['sidewalk'] == "none":
                segment['sidewalk'] = 0
            if tags['sidewalk'] == "left":
                if walking_reverse == False:
                    segment['sidewalk'] = 1
                else:
                    segment['sidewalk'] = 2
            if tags['sidewalk'] == "right":
                if walking_reverse == False:
                    segment['sidewalk'] = 2
                else:
                    segment['sidewalk'] = 1
            if tags['sidewalk'] == "both":
                segment['sidewalk'] = 3
        if tags.has_key("tactile_paving"):
            if tags['tactile_paving'] == "yes":
                segment['tactile_paving'] = 1
            if tags['tactile_paving'] == "no":
                segment['tactile_paving'] = 0
        if tags.has_key("name"):
            segment['name'] = tags['name']
        else:
            if segment.has_key("surface"):
                segment['name'] = "%s (%s)" % (segment['sub_type'], segment['surface'])
            elif segment.has_key("tracktype"):
                segment['name'] = "%s (%s)" % (segment['sub_type'], segment['tracktype'])
            else:
                segment['name'] = segment['sub_type']
        return segment

    def create_intersection_by_id(self, osm_id):
        intersection_table = Config().get_param("intersection_table")
        try:
            result = DBControl().fetch_data("SELECT ST_X(geom) as x, ST_Y(geom) as y, name, tags, \
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
        intersection_table = Config().get_param("intersection_table")
        intersection_table_data = Config().get_param("intersection_data_table")
        intersection = {}
        if type(osm_id) is not int or type(lat) is not float or type(lon) is not float or type(name) is not str or type(tags) is not dict or type(number_of_streets) is not int or type(number_of_streets_with_name) is not int or type(number_of_traffic_signals) is not int:
            return intersection
        intersection = self.create_way_point(osm_id, lat, lon, tags)
        if intersection == {}:
            return intersection

        # traffic lights
        intersection['traffic_signal_list'] = []
        if number_of_traffic_signals > 0:
            result = DBControl().fetch_data("SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, crossing_street_name, tags \
                    from traffic_signals where intersection_id = %d" % osm_id)
            for row in result:
                signal = self.create_poi(0, int(row['id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), 0, 0)
                signal['name'] = "%s (%s)" % (self.translator.translate("highway", "traffic_signals"),
                        row['crossing_street_name'])
                intersection['traffic_signal_list'].append(signal)

        # intersection specific properties
        intersection['name'] = ""
        for street in name.split(","):
            translated_street = self.translator.translate("highway", street.strip())
            if translated_street == street.strip():
                translated_street = self.translator.translate("railway", street.strip())
            intersection['name'] += "%s, " % translated_street
        intersection['name'] = intersection['name'].strip(",")
        intersection['number_of_streets_with_name'] = number_of_streets_with_name
        intersection['type'] = "intersection"
        intersection['sub_type'] = self.translator.translate("crossing", "unknown")
        if tags.has_key("crossing"):
            intersection['sub_type'] = self.translator.translate("crossing", tags['crossing'])
        elif tags.has_key("highway") and tags['highway'] == "traffic_signals":
            intersection['sub_type'] = self.translator.translate("highway", "traffic_signals")
        elif intersection['traffic_signal_list'].__len__() > 0:
            intersection['sub_type'] = self.translator.translate("highway", "traffic_signals")

        # streets
        intersection['sub_points'] = []
        result = DBControl().fetch_data("\
                SELECT way_id, node_id, direction, way_tags, node_tags, \
                    ST_X(geom) as lon, ST_Y(geom) as lat \
                from %s where id = %d" % (intersection_table_data, osm_id))
        for street in result:
            sub_point = self.create_way_point(street['node_id'], street['lat'], street['lon'],
                    self.parse_hstore_column(street['node_tags']))
            if street['direction'] == "B":
                way_segment = self.create_way_segment(street['way_id'],
                        self.parse_hstore_column(street['way_tags']), True)
            else:
                way_segment = self.create_way_segment(street['way_id'],
                        self.parse_hstore_column(street['way_tags']), False)
            for key in way_segment:
                sub_point[key] = way_segment[key]
            sub_point['intersection_bearing'] = geometry.bearing_between_two_points(
                    intersection['lat'], intersection['lon'], sub_point['lat'], sub_point['lon'])
            intersection['sub_points'].append(sub_point)
        return intersection

    def create_poi_by_id(self, poi_id):
        try:
            result = DBControl().fetch_data("SELECT osm_id, ST_X(geom) as x, ST_Y(geom) as y, tags, \
                    outer_building_id, number_of_entrances \
                    from poi where id = %d" % poi_id)[0]
        except IndexError as e:
            return {}
        poi_id = int(poi_id)
        osm_id = int(result['osm_id'])
        lat = result['y']
        lon = result['x']
        tags = self.parse_hstore_column(result['tags'])
        outer_building_id = int(result['outer_building_id'])
        number_of_entrances = result['number_of_entrances']
        return self.create_poi(poi_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances)

    def create_poi(self, poi_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances):
        poi = {}
        if type(poi_id) is not int or type(lat) is not float or type(lon) is not float \
                or type(tags) is not dict or type(outer_building_id) is not int or type(number_of_entrances) is not int:
            return poi
        poi = self.create_way_point(osm_id, lat, lon, tags)
        if poi == {}:
            return poi

        # parse tags
        # address
        address1 = ""
        if tags.has_key("addr:street") and tags.has_key("addr:housenumber"):
            address1 += "%s %s" % (tags['addr:street'], tags['addr:housenumber'])
            if tags.has_key("addr:postcode"):
                address1 += ", %s" % tags['addr:postcode']
            if tags.has_key("addr:city"):
                address1 += " %s" % tags['addr:city']
        address2 = ""
        if tags.has_key("street") and tags.has_key("housenumber"):
            address2 += "%s %s" % (tags['street'], tags['housenumber'])
            if tags.has_key("postcode"):
                address2 += ", %s" % tags['postcode']
            if tags.has_key("city"):
                address2 += " %s" % tags['city']
        if address1.__len__() > 0 or address2.__len__() > 0:
            if address1.__len__() < address2.__len__():
                poi['address'] = address2
            else:
                poi['address'] = address1
        # type and subtype
        poi['type'] = "poi"
        poi['sub_type'] = ""
        if tags.has_key("amenity"):
            if tags.has_key("cuisine"):
                poi['sub_type'] = "%s (%s)" % (self.translator.translate("amenity", tags['amenity']),
                        self.translator.translate("cuisine", tags['cuisine']))
            elif tags.has_key("vending"):
                poi['sub_type'] = "%s (%s)" % (self.translator.translate("amenity", tags['amenity']),
                        self.translator.translate("vending", tags['vending']))
            else:
                poi['sub_type'] = self.translator.translate("amenity", tags['amenity'])
        elif tags.has_key("tourism"):
            poi['sub_type'] = self.translator.translate("tourism", tags['tourism'])
        elif tags.has_key("historic"):
            poi['sub_type'] = self.translator.translate("historic", tags['historic'])
        elif tags.has_key("leisure"):
            if tags.has_key("sport"):
                poi['sub_type'] = "%s (%s)" % (self.translator.translate("leisure", tags['leisure']),
                        self.translator.translate("sport", tags['sport']))
            else:
                poi['sub_type'] = self.translator.translate("leisure", tags['leisure'])
        elif tags.has_key("natural"):
            poi['sub_type'] = self.translator.translate("natural", tags['natural'])
        elif tags.has_key("shop"):
            poi['sub_type'] = self.translator.translate("shop", tags['shop'])
        elif tags.has_key("building"):
            if tags['building'] == "yes":
                poi['sub_type'] = self.translator.translate("building", "building")
            else:
                poi['sub_type'] = self.translator.translate("building", tags['building'])
        elif poi.has_key("address") == True:
            poi['sub_type'] = self.translator.translate("poi", "address")
        if tags.has_key("highway") and tags['highway'] == "traffic_signals":
            poi['sub_type'] = self.translator.translate("highway", "traffic_signals")
        elif tags.has_key("crossing") and tags['crossing'] == "traffic_signals":
            poi['sub_type'] = self.translator.translate("highway", "pedestrian_traffic_signals")
            signals_class = 0
            if tags.has_key("traffic_signals:sound") and tags['traffic_signals:sound'] == "yes":
                signals_class += 1
            if tags.has_key("traffic_signals:vibration") and tags['traffic_signals:vibration'] == "yes":
                signals_class += 2
            if signals_class > 0:
                poi['traffic_signals_accessibility'] = signals_class
        # name
        if tags.has_key("name"):
            poi['name'] = tags['name']
        elif tags.has_key("operator"):
            poi['name'] = tags['operator']
        elif tags.has_key("ref"):
            poi['name'] += " (%s)" % tags['ref']
        elif poi.has_key("address"):
            poi['name'] = poi['address']
        else:
            poi['name'] = poi['sub_type']
        # contact
        if tags.has_key("contact:website"):
            poi['website'] = tags['contact:website']
        elif tags.has_key("website"):
            poi['website'] = tags['website']
        if tags.has_key("contact:email"):
            poi['email'] = tags['contact:email']
        elif tags.has_key("email"):
            poi['email'] = tags['email']
        if tags.has_key("contact:phone"):
            poi['phone'] = tags['contact:phone']
        elif tags.has_key("phone"):
            poi['phone'] = tags['phone']
        if tags.has_key("opening_hours"):
            poi['opening_hours'] = tags['opening_hours']

        # outer building
        poi['is_inside'] = {}
        if outer_building_id > 0:
            try:
                result = DBControl().fetch_data("SELECT ST_X(geom) as x, ST_Y(geom) as y, tags \
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
            result = DBControl().fetch_data("SELECT entrance_id, ST_X(geom) as lon, ST_Y(geom) as lat, label, tags \
                    from entrances where poi_id = %d ORDER BY class" % poi_id)
            for row in result:
                entrance = self.create_way_point(row['entrance_id'], row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']))
                entrance['name'] = self.translator.translate("entrance", row['label'])
                entrance['type'] = "poi"
                entrance['sub_type'] = self.translator.translate("entrance", "entrance")
                entrance['entrance'] = row['label']
                poi['entrance_list'].append(entrance)
        return poi

    def create_station_by_id(self, station_id):
        try:
            result = DBControl().fetch_data("SELECT osm_id, ST_X(geom) as x, ST_Y(geom) as y, tags, \
                    outer_building_id, number_of_entrances, number_of_lines \
                    from stations where id = %d" % station_id)[0]
        except IndexError as e:
            return {}
        station_id = int(station_id)
        osm_id = int(result['osm_id'])
        lat = result['y']
        lon = result['x']
        tags = self.parse_hstore_column(result['tags'])
        outer_building_id = int(result['outer_building_id'])
        number_of_entrances = result['number_of_entrances']
        number_of_lines = result['number_of_lines']
        return self.create_station(station_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances, number_of_lines)

    def create_station(self, station_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances, number_of_lines):
        station = {}
        if type(station_id) is not int or type(lat) is not float or type(lon) is not float or type(tags) is not dict or type(outer_building_id) is not int or type(number_of_entrances) is not int or type(number_of_lines) is not int:
            return poi
        station = self.create_poi(station_id, osm_id, lat, lon, tags, outer_building_id, number_of_entrances)
        if station == {}:
            return station
    
        # parse tags
        station['type'] = "station"
        station['sub_type'] = self.translator.translate("public_transport", "unknown")
        station['vehicles'] = []
        if tags.has_key("highway") and tags['highway'] == "bus_stop":
            if "bus" not in station['vehicles']:
                station['vehicles'].append("bus")
        if tags.has_key("railway") and tags['railway'] == "tram_stop":
            if "tram" not in station['vehicles']:
                station['vehicles'].append("tram")
        if tags.has_key("train") and tags['train'] == "yes":
            if "train" not in station['vehicles']:
                station['vehicles'].append("train")
        if tags.has_key("subway") and tags['subway'] == "yes":
            if "subway" not in station['vehicles']:
                station['vehicles'].append("subway")
        if tags.has_key("monorail") and tags['monorail'] == "yes":
            if "monorail" not in station['vehicles']:
                station['vehicles'].append("monorail")
        if tags.has_key("light_rail") and tags['light_rail'] == "yes":
            if "light_rail" not in station['vehicles']:
                station['vehicles'].append("light_rail")
        if tags.has_key("bus") and tags['bus'] == "yes":
            if "bus" not in station['vehicles']:
                station['vehicles'].append("bus")
        if tags.has_key("tram") and tags['tram'] == "yes":
            if "tram" not in station['vehicles']:
                station['vehicles'].append("tram")
        if tags.has_key("aerialway") and tags['aerialway'] == "yes":
            if "aerialway" not in station['vehicles']:
                station['vehicles'].append("aerialway")
        if tags.has_key("ferry") and tags['ferry'] == "yes":
            if "ferry" not in station['vehicles']:
                station['vehicles'].append("ferry")
        if tags.has_key("railway") and (tags['railway'] == "station" or tags['railway'] == "halt"):
            if tags.has_key("station") and tags['station'] == "subway":
                if "subway" not in station['vehicles']:
                    station['vehicles'].append("subway")
            elif tags.has_key("station") and tags['station'] == "light_rail":
                if "light_rail" not in station['vehicles']:
                    station['vehicles'].append("light_rail")
            else:
                if station['vehicles'].__len__() == 0:
                    station['vehicles'].append("train")
        if station['vehicles'].__len__() > 0:
            station['sub_type'] = ""
            for vehicle in station['vehicles']:
                station['sub_type'] += "%s, " % self.translator.translate("public_transport", vehicle)
            if station['sub_type'].endswith(", "):
                station['sub_type'] = station['sub_type'][0:station['sub_type'].__len__()-2]

        # transport lines
        station['lines'] = []
        if number_of_lines > 0:
            result = DBControl().fetch_data("SELECT DISTINCT line, direction, type \
                    from transport_lines where poi_id = %d ORDER BY type" % station_id)
            for row in result:
                if not row.has_key("line"):
                    continue
                line = {"nr":row['line'], "to":""}
                if row.has_key("direction") and row['direction'] != None:
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
            if keyvalue.__len__() != 2:
                continue
            hstore[keyvalue[0]] = keyvalue[1]
        return hstore

    # function to group poi tags into categories
    # an overview over commonly used tags can be found at:
    # http://wiki.openstreetmap.org/wiki/Map_Features
    def create_tags(self, tag_list):
        tags = {}
        tags['intersection'] = ""
        tags['station'] = ""
        tags['poi'] = ""
        tags['traffic_signals'] = ""

        # prepare tag list
        if type(tag_list) != type([]):
            tag_list = [tag_list]

        for t in tag_list:
            if t in ["transport", "transportation_class_1"]:
                tags['station'] += " or (" \
                        "tags->'highway' = 'bus_stop' or tags->'railway' = 'tram_stop' or " \
                        "tags->'amenity' = 'bus_station' or tags->'amenity' = 'ferry_terminal' or " \
                        "(tags->'public_transport' = 'stop_position' and tags->'bus' = 'yes') or " \
                        "(tags->'public_transport' = 'stop_position' and tags->'tram' = 'yes') or " \
                        "(tags->'public_transport' = 'stop_position' and tags->'ferry' = 'yes')" \
                        ")"
            if t in ["transport", "transportation_class_2"]:
                tags['station'] += " or (" \
                        "tags->'railway' = 'station' or " \
                        "tags->'railway' = 'halt' or " \
                        "tags->'building' LIKE '%station'" \
                        ")"
            if t == "transport":
                tags['poi'] += " or (" \
                        "tags->'amenity' = 'taxi' or " \
                        "tags->'aerialway' = 'station' or " \
                        "tags->'aeroway' = 'terminal'" \
                        ")"
            if t == "food":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"cafe\", \"bbq\", \"fast_food\", \"restaurant\", \"bar\", " \
                        "\"pub\", \"drinking_water\", \"biergarten\", \"ice_cream\"}')"
            if t == "tourism":
                tags['poi'] += " or (" \
                        "tags->'amenity' = " \
                            "ANY('{\"crypt\", \"place_of_worship\"}') or " \
                        "tags->'tourism' != '' or " \
                        "tags->'natural' = 'water' or " \
                        "tags->'historic' != ''" \
                        ")"
            if t == "shop":
                tags['poi'] += " or (" \
                        "tags->'amenity' = " \
                            "ANY('{\"fuel\", \"marketplace\", \"shop\", \"shopping\", " \
                            "\"Supermarket\", \"post_office\", \"vending_machine\"}') or " \
                        "tags->'building' = 'shop' or " \
                        "tags->'craft' != '' or " \
                        "tags->'office' != '' or " \
                        "tags->'shop' != ''" \
                        ")"
            if t == "health":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"pharmacy\", \"doctors\", \"dentist\", \"hospital\", \"health_centre\", " \
                            "\"baby_hatch\", \"clinic\", \"nursing_home\", \"social_facility\", \"veterinary\", " \
                            "\"retirement_home\", \"sauna\", \"shower\", \"toilets\"}')"
            if t == "education":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"school\", \"college\", \"university\", \"library\", " \
                            "\"kindergarten\", \"Dormitory\", \"auditorium\", \"preschool\"}')" 
            if t == "finance":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"atm\", \"bank\", \"bureau_de_change\"}')"
            if t == "entertainment":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"arts_centre\", \"Brothel\", \"Casino\", \"Cinema\", \"community_centre\", " \
                        "\"fountain\", \"planetarium\", \"social_centre\", " \
                        "\"nightclub\", \"stripclub\", \"studio\", \"swingerclub\", \"theatre\", " \
                        "\"youth_centre\"}')"
            if t == "public_service":
                tags['poi'] += " or (" \
                        "tags->'amenity' = " \
                            "ANY('{\"townhall\", \"public_building\", \"embassy\", \"courthouse\", " \
                            "\"police\", \"prison\", \"fire_station\", \"register_office\", " \
                            "\"shelter\", \"grave_yard\", \"crematorium\", \"village_hall\"}') or " \
                        "tags->'leisure' != '' or " \
                        "(tags->'building' != '' and tags->'name' != '')" \
                        ")"
            if t == "trash":
                tags['poi'] += " or tags->'amenity' = " \
                        "ANY('{\"recycling\", \"waste_basket\", \"waste_disposal\"}')"

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

        # traffic signals
        if "traffic_signals" in tag_list:
            tags['traffic_signals'] = "traffic_signals"
        return tags

    def insert_into_poi_list(self, poi_list, entry, lat, lon):
        if entry == {} or entry.has_key("name") == False \
                or entry.has_key("lat") == False or entry.has_key("lon") == False:
            return poi_list
        entry['distance'] = geometry.distance_between_two_points(lat, lon, entry['lat'], entry['lon'])
        entry['bearing'] = geometry.bearing_between_two_points(lat, lon, entry['lat'], entry['lon'])
        # add in pois list sorted by distance
        if poi_list.__len__() == 0:
            poi_list.append(entry)
        else:
            inserted = False
            for index in range(0, poi_list.__len__()):
                if entry['distance'] < poi_list[index]['distance']:
                    poi_list.insert(index, entry)
                    inserted = True
                    break
            if inserted == False:
                poi_list.append(entry)
        return poi_list

