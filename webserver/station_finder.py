#!/usr/bin/python
# -*- coding: utf-8 -*-

from py4j.java_gateway import JavaGateway, GatewayClient

from . import geometry
from .config import Config


class StationFinder:

    def __init__(self, public_transport_provider):
        self.public_transport_provider = public_transport_provider

    def select_station_by_vehicle_type(self, station_list, lat, lon, vehicles):
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
                            vcode = departure.line.product.code
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

