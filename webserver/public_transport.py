#!/usr/bin/python
# -*- coding: utf-8 -*-

from py4j.java_gateway import JavaGateway, GatewayClient

from . import constants, geometry
from .config import Config
from .constants import ReturnCode
from .helper import WebserverException, send_email


class PublicTransport:

    @classmethod
    def get_gateway(cls):
        return JavaGateway(
                GatewayClient(port=Config().java.get("gateway_port")), auto_field=True)

    @classmethod
    def get_supported_public_transport_provider_list(cls):
        supported_public_transport_provider_list = []
        if Config().java.get("gateway_port") > 0:
            for provider_id in cls.get_gateway().entry_point.getSupportedNetworkProviderIdList():
                supported_public_transport_provider_list.append(provider_id)
        return supported_public_transport_provider_list


    def __init__(self, session_id):
        self.session_id = session_id


    def get_departures(self, lat, lon, public_transport_provider_id, vehicle_list):
        gateway = self.get_gateway()
        main_point = gateway.entry_point

        # check variables
        # latitude
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
        # public transport provider
        if not public_transport_provider_id:
            raise WebserverException(
                    ReturnCode.PUBLIC_TRANSPORT_PROVIDER_LOADING_FAILED,
                    "No public_transport_provider_id")
        elif not isinstance(public_transport_provider_id, str):
            raise WebserverException(
                    ReturnCode.PUBLIC_TRANSPORT_PROVIDER_LOADING_FAILED,
                    "Invalid public_transport_provider_id")
        elif public_transport_provider_id not in self.get_supported_public_transport_provider_list():
            raise WebserverException(
                    ReturnCode.PUBLIC_TRANSPORT_PROVIDER_LOADING_FAILED,
                    "public_transport_provider_id not supported")
        else:
            network_provider = main_point.getNetworkProvider(public_transport_provider_id)
        # vehicle list
        if not vehicle_list:
            vehicle_list = []
        elif not isinstance(vehicle_list, list) \
                 or [False for vehicle in vehicle_list if not isinstance(vehicle, str)]:
            raise WebserverException(
                    ReturnCode.BAD_REQUEST, "Invalid vehicle_list")

        # find nearby station for lat,lon
        nearby_stations_result = main_point.getNearbyStations(network_provider, lat, lon)
        if Config().has_session_id_to_remove(self.session_id):
            raise WebserverException(
                    ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
        elif not nearby_stations_result \
                or nearby_stations_result.status.toString() == "SERVICE_DOWN":
            raise WebserverException(
                    ReturnCode.BAD_GATEWAY, "public transport provider is down")
        elif not nearby_stations_result.locations \
                or nearby_stations_result.status.toString() == "INVALID_ID":
            raise WebserverException(
                    ReturnCode.PUBLIC_TRANSPORT_STATION_NOT_FOUND, "Station not found")
        else:
            min_distance_to_station = 1000000
            for station in nearby_stations_result.locations:
                distance_to_station = geometry.distance_between_two_points(
                        lat, lon, station.getLatAsDouble(), station.getLonAsDouble())
                if distance_to_station < min_distance_to_station:
                    closest_station = station

        # get departures for station
        departures_result = main_point.getDepartures(network_provider, closest_station.id)
        if Config().has_session_id_to_remove(self.session_id):
            raise WebserverException(
                    ReturnCode.CANCELLED_BY_CLIENT, "Cancelled by client")
        elif not departures_result:
            raise WebserverException(
                    ReturnCode.BAD_GATEWAY, "public transport provider is down")
        else:
            departure_list = []
            for station_departure in departures_result.stationDepartures:
                for departure in station_departure.departures:
                    try:
                        dep_entry = {}
                        dep_entry['nr'] = "{}{}".format(departure.line.product.code, departure.line.label)
                        dep_entry['to'] = departure.destination.name
                        dep_entry['time'] = departure.plannedTime.getTime()
                        departure_list.append(dep_entry)
                    except Exception as e:
                        pass

        gateway.close_callback_server()
        return departure_list

