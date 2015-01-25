#!/usr/bin/python
# -*- coding: utf-8 -*-

from db_control import DBControl
from translator import Translator
from poi import POI 
import geometry, time, re

class StationFinder:

    def __init__(self, translator_object):
        self.translator = translator_object
        self.poi = POI("00000", translator_object, True)
        self.stations = []

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
        new_station = {"lat":lat, "lon":lon, "node_id":-1, "accuracy":False, "type":"station"}
        t1 = time.time()
        #print line
        #print direction
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
                #print "radius = %d" % radius
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
                    station['accuracy'] = True
                    for s in l['to'].split(" "):
                        if s.replace(",", "").strip().lower() not in direction.strip().lower():
                            station['accuracy'] = False
                            break
                    if station['accuracy'] == True:
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
            station['accuracy'] = False
            if station.has_key("entrance_list") == True:
                if station['entrance_list'].__len__() > 0:
                    station['accuracy'] = True
                    station['lat'] = station['entrance_list'][0]['lat']
                    station['lon'] = station['entrance_list'][0]['lon']
            return station

        # if we didn't find the exact station
        return new_station 

