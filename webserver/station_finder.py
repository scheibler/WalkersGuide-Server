#!/usr/bin/python
# -*- coding: utf-8 -*-

import geometry, time, re
from py4j.java_gateway import JavaGateway, GatewayClient
from config import Config
from poi import POI 
from translator import Translator

class StationFinder:

    def __init__(self, db, translator_object, public_transport_provider,):
        self.translator = translator_object
        self.poi = POI(db, "00000", translator_object, True)
        self.stations = []
        self.public_transport_provider, = public_transport_provider,

    def get_station(self, db_station, line, direction):
        new_station = { "line": line, "direction": direction, "data":{},
                "lat": geometry.convert_coordinate_to_float(db_station.lat),
                "lon": geometry.convert_coordinate_to_float(db_station.lon) }
        for station in self.stations:
            if station['lat'] == new_station['lat'] and station['lon'] == new_station['lon'] and station['line'] == new_station['line'] and station['direction'] == new_station['direction']:
                return station['data']
        data = self.find_station_in_osm_database(new_station['lat'], new_station['lon'], new_station['line'], new_station['direction'])
        data['station_id'] = db_station.id
        if data.has_key("name") == False:
            data['name'] = db_station.name.encode("utf-8")
        new_station['data'] = data
        self.stations.append(new_station)
        return new_station['data']

    def find_station_in_osm_database(self, lat, lon, line, direction):
        if type(direction) == type(u""):
            direction = direction.encode("utf-8")
        new_station = {"lat":lat, "lon":lon, "node_id":-1, "exact_position":False, "type":"station"}
        t1 = time.time()
        if line.startswith("T") == True or line.startswith("B") == True:
            # transport class 1
            new_station['transportation_class'] = 1
            if line.startswith("T") == True:
                new_station['sub_type'] = self.translator.translate("public_transport", "tram")
            if line.startswith("B") == True:
                new_station['sub_type'] = self.translator.translate("public_transport", "bus")
            t2 = time.time()
            radius = 125
            station_list = []
            while station_list.__len__() == 0:
                station_list = self.poi.get_poi(lat, lon, radius, ["transportation_class_1"])
                radius *= 2
            t3 = time.time()
            reference_station_name = station_list[0]['name']
            for station in station_list:
                if station['name'] != reference_station_name:
                    continue
                for l in station['lines']:
                    if re.sub("\D", "", l['nr']) != re.sub("\D", "", line):
                        continue
                    if l['to'] == None or l['to'] == "":
                        continue
                    # check if the direction value from the osm database is contained by the db direction value
                    osm_direction_in_db_direction = True
                    for s in l['to'].split(" "):
                        if s.replace(",", "").strip().lower() not in direction.strip().lower():
                            osm_direction_in_db_direction = False
                    # now check the other way around
                    db_direction_in_osm_direction = True
                    for s in direction.split(" "):
                        if s.replace(",", "").strip().lower() not in l['to'].strip().lower():
                            db_direction_in_osm_direction = False
                    if osm_direction_in_db_direction or db_direction_in_osm_direction:
                        station['exact_position'] = True
                        station['transportation_class'] = 1
                        return station 

        else:
            # transport class 2
            new_station['transportation_class'] = 2
            if line.startswith("U") == True:
                new_station['sub_type'] = self.translator.translate("public_transport", "subway")
            elif line.startswith("S") == True:
                new_station['sub_type'] = self.translator.translate("public_transport", "light_rail")
            elif line.startswith("F") == True:
                new_station['sub_type'] = self.translator.translate("public_transport", "ferry")
            else:
                new_station['sub_type'] = self.translator.translate("public_transport", "station")
            radius = 125
            station_list = []
            while station_list.__len__() == 0:
                station_list = self.poi.get_poi(lat, lon, radius, ["transportation_class_2"])
                radius *= 2
            station = station_list[0]
            station['transportation_class'] = 2
            station['exact_position'] = False
            if station.has_key("entrance_list") == True:
                if station['entrance_list'].__len__() > 0:
                    station['exact_position'] = True
                    station['lat'] = station['entrance_list'][0]['lat']
                    station['lon'] = station['entrance_list'][0]['lon']
            return station

        # if we didn't find the exact station
        return new_station 

    def choose_station_by_vehicle_type(self, station_list, lat, lon, vehicles):
        print(station_list)
        gateway = JavaGateway(GatewayClient(port=Config().java.get("gateway_port")), auto_field=True)
        for station in station_list:
            distance_to_station = geometry.distance_between_two_points(lat, lon,
                    geometry.convert_coordinate_to_float(station.lat),
                    geometry.convert_coordinate_to_float(station.lon))
            if distance_to_station < 100:
                departures_result = gateway.entry_point.getDepartures(
                        self.public_transport_provider, station.id)
                for station_departure in departures_result.stationDepartures:
                    for departure in station_departure.departures:
                        try:
                            vcode = departure.line.product.code.encode("utf-8")
                            if "bus" in vehicles and vcode == "B":
                                return station
                            if "tram" in vehicles and vcode == "T":
                                return station
                            if "ferry" in vehicles and vcode == "F":
                                return station
                            if "monorail" in vehicles and vcode == "S":
                                return station
                            if "lightrail" in vehicles and vcode == "S":
                                return station
                            if "train" in vehicles and vcode in ["I", "R", "S"]:
                                return station
                            if "subway" in vehicles and vcode == "U":
                                return station
                        except Exception as e:
                            pass
        return station_list[0]

