#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging, math, time
from psycopg2 import sql

from . import constants, geometry, statistics
from .config import Config
from .constants import ReturnCode
from .db_control import DBControl
from .helper import WebserverException
from .translator import Translator 


class POI:

    def __init__(self, map_id, session_id, user_language):
        self.selected_db = DBControl(map_id)
        self.session_id = session_id
        self.translator = Translator(user_language)


    def get_hiking_trails(self, lat, lon, radius, order_by="closest"):
        # deprecated: no hiking trails on map versions 1 and 2
        if self.selected_db.map_version == 2:
            raise WebserverException(
                    ReturnCode.MAP_OUTDATED, "Hiking trails not available in map version 2")

        # sql queries
        # boundary box
        boundary_box_query, boundary_box_query_params = self.get_boundary_box_query_and_params(lat, lon, radius)
        # order by
        if order_by == "start":
            order_by_query = sql.SQL("ORDER BY distance_to_start")
        elif order_by == "destination":
            order_by_query = sql.SQL("ORDER BY distance_to_destination")
        else:
            order_by_query = sql.SQL("ORDER BY distance_to_closest")

        table_name = "hiking_trails"
        result = self.selected_db.fetch_all(
                sql.SQL(
                    """
                    WITH closest_trails AS (
                        SELECT * FROM {i_table_name} WHERE {c_where_clause_query})
                    SELECT
                        relation_id,
                        tags,
                        ST_Distance(
                            ST_ClosestPoint(geom, ST_SetSrid(ST_MakePoint({p_lon}, {p_lat}),4326))::geography,
                            ST_SetSrid(ST_MakePoint({p_lon}, {p_lat}),4326)::geography
                        ) AS distance_to_closest,
                        ST_Distance(
                            ST_PointN(geom, 1)::geography,
                            ST_SetSrid(ST_MakePoint({p_lon}, {p_lat}),4326)::geography
                        ) AS distance_to_start,
                        ST_Distance(
                            ST_PointN(geom, -1)::geography,
                            ST_SetSrid(ST_MakePoint({p_lon}, {p_lat}),4326)::geography
                        ) AS distance_to_destination
                    FROM closest_trails {c_order_by_query}
                    """
                    ).format(
                            i_table_name=sql.Identifier(table_name),
                            c_where_clause_query=boundary_box_query,
                            p_lon=sql.Placeholder(name='lon'),
                            p_lat=sql.Placeholder(name='lat'),
                            c_order_by_query=order_by_query),
                    { **boundary_box_query_params, **{"lat":lat, "lon":lon}})

        trail_list = []
        for row in result:
            # parse tags
            trail_tags = self.parse_hstore_column(row['tags'])
            # create trail
            trail = {}
            trail['relation_id'] = int(row['relation_id'])
            trail['name'] = trail_tags.get(
                    "name", self.translator.translate("poi", "hiking_trail"))
            # distances
            trail['distance_to_closest'] = int(row['distance_to_closest'])
            trail['distance_to_start'] = int(row['distance_to_start'])
            trail['distance_to_destination'] = int(row['distance_to_destination'])
            # optional attributes
            if "description" in trail_tags:
                trail['description'] = trail_tags.get("description")
            elif "note" in trail_tags:
                trail['description'] = trail_tags.get("note")
            if "distance" in trail_tags:
                trail['length'] = trail_tags.get("distance")
            if "symbol" in trail_tags:
                trail['symbol'] = trail_tags.get("symbol")
            elif "osmc:symbol" in trail_tags:
                trail['symbol'] = trail_tags.get("osmc:symbol")
            # add to list
            trail_list.append(trail)
        return trail_list


    def get_poi(self, lat, lon, radius, number_of_results, tags, search):
        ts = time.time()
        poi_list = []

        # sql queries
        # boundary box
        boundary_box_query, boundary_box_query_params = self.get_boundary_box_query_and_params(lat, lon, radius)
        # order_by
        order_by_and_limit_query = sql.SQL(
                """
                ORDER BY ST_Distance(geom::geography, 'POINT({p_lon} {p_lat})'::geography)
                LIMIT {p_number_of_results}
                """
                ).format(
                        p_lon=sql.Placeholder(name='lon'),
                        p_lat=sql.Placeholder(name='lat'),
                        p_number_of_results=sql.Placeholder(name='number_of_results'))

        # parse tags
        if not tags:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "No tags")
        elif not isinstance(tags, list):
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "Invalid tags")
        else:
            tag_list = []
            for tag in tags:
                if tag in constants.supported_poi_category_listp:
                    tag_list.append(tag)
                else:
                    logging.warning("Skipping poi tag {}".format(tag))
            if not tag_list:
                raise WebserverException(
                        ReturnCode.NO_POI_TAGS_SELECTED, "tag_list is empty")

        # query params
        where_clause_param_dict = {
                **boundary_box_query_params, **{"lat":lat, "lon":lon}}
        # number of results
        try:
            if number_of_results > 0:
                # increase number of results limit by 10% to counter unparsable poi
                where_clause_param_dict['number_of_results'] = int(number_of_results * 1.1)
            else:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "number_of_results <= 0")
        except TypeError as e:
            if number_of_results:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "Invalid number_of_results")
            else:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "No number_of_results")
        # add escaped search string
        if search:
            if isinstance(search, str):
                where_clause_param_dict['search_term'] = '%{}%'.format(
                        search.replace(" ", "%").lower())
            else:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "Invalid search")


        ###############
        # intersections
        ###############
        intersection_tag_list = ["named_intersection", "other_intersection"]
        if [True for tag in tag_list if tag in intersection_tag_list]:
            t1 = time.time()
            where_clause_query_list = [boundary_box_query]

            # tags
            if "named_intersection" in tag_list and "other_intersection" not in tag_list:
                # only bigger intersections
                where_clause_query_list.append(
                        sql.SQL("number_of_streets_with_name > 1"))
            elif "named_intersection" not in tag_list and "other_intersection" in tag_list:
                # only smaller intersections
                where_clause_query_list.append(
                        sql.SQL("number_of_streets_with_name <= 1"))

            # search
            if search:
                where_clause_query_list.append(
                        sql.SQL(
                            """
                            LOWER(name) LIKE {p_search_term}
                            """
                            ).format(
                                    p_search_term=sql.Placeholder(name='search_term'))
                        )

            table_name = Config().database.get("intersection_table")
            result = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        WITH closest_points AS (
                            SELECT * FROM {i_table_name} WHERE {c_where_clause_query})
                        SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, name, tags, number_of_streets,
                                number_of_streets_with_name, number_of_traffic_signals
                        FROM closest_points {c_order_by_and_limit_query}
                        """
                        ).format(
                                i_table_name=sql.Identifier(table_name),
                                c_where_clause_query=sql.SQL(" AND ").join(where_clause_query_list),
                                c_order_by_and_limit_query=order_by_and_limit_query),
                    where_clause_param_dict)
            t2 = time.time()

            for row in result:
                intersection_id = int(row['id'])
                intersection_tags = self.parse_hstore_column(row['tags'])
                intersection = self.create_intersection(intersection_id, row['lat'], row['lon'], row['name'], intersection_tags, row['number_of_streets'],
                        row['number_of_streets_with_name'], row['number_of_traffic_signals'])
                poi_list = self.insert_into_poi_list(poi_list, intersection, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    raise WebserverException(
                            ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
            t3 = time.time()
            logging.debug("intersection gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))


        ##########
        # stations
        ##########
        station_tag_list = ["transportation_class_1", "transportation_class_2",
                "transport_bus_tram", "transport_train_lightrail_subway", "transport_airport_ferry_aerialway"]
        if [True for tag in tag_list if tag in station_tag_list]:
            t1 = time.time()
            where_clause_query_list = [boundary_box_query]
            # double number of results limit to counter redundant stations
            where_clause_param_dict['number_of_results'] *= 2

            # tags
            tag_query_list = []
            for t in tag_list:
                if t in ["transportation_class_2", "transport_train_lightrail_subway"]:
                    tag_query_list.append(
                            sql.SQL(
                                """
                                   tags->'railway' = 'station'
                                OR tags->'railway' = 'halt'
                                """))
                if t in ["transportation_class_1", "transport_bus_tram"]:
                    tag_query_list.append(
                            sql.SQL(
                                """
                                   tags->'amenity' = 'bus_station'
                                OR (tags->'public_transport' = ANY('{"platform", "stop_position"}')
                                    AND (tags->'bus' = 'yes' OR tags->'highway' = 'bus_stop'))
                                OR (tags->'highway' = 'bus_stop' AND NOT tags ? 'public_transport')
                                OR (tags->'public_transport' = ANY('{"platform", "stop_position"}')
                                    AND (tags->'tram' = 'yes' OR tags->'railway' = 'tram_stop'))
                                OR (tags->'railway' = 'tram_stop' AND NOT tags ? 'public_transport')
                                """))
                if t in ["transportation_class_1", "transport_airport_ferry_aerialway"]:
                    tag_query_list.append(
                            sql.SQL(
                                """
                                   (tags->'public_transport' = 'stop_position'
                                    AND (tags->'ferry' = 'yes' OR tags->'amenity' = 'ferry_terminal'))
                                OR (tags->'amenity' = 'ferry_terminal' AND NOT tags ? 'public_transport')
                                OR (tags->'public_transport' = 'stop_position'
                                    AND (tags->'aerialway' = 'yes' AND tags->'aerialway' = 'station'))
                                OR (tags->'aerialway' = 'station' AND NOT tags ? 'public_transport')
                                """))
            # add to where clause
            where_clause_query_list.append(
                    sql.SQL("({})").format(sql.SQL(" OR ").join(tag_query_list)))

            # search
            if search:
                where_clause_query_list.append(
                        sql.SQL(
                            """
                            LOWER(tags->'name') LIKE {p_search_term}
                            """
                            ).format(
                                    p_search_term=sql.Placeholder(name='search_term'))
                        )

            table_name = "stations"
            result = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        WITH closest_points AS (
                            SELECT * FROM {i_table_name} WHERE {c_where_clause_query})
                        SELECT id, osm_id, ST_X(geom) as lon, ST_Y(geom) as lat, tags,
                                outer_building_id, number_of_entrances, number_of_lines
                        FROM closest_points {c_order_by_and_limit_query}
                        """
                        ).format(
                                i_table_name=sql.Identifier(table_name),
                                c_where_clause_query=sql.SQL(" AND ").join(where_clause_query_list),
                                c_order_by_and_limit_query=order_by_and_limit_query),
                    where_clause_param_dict)
            t2 = time.time()

            for row in result:
                station_id = int(row['id'])
                osm_id = int(row['osm_id'])
                outer_building_id = int(row['outer_building_id'])
                station_tags = self.parse_hstore_column(row['tags'])
                if "name" not in station_tags:
                    # a station without a name is not very usefull
                    continue

                if station_tags.get("public_transport") != "stop_position":
                    # if the station is not tagged as stop position, check if there is another one
                    # with a stop position nearby
                    station_boundary_box_query, station_boundary_box_query_params = \
                            self.get_boundary_box_query_and_params(row['lat'], row['lon'], 50)
                    station_exists_result = self.selected_db.fetch_one(
                            sql.SQL(
                                """
                                SELECT exists(
                                    SELECT 1
                                    FROM {i_table_name}
                                    WHERE {c_station_boundary_box_query}
                                        and tags->'public_transport' = 'stop_position')
                                as exists
                                """
                                ).format(
                                        i_table_name=sql.Identifier(table_name),
                                        c_station_boundary_box_query=station_boundary_box_query),
                            station_boundary_box_query_params)
                    if station_exists_result.get("exists"):
                        # the station already is represented by another one with
                        # a stop position, so skip this one
                        logging.debug("station with id {} ({}) already exists with a stop position, skip"
                                .format(station_id, station_tags.get("name")))
                        continue

                station = self.create_station(station_id, osm_id, row['lat'], row['lon'], station_tags, outer_building_id,
                        row['number_of_entrances'], row['number_of_lines'])
                poi_list = self.insert_into_poi_list(poi_list, station, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    raise WebserverException(
                            ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
            t3 = time.time()
            logging.debug("station gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))


        #####
        # poi
        #####
        poi_tag_list = ["transport_airport_ferry_aerialway", "transport_taxi",
                "food", "entertainment", "tourism", "finance", "shop",
                "health", "education", "public_service", "all_buildings_with_name",
                "surveillance", "bench", "trash", "bridge"]
        if [True for tag in tag_list if tag in poi_tag_list]:
            t1 = time.time()
            where_clause_query_list = [boundary_box_query]

            # tags
            tag_query_list = []
            for t in tag_list:
                if t == "transport_airport_ferry_aerialway":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'aeroway' = ANY(
                                    '{"aerodrome", "gate", "helipad", "terminal"}')
                                """))
                if t == "transport_taxi":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = 'taxi'
                                """))
                if t == "food":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"cafe", "canteen", "bbq", "fast_food", "kitchen",
                                    "food_court", "restaurant", "hookah_lounge", "bar",
                                    "pub", "drinking_water", "biergarten", "ice_cream"}')
                                """))
                if t == "entertainment":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"arts_centre", "Brothel", "Casino", "gambling",
                                    "Cinema", "community_centre", "bar", "pub", "fountain",
                                    "planetarium", "social_centre", "social_club", "nightclub",
                                    "stripclub", "studio", "swingerclub", "theatre",
                                    "youth_centre", "events_venue", "conference_centre",
                                    "love_hotel", "public_bookcase"}')
                                OR tags ? 'leisure'
                                OR tags->'tourism' = 'museum'
                                """))
                if t == "tourism":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"crypt", "place_of_worship", "shelter", "hunting_stand"}')
                                OR tags->'natural' = ANY(
                                    '{"glacier", "hot_spring", "spring", "volcano",
                                    "peak", "cave_entrance", "rock", "stone"}')
                                OR tags->'man_made' = ANY(
                                    '{"adit", "beacon", "communications_tower", "crane",
                                    "cross", "flagpole", "gasometer", "lighthouse",
                                    "mineshaft", "nesting_site", "obelisk", "observatory",
                                    "stupa", "telescope", "tower", "watermill",
                                    "water_tap", "water_well", "windmill"}')
                                or (tags ? 'natural' and tags ? 'name')
                                OR tags ? 'tourism'
                                OR tags ? 'historic'
                                """))
                if t == "finance":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"atm", "bank", "bureau_de_change"}')
                                """))
                if t == "shop":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"bicycle_rental", "boat_rental", "boat_sharing",
                                    "car_rental", "car_sharing", "fuel", "marketplace",
                                    "shop", "shopping", "pharmacy", "Supermarket",
                                    "post_office", "vending_machine", "veterinary"}')
                                OR tags ? 'craft'
                                OR tags ? 'office'
                                OR (tags ? 'shop' and tags->'shop' != 'vacant')
                                """))
                if t == "health":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"pharmacy", "doctors", "dentist", "hospital", "health_centre",
                                    "baby_hatch", "clinic", "nursing_home", "social_facility",
                                    "retirement_home", "sauna", "shower", "toilets", "veterinary"}')
                                OR tags ? 'healthcare'
                                """))
                if t == "education":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"school", "college", "university", "library",
                                    "kindergarten", "Dormitory", "auditorium", "childcare",
                                    "preschool", "language_school", "music_school"}')
                                """))
                if t == "public_service":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"townhall", "public_building", "embassy", "courthouse",
                                    "police", "prison", "fire_station", "register_office",
                                    "shelter", "grave_yard", "crematorium", "village_hall",
                                    "post_box", "post_office", "ranger_station",
                                    "funeral_hall", "waste_transfer_station"}')
                                """))
                if t == "all_buildings_with_name":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                (tags ? 'building' AND tags ? 'name')
                                """))
                if t == "surveillance":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'man_made' = 'surveillance'
                                """))
                if t == "bench":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"bench", "lounger"}')
                                """))
                if t == "trash":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                tags->'amenity' = ANY(
                                    '{"recycling", "waste_basket", "waste_disposal",
                                    "sanitary_dump_station", "dog_toilet", "waste_transfer_station"}')
                                """))
                if t == "bridge":
                    tag_query_list.append(
                            sql.SQL(
                                """
                                   (tags ? 'bridge' AND tags ? 'name')
                                OR (tags->'man_made' = 'bridge' AND tags ? 'name')
                                """))
            # add to where clause
            where_clause_query_list.append(
                    sql.SQL("({})").format(sql.SQL(" OR ").join(tag_query_list)))

            # search
            if search:
                where_clause_query_list.append(
                        sql.SQL(
                            """
                            (  LOWER(tags->'name') LIKE {p_search_term}
                            OR LOWER(tags->'amenity') LIKE {p_search_term}
                            OR LOWER(tags->'cuisine') LIKE {p_search_term}
                            OR LOWER(tags->'addr:street') LIKE {p_search_term}
                            OR LOWER(tags->'street') LIKE {p_search_term})
                            """
                            ).format(
                                    p_search_term=sql.Placeholder(name='search_term'))
                        )

            table_name = "poi"
            result = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        WITH closest_points AS (
                            SELECT * FROM {i_table_name} WHERE {c_where_clause_query})
                        SELECT id, osm_id, ST_X(geom) as lon, ST_Y(geom) as lat, tags,
                                outer_building_id, number_of_entrances
                        FROM closest_points {c_order_by_and_limit_query}
                        """
                        ).format(
                                i_table_name=sql.Identifier(table_name),
                                c_where_clause_query=sql.SQL(" AND ").join(where_clause_query_list),
                                c_order_by_and_limit_query=order_by_and_limit_query),
                    where_clause_param_dict)
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
                    raise WebserverException(
                            ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
            t3 = time.time()
            logging.debug("poi gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))


        ###########
        # entrances
        ###########
        if "entrance" in tag_list:
            t1 = time.time()
            where_clause_query_list = [boundary_box_query]

            # search
            if search:
                where_clause_query_list.append(
                        sql.SQL(
                            """
                            LOWER(label) LIKE {p_search_term}
                            """
                            ).format(
                                    p_search_term=sql.Placeholder(name='search_term'))
                        )

            table_name = "entrances"
            result = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        WITH closest_points AS (
                            SELECT * FROM {i_table_name} WHERE {c_where_clause_query})
                        SELECT entrance_id, ST_X(geom) as lon, ST_Y(geom) as lat, label, tags
                        FROM closest_points {c_order_by_and_limit_query}
                        """
                        ).format(
                                i_table_name=sql.Identifier(table_name),
                                c_where_clause_query=sql.SQL(" AND ").join(where_clause_query_list),
                                c_order_by_and_limit_query=order_by_and_limit_query),
                    where_clause_param_dict)
            t2 = time.time()

            for row in result:
                entrance = self.create_entrance(int(row['entrance_id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['label'])
                poi_list = self.insert_into_poi_list(poi_list, entrance, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    raise WebserverException(
                            ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
            t3 = time.time()
            logging.debug("entrances gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))


        ######################
        # pedestrian crossings
        ######################
        if "pedestrian_crossings" in tag_list:
            t1 = time.time()
            where_clause_query_list = [boundary_box_query]

            # search
            if search:
                where_clause_query_list.append(
                        sql.SQL(
                            """
                            LOWER(crossing_street_name) LIKE {p_search_term}
                            """
                            ).format(
                                    p_search_term=sql.Placeholder(name='search_term'))
                        )

            table_name = "pedestrian_crossings"
            result = self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        WITH closest_points AS (
                            SELECT * FROM {i_table_name} WHERE {c_where_clause_query})
                        SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, tags, crossing_street_name
                        FROM closest_points {c_order_by_and_limit_query}
                        """
                        ).format(
                                i_table_name=sql.Identifier(table_name),
                                c_where_clause_query=sql.SQL(" AND ").join(where_clause_query_list),
                                c_order_by_and_limit_query=order_by_and_limit_query),
                    where_clause_param_dict)
            t2 = time.time()

            for row in result:
                signal = self.create_pedestrian_crossing(int(row['id']), row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['crossing_street_name'])
                poi_list = self.insert_into_poi_list(poi_list, signal, lat, lon)
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    raise WebserverException(
                            ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
            t3 = time.time()
            logging.debug("pedestrian crossings gesamt = %.2f, dbquery = %.2f, parsing = %.2f" % ((t3-t1), (t2-t1), (t3-t2)))


        # filter out entries above given radius
        thrown_away = 0
        filtered_poi_list = []
        for entry in poi_list:
            if entry['distance'] < radius and len(filtered_poi_list) < number_of_results:
                filtered_poi_list.append(entry)
            else:
                thrown_away += 1
        logging.debug("taken/thrown: {} / {}".format(len(filtered_poi_list), thrown_away))
        # log
        te = time.time()
        logging.debug("gesamtzeit: %.2f;   anzahl entries = %d" % ((te-ts), len(poi_list)))

        # add to access statistics and return
        statistics.add_to_access_statistics(self.selected_db, self.session_id)
        return filtered_poi_list


    def next_intersections_for_way(self, node_id, way_id, next_node_id):
        # check params
        if not node_id:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "No node_id")
        elif not isinstance(node_id, int) or node_id < 0:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "Invalid node_id")
        if not way_id:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "No way_id")
        elif not isinstance(way_id, int) or way_id < 0:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "Invalid way_id")
        if not next_node_id:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "No next_node_id")
        elif not isinstance(next_node_id, int) or next_node_id < 0:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "Invalid next_node_id")

        # get current way id and tags
        try:
            way_id = way_id
            way_tags = self.parse_hstore_column(
                    self.selected_db.fetch_one(
                        sql.SQL(
                            """
                            SELECT tags from ways where id = {p_way_id}
                            """
                            ).format(
                                    p_way_id=sql.Placeholder(name='way_id')),
                        {"way_id":way_id})
                    ['tags'])
        except DBControl.DatabaseResultEmptyError as e:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "way id not found")

        # get initial movement direction
        try:
            sequence_id_query = sql.SQL(
                    """
                    SELECT sequence_id FROM way_nodes
                        WHERE way_id = {p_way_id} AND node_id = {p_node_id}
                    """
                    ).format(
                            p_way_id=sql.Placeholder(name='way_id'),
                            p_node_id=sql.Placeholder(name='node_id'))
            node_id_seq_nr = self.selected_db.fetch_one(
                    sequence_id_query,
                    {"way_id":way_id, "node_id": node_id})['sequence_id']
            next_node_id_seq_nr = self.selected_db.fetch_one(
                    sequence_id_query,
                    {"way_id":way_id, "node_id": next_node_id})['sequence_id']
        except DBControl.DatabaseResultEmptyError as e:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "node id not found")
        else:
            if node_id_seq_nr < next_node_id_seq_nr:
                is_ascending = True
            else:
                is_ascending = False

        # create node list and add start intersection
        next_node_list = []
        first_node = self.create_intersection_by_id(node_id)
        if not first_node:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "node id not found")
        next_node_list.append(first_node)

        # collect next node id list
        next_node_id_list = []
        index = 0
        while True:
            index += 1
            if is_ascending:
                next_node_id_list_query = sql.SQL(
                        """
                        SELECT node_id FROM way_nodes
                            WHERE way_id = {p_way_id} AND sequence_id > {p_sequence_id}
                            ORDER BY sequence_id ASC
                        """
                        ).format(
                            p_way_id=sql.Placeholder(name='way_id'),
                                    p_sequence_id=sql.Placeholder(name='sequence_id'))
            else:
                next_node_id_list_query = sql.SQL(
                        """
                        SELECT node_id FROM way_nodes
                            WHERE way_id = {p_way_id} AND sequence_id < {p_sequence_id}
                            ORDER BY sequence_id DESC
                        """
                        ).format(
                                p_way_id=sql.Placeholder(name='way_id'),
                                p_sequence_id=sql.Placeholder(name='sequence_id'))
            next_node_id_list += self.selected_db.fetch_all(
                    next_node_id_list_query,
                    {"way_id":way_id, "sequence_id":node_id_seq_nr})

            # find start of the next potential way
            node_id = next_node_id_list[-1]['node_id']
            potential_next_way_list = []
            for potential_next_way in self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        SELECT wn.sequence_id AS sequence_id, w.id AS way_id, w.tags AS way_tags
                        FROM way_nodes wn JOIN ways w ON wn.way_id = w.id
                        WHERE wn.node_id = {p_node_id} AND wn.way_id != {p_way_id}
                        """
                        ).format(
                                p_node_id=sql.Placeholder(name='node_id'),
                                p_way_id=sql.Placeholder(name='way_id')),
                    {"node_id":node_id, "way_id":way_id}):
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
                    is_ascending = True
                else:
                    is_ascending = False
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
            result = self.selected_db.fetch_one(
                    sql.SQL(
                        """
                        SELECT ST_X(geom) as x, ST_Y(geom) as y, tags
                            FROM nodes
                            WHERE id = {p_osm_node_id}
                        """
                        ).format(
                                p_osm_node_id=sql.Placeholder(name='osm_node_id')),
                    {"osm_node_id":osm_node_id})
        except DBControl.DatabaseError as e:
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
        point['sub_type'] = ""
        if "name" in tags:
            point['name'] = tags['name']
        else:
            point['name'] = self.translator.translate("poi", "way_point")
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
        # description, alternative names and note
        if "description" in tags:
            point['description'] = tags['description']
        if "alt_name" in tags:
            point['alt_name'] = tags['alt_name']
        if "old_name" in tags:
            point['old_name'] = tags['old_name']
        if "note" in tags:
            point['note'] = tags['note']
        return point

    def create_way_segment_by_id(self, osm_way_id, walking_reverse=False):
        try:
            result = self.selected_db.fetch_one(
                    sql.SQL(
                        """
                        SELECT tags
                            FROM ways
                            WHERE id = {p_osm_way_id}
                        """
                        ).format(
                                p_osm_way_id=sql.Placeholder(name='osm_way_id')),
                    {"osm_way_id":osm_way_id})
        except DBControl.DatabaseError as e:
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
        segment['sub_type'] = ""
        if "highway" in tags:
            segment['sub_type'] = self.translator.translate("highway", tags['highway'])
            # special subtype for sidewalks and pedestrian crossings
            if tags['highway'] in ["footway", "path"]:
                if tags.get("footway") == "sidewalk":
                    segment['sub_type'] = self.translator.translate("highway", "footway_sidewalk")
                elif tags.get("footway") == "crossing":
                    segment['sub_type'] = self.translator.translate("highway", "footway_crossing")
                # beware bicyclists
                if tags['highway'] == "footway" \
                        or "footway" in tags:
                    if tags.get("bicycle") in ["yes", "designated", "permissive"]:
                        segment['beware_bicyclists'] = 1
                    else:
                        segment['beware_bicyclists'] = 0
            # additional information
            if tags['highway'] in ["footway", "path", "track"]:
                if "surface" in tags:
                    segment['sub_type'] += ", %s" % self.translator.translate("surface", tags['surface'])
                elif "tracktype" in tags:
                    segment['sub_type'] += ", %s" % tags['tracktype']
            if "railway" in tags and tags['railway'] == "tram":
                segment['tram'] = 1
            else:
                segment['tram'] = 0
        elif "railway" in tags:
            segment['sub_type'] = self.translator.translate("railway", tags['railway'])

        # name
        if "name" in tags:
            segment['name'] = tags['name']
        elif segment['sub_type'] != "":
            segment['name'] = segment['sub_type']
        else:
            segment['name'] = self.translator.translate("poi", "way_segment")
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
        try:
            result = self.selected_db.fetch_one(
                    sql.SQL(
                        """
                        SELECT ST_X(geom) as x, ST_Y(geom) as y, name, tags,
                                number_of_streets, number_of_streets_with_name, number_of_traffic_signals
                            FROM {i_intersection_table_name}
                            WHERE id = {p_osm_id}
                        """
                        ).format(
                                i_intersection_table_name=sql.Identifier(Config().database.get("intersection_table")),
                                p_osm_id=sql.Placeholder(name='osm_id')),
                    {"osm_id":osm_id})
        except DBControl.DatabaseError as e:
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
        intersection['sub_type'] = ""
        if "highway" in tags and tags['highway'] == "mini_roundabout":
            intersection['sub_type'] = self.translator.translate("highway", "roundabout")
        elif "highway" in tags and tags['highway'] == "traffic_signals":
            intersection['sub_type'] = self.translator.translate("highway", "traffic_signals")
        elif "railway" in tags and tags['railway'] == "crossing":
            intersection['sub_type'] = self.translator.translate("railway", "crossing")

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
        for street in self.selected_db.fetch_all(
                sql.SQL(
                    """
                    SELECT way_id, node_id, direction, way_tags, node_tags,
                            ST_X(geom) as lon, ST_Y(geom) as lat
                        FROM {i_intersection_data_table_name}
                        WHERE id = {p_osm_id}
                    """
                    ).format(
                            i_intersection_data_table_name=sql.Identifier(Config().database.get("intersection_data_table")),
                            p_osm_id=sql.Placeholder(name='osm_id')),
                {"osm_id":osm_id}):
            sub_segment = self.create_way_segment(
                    street['way_id'],
                    self.parse_hstore_column(street['way_tags']),
                    street['direction'] == "B")
            sub_segment['intersection_node_id'] = osm_id
            sub_segment['next_node_id'] = street['node_id']
            sub_segment['type'] = "footway_intersection"
            sub_segment['intersection_name'] = intersection['name']
            sub_segment['bearing'] = geometry.bearing_between_two_points(
                    intersection['lat'], intersection['lon'], street['lat'], street['lon'])
            intersection['way_list'].append(sub_segment)

        # crossings
        intersection['pedestrian_crossing_list'] = []
        if number_of_traffic_signals > 0:
            for row in self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        SELECT id, ST_X(geom) as lon, ST_Y(geom) as lat, crossing_street_name, tags
                            FROM pedestrian_crossings
                            WHERE intersection_id = {p_osm_id}
                        """
                        ).format(
                                p_osm_id=sql.Placeholder(name='osm_id')),
                    {"osm_id":osm_id}):
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
        # type and subtype
        entrance['type'] = "entrance"
        entrance['sub_type'] = self.translator.translate("entrance", entrance_label)
        # parse address
        address_data = self.extract_address(tags)
        if address_data:
            entrance.update(address_data)
        # name
        if "name" in tags:
            entrance['name'] = tags['name']
        elif entrance.get("display_name"):
            entrance['name'] = entrance['display_name']
        else:
            entrance['name'] = entrance['sub_type']
        # add label separately
        entrance['label'] = entrance_label
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
        elif "healthcare" in tags:
            if "healthcare:speciality" in tags \
                    and tags['healthcare:speciality'].lower() != "general":
                poi['sub_type'] = "{} ({})".format(
                        self.translator.translate("healthcare", tags['healthcare']),
                        self.translator.translate("healthcare", tags['healthcare:speciality']))
            else:
                poi['sub_type'] = self.translator.translate("healthcare", tags['healthcare'])
        elif "craft" in tags:
            poi['sub_type'] = self.translator.translate("craft", tags['craft'])
        elif "office" in tags:
            poi['sub_type'] = self.translator.translate("office", tags['office'])
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
                result = self.selected_db.fetch_one(
                        sql.SQL(
                            """
                            SELECT ST_X(geom) as x, ST_Y(geom) as y, tags
                                FROM outer_buildings
                                WHERE id = {p_outer_building_id}
                            """
                            ).format(
                                    p_outer_building_id=sql.Placeholder(name='outer_building_id')),
                        {"outer_building_id":outer_building_id})
            except DBControl.DatabaseError as e:
                poi['is_inside'] = {}
            else:
                lat = result['y']
                lon = result['x']
                tags = self.parse_hstore_column(result['tags'])
                poi['is_inside'] = self.create_poi(0, 0, lat, lon, tags, 0, 0)

        # entrances
        poi['entrance_list'] = []
        if number_of_entrances > 0:
            for row in self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        SELECT entrance_id, ST_X(geom) as lon, ST_Y(geom) as lat, label, tags
                            FROM entrances
                            WHERE poi_id = {p_poi_id}
                            ORDER BY class
                        """
                        ).format(
                                p_poi_id=sql.Placeholder(name='poi_id')),
                    {"poi_id":poi_id}):
                entrance = self.create_entrance(row['entrance_id'], row['lat'], row['lon'],
                        self.parse_hstore_column(row['tags']), row['label'])
                poi['entrance_list'].append(entrance)

        # other attributes
        if "ele" in tags:
            poi['ele'] = tags['ele']
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
        station['sub_type'] = ""
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
            station['sub_type'] = ", ".join(
                    [ self.translator.translate("public_transport", vehicle) \
                            for vehicle in station['vehicles'] ])

        # transport lines
        station['lines'] = []
        if number_of_lines > 0:
            for row in self.selected_db.fetch_all(
                    sql.SQL(
                        """
                        SELECT DISTINCT line, direction, type
                            FROM transport_lines
                            WHERE poi_id = {p_station_id}
                            ORDER BY type
                        """
                        ).format(
                                p_station_id=sql.Placeholder(name='station_id')),
                    {"station_id":station_id}):
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

    def get_boundary_box_query_and_params(self, lat, lon, radius):
        # check params
        try:
            if lat < -180 or lat > 180:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "Latitude out of range")
        except TypeError as e:
            if lat:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "Invalid latitude")
            else:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "No latitude")
        # longitude
        try:
            if lon < -180 or lon > 180:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "longitude out of range")
        except TypeError as e:
            if lon:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "Invalid longitude")
            else:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "No longitude")
        # radius
        try:
            if radius <= 0:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "radius <= 0")
        except TypeError as e:
            if radius:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "Invalid radius")
            else:
                raise WebserverException(
                        ReturnCode.BAD_REQUEST, "No radius")

        # boundary box sql query
        boundary_box_query = sql.SQL(
                """
                geom && ST_MakeEnvelope(
                        {p_boundaries_left}, {p_boundaries_bottom}, {p_boundaries_right}, {p_boundaries_top})
                """
                ).format(
                        p_boundaries_left=sql.Placeholder(name='boundaries_left'),
                        p_boundaries_bottom=sql.Placeholder(name='boundaries_bottom'),
                        p_boundaries_right=sql.Placeholder(name='boundaries_right'),
                        p_boundaries_top=sql.Placeholder(name='boundaries_top'))
        # params
        boundaries = geometry.get_boundary_box(lat, lon, radius)
        boundary_box_query_params = {
                'boundaries_left' : boundaries['left'],
                'boundaries_bottom' : boundaries['bottom'],
                'boundaries_right' : boundaries['right'],
                'boundaries_top' : boundaries['top'] }

        # lat/lon inside selected map?
        try:
            self.selected_db.fetch_one(
                    sql.SQL(
                        """
                        SELECT * FROM {i_table_name} WHERE {c_boundary_box_query} LIMIT 1
                        """
                        ).format(
                            i_table_name=sql.Identifier("nodes"),
                            c_boundary_box_query=boundary_box_query),
                        boundary_box_query_params)
        except DBControl.DatabaseResultEmptyError as e:
            raise WebserverException(ReturnCode.WRONG_MAP_SELECTED)

        return (boundary_box_query, boundary_box_query_params)


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
            if city:
                addr_list.append(city)
            addr_dict['display_name'] = ', '.join(addr_list)
        return addr_dict


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



