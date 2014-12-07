#!/usr/bin/python
# -*- coding: utf-8 -*-

from station_finder import StationFinder
from py4j.java_gateway import JavaGateway, GatewayClient
from route_logger import RouteLogger
from translator import Translator
from config import Config
import geometry
import time, json, operator

class RouteTransportCreator:

    def __init__(self, session_id, route_logger_object, translator_object):
        self.session_id = session_id
        self.route_logger = route_logger_object
        self.translator = translator_object
        self.s_finder = StationFinder(translator_object)
        self.gateway = JavaGateway(GatewayClient(port=Config().get_param("gateway_port")), auto_field=True)
        self.main_point = self.gateway.entry_point
        self.costs = {
                'change_1': 2,
                'change_2': 4,
                'change_3': 6,
                'change_4': 8,
                'change_not_enough_time': 100,
                'walk_dist_meters': 100,
                'min_departure': 5,
                'min_trip_length': 10 }
        self.short_change_interval = 5
        self.long_change_interval = 9

    def find_transport_route( self, start_point, dest_point, number_of_possible_routes):
        print "transport route creator"
        # find start and destination stations
        t1 = time.time()
        start_stations = [ self.main_point.createAddressObject(
                geometry.convert_coordinate_to_int(start_point['lat']),
                geometry.convert_coordinate_to_int(start_point['lon']) ) ]
        for station in self.main_point.getNearestStations(
                geometry.convert_coordinate_to_int(start_point['lat']),
                geometry.convert_coordinate_to_int(start_point['lon'])).stations:
            start_stations.append(station)
            if start_stations.__len__() >= 5:
                break
        dest_stations = [ self.main_point.createAddressObject(
                geometry.convert_coordinate_to_int(dest_point['lat']),
                geometry.convert_coordinate_to_int(dest_point['lon']) ) ]
        for station in self.main_point.getNearestStations(
                geometry.convert_coordinate_to_int(dest_point['lat']),
                geometry.convert_coordinate_to_int(dest_point['lon'])).stations:
            dest_stations.append(station)
            if dest_stations.__len__() >= 5:
                break
        # check for cancel command
        if Config().has_session_id_to_remove(self.session_id):
            Config().confirm_removement_of_session_id(self.session_id)
            return

        # calculate best connections
        transport_route_list = []
        location_type = self.gateway.jvm.de.schildbach.pte.dto.LocationType
        t2 = time.time()
        begin = time.time()
        for start in start_stations:
            for dest in dest_stations:
                log_string = ""
                if start.name == None:
                    log_string += "von %s " % start_point['name']
                else:
                    log_string += "Von haltestelle %s " % start.name.encode("utf-8")
                if dest.name == None:
                    log_string += "nach %s" % dest_point['name']
                else:
                    log_string += "nach haltestelle %s" % dest.name.encode("utf-8")
                self.route_logger.append_to_log(log_string)

                # set the start delay in minutes
                delay = 15
                distance_from_start_to_departure = geometry.distance_between_two_points( start_point['lat'], start_point['lon'],
                        geometry.convert_coordinate_to_float(start.lat), geometry.convert_coordinate_to_float(start.lon) )
                delay += distance_from_start_to_departure / 50

                # question trips from bahn.de
                response = self.main_point.calculateConnection(start, dest, delay)
                if response == None:
                    continue
                trips = response.trips
                if trips == None:
                    continue
                index = 1
                for trip in trips:
                    if trip.legs.__len__() == 0:
                        continue
                    self.route_logger.append_to_log("Connection %d / 4" % index)
                    cstart = time.time()
                    add_to_list = True
                    transport_route_object = self.create_transport_route_object(start_point, trip.legs, dest_point)
                    for object in transport_route_list:
                        if transport_route_object.cost < 0:
                            add_to_list = False
                            break
                        if object.description == transport_route_object.description:
                            add_to_list = False
                            break
                    if add_to_list == True:
                        transport_route_list.append(transport_route_object)
                    cend = time.time()
                    self.route_logger.append_to_log("== %d cost; Connection parsing time: %.2f\n"
                            % (transport_route_list[-1].cost, (cend-cstart)) )
                    index += 1
                # check for cancel command
                if Config().has_session_id_to_remove(self.session_id):
                    Config().confirm_removement_of_session_id(self.session_id)
                    return

        end = time.time()
        t3 = time.time()
        # print route
        transport_route_list.sort(key = operator.attrgetter('cost'))
        self.route_logger.append_to_log("Winner = %d points, parsing time: %.2f" % (transport_route_list[0].cost, (end-begin)))
        self.route_logger.append_to_log( json.dumps( transport_route_list[0].route, indent=4, encoding="utf-8") )
        t4 = time.time()
        print "transport1: %.2f" % (t2-t1)
        print "transport2: %.2f" % (t3-t2)
        print "transport3: %.2f" % (t4-t3)
        print "transport gesamt: %.2f" % (t4-t1)
        return transport_route_list[0:number_of_possible_routes]

    def create_transport_route_object( self, start_point, legs, dest_point):
        cost = 0
        route = []
        walking_distance = 0
        start = time.time()

        # add the start point
        start_index = 0
        placeholder_segment = {"name":"", "type":"footway", "sub_type":"", "distance":0, "bearing":0}
        if "$Individual" in legs[0].getClass().getName():
            route.append(start_point)
            placeholder_segment['distance'] = geometry.distance_between_two_points( start_point['lat'], start_point['lon'],
                    geometry.convert_coordinate_to_float(legs[0].arrival.lat),
                    geometry.convert_coordinate_to_float(legs[0].arrival.lon) )
            walking_distance += placeholder_segment['distance']
            placeholder_segment['bearing'] = geometry.bearing_between_two_points( start_point['lat'], start_point['lon'],
                    geometry.convert_coordinate_to_float(legs[0].arrival.lat),
                    geometry.convert_coordinate_to_float(legs[0].arrival.lon) )
            placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
            placeholder_segment['sub_type'] = "footway_place_holder"
            route.append(placeholder_segment)
            start_index += 1
        else:
            placeholder_segment['distance'] = geometry.distance_between_two_points( start_point['lat'], start_point['lon'],
                    geometry.convert_coordinate_to_float(legs[0].departure.lat),
                    geometry.convert_coordinate_to_float(legs[0].departure.lon) )
            placeholder_segment['bearing'] = geometry.bearing_between_two_points( start_point['lat'], start_point['lon'],
                    geometry.convert_coordinate_to_float(legs[0].departure.lat),
                    geometry.convert_coordinate_to_float(legs[0].departure.lon) )
            if placeholder_segment['distance'] > 20:
                walking_distance += placeholder_segment['distance']
                placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                placeholder_segment['sub_type'] = "footway_place_holder"
                route.append(start_point)
                route.append(placeholder_segment)

        # check, if the last part of the trip is a walking part
        dest_index = legs.__len__()
        if "$Individual" in legs[-1].getClass().getName():
            if dest_index > 0:
                dest_index -= 1

        for index in range(start_index, dest_index):
            leg = legs[index]
            #if "$Individual" in leg.getClass().getName():
            #    # a walking part between public transport legs
            #    distance = geometry.distance_between_two_points(
            #            geometry.convert_coordinate_to_float(leg.departure.lat),
            #            geometry.convert_coordinate_to_float(leg.departure.lon),
            #            geometry.convert_coordinate_to_float(leg.arrival.lat),
            #            geometry.convert_coordinate_to_float(leg.arrival.lon) )
            #    placeholder_segment['name'] = "%d Meter Fußweg" % distance
            #    placeholder_segment['sub_type'] = "footway_place_holder"
            #    walking_distance += distance
            #    # route.append(placeholder_segment)
            #    self.route_logger.append_to_log("fußweg: %d meter; from %s to %s" % (distance,
            #        leg.departure.name.encode("utf-8"), leg.arrival.name.encode("utf-8")) )

            if "$Public" in leg.getClass().getName():
                # create departure and arrival objects
                line = leg.line.label.encode("utf-8")
                if leg.destination != None:
                    destination_name = leg.destination.name.encode("utf-8")
                else:
                    destination_name = leg.arrival.name.encode("utf-8")
                t1 = time.time()
                departure = self.s_finder.get_station( leg.departure, line, destination_name)
                if leg.departureStop.plannedDeparturePosition != None:
                    departure['platform_number'] = leg.departureStop.plannedDeparturePosition.name
                t2 = time.time()
                arrival = self.s_finder.get_station( leg.arrival, line, destination_name)
                if leg.arrivalStop.plannedArrivalPosition != None:
                    arrival['platform_number'] = leg.arrivalStop.plannedArrivalPosition.name.encode("utf-8")
                t3 = time.time()
                print "departure and arrival time: %.2f" % (t3-t1)
                self.route_logger.append_to_log("line: %s; From %s to %s" % (line, departure['name'], arrival['name']))

                # create transport segment
                transport_segment = { "type":"transport", "line":line, "direction":destination_name }
                # departure and arrival time
                date_format = self.gateway.jvm.java.text.SimpleDateFormat("HH:mm", self.gateway.jvm.java.util.Locale.GERMAN)
                transport_segment['departure_time'] = date_format.format(leg.getDepartureTime())
                transport_segment['departure_time_millis'] = leg.getDepartureTime().getTime()
                transport_segment['arrival_time'] = date_format.format(leg.getArrivalTime())
                transport_segment['arrival_time_millis'] = leg.getArrivalTime().getTime()
                duration = (leg.getArrivalTime().getTime() - leg.getDepartureTime().getTime())/1000
                hours, remainder = divmod(duration, 3600)
                minutes, seconds = divmod(remainder, 60)
                if hours == 0:
                    transport_segment['duration'] = "%d Min" % minutes
                else:
                    transport_segment['duration'] = "%d:%d" % (hours, minutes)
                # intermediate stops
                intermediate_stop_list = leg.intermediateStops
                transport_segment['stops'] = []
                if intermediate_stop_list == None:
                    transport_segment['number_of_stops'] = 0
                else:
                    transport_segment['number_of_stops'] = intermediate_stop_list.__len__()
                    for stop in intermediate_stop_list:
                        transport_segment['stops'].append(stop.location.name)

                # first leg of trip
                is_first_leg = False
                if route.__len__() == 0:
                    is_first_leg = True
                elif route[-1]['type'] == "footway":
                    is_first_leg = True
                if is_first_leg == True:
                    # the last route segment was either a footway part or the route is still empty
                    # get cost for first departure
                    if departure['transportation_class'] == 1:
                        if departure['accuracy'] == True:
                            cost += self.costs['change_1']
                            self.route_logger.append_to_log("%s: enter tc1 +acc (+%d)" % 
                                    (departure['name'], self.costs['change_1']))
                        else:
                            cost += self.costs['change_2']
                            self.route_logger.append_to_log("%s: enter tc1 -acc (+%d)" % 
                                    (departure['name'], self.costs['change_2']))
                    else:
                        if departure['accuracy'] == True:
                            cost += self.costs['change_2']
                            self.route_logger.append_to_log("%s: enter tc2 with entrance (+%d)" % 
                                    (departure['name'], self.costs['change_2']))
                        else:
                            cost += self.costs['change_3']
                            self.route_logger.append_to_log("%s: enter tc2 without entrance (+%d)" % 
                                    (departure['name'], self.costs['change_3']))

                # change for another transportation vehicle
                else:
                    last_transport_segment = route[-2]
                    last_arrival = route[-1]
                    time_for_change = (leg.getDepartureTime().getTime() -
                            last_transport_segment['arrival_time_millis']) / 60000
                    self.route_logger.append_to_log("time for change = %d" % time_for_change)
                    placeholder_segment = {"name":"", "type":"footway", "sub_type":"", "distance":0, "bearing":0}
                    placeholder_segment['distance'] = geometry.distance_between_two_points(
                            last_arrival['lat'], last_arrival['lon'],
                            departure['lat'], departure['lon'])
                    walking_distance += placeholder_segment['distance']
                    placeholder_segment['bearing'] = geometry.bearing_between_two_points(
                            last_arrival['lat'], last_arrival['lon'],
                            departure['lat'], departure['lon'])

                    # tc1-tc1
                    if last_arrival['transportation_class'] == 1 and departure['transportation_class'] == 1:

                        # tc1-tc1: arrival and departure positions known
                        if last_arrival['accuracy'] == True and departure['accuracy'] == True:
                            # same platform, user can wait for next vehicle
                            if last_arrival['node_id'] == departure['node_id']:
                                cost += self.costs['change_1']
                                placeholder_segment['name'] = self.translator.translate("transport_creator", "same_station")
                                placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                                self.route_logger.append_to_log("%s - %s: same platform (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_1']))
                            elif last_arrival['station_id'] == departure['station_id']:
                                # same station but different stop position
                                last_arrival_line = last_arrival['lines'][0]['nr']
                                is_towards = False
                                for line in departure['lines']:
                                    if line['nr'] == last_arrival_line:
                                        is_towards = True
                                        break
                                if is_towards == True:
                                    placeholder_segment['name'] = self.translator.translate("transport_creator", "opposite_station")
                                    placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                                    if time_for_change < self.short_change_interval:
                                        cost += self.costs['change_not_enough_time']
                                        self.route_logger.append_to_log("%s - %s: tc1_acc-tc1_acc: s_id = s_id oppposite platform (+%d)" % 
                                                (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                    else:
                                        cost += self.costs['change_2']
                                        self.route_logger.append_to_log("%s - %s: tc1_acc-tc1_acc: s_id = s_id oppposite platform (+%d)" % 
                                                (last_arrival['name'], departure['name'], self.costs['change_2']))
                                else:
                                    placeholder_segment['name'] = self.translator.translate("transport_creator", "nearby_station")
                                    placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                                    if time_for_change < self.short_change_interval:
                                        cost += self.costs['change_not_enough_time']
                                        self.route_logger.append_to_log("%s - %s: tc1_acc-tc1_acc: s_id = s_id near by platform (+%d)" % 
                                                (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                    else:
                                        cost += self.costs['change_2']
                                        self.route_logger.append_to_log("%s - %s: tc1_acc-tc1_acc: s_id = s_id near by platform (+%d)" % 
                                                (last_arrival['name'], departure['name'], self.costs['change_2']))
                            else:
                                # other station
                                placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                                placeholder_segment['sub_type'] = "footway_place_holder"
                                if time_for_change < self.long_change_interval:
                                    cost += self.costs['change_not_enough_time']
                                    self.route_logger.append_to_log("%s - %s: tc1_acc-tc1_acc: s_id != s_id different platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                else:
                                    cost += self.costs['change_3']
                                    self.route_logger.append_to_log("%s - %s: tc1_acc-tc1_acc: s_id != s_id different platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_3']))

                        # tc1-tc1: only the destination station of the change is known
                        elif departure['accuracy'] == True:
                            if last_arrival['station_id'] == departure['station_id']:
                                placeholder_segment['name'] = self.translator.translate("transport_creator", "nearby_station")
                                placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                                if time_for_change < self.short_change_interval:
                                    cost += self.costs['change_not_enough_time']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_acc: s_id = s_id near by platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                else:
                                    cost += self.costs['change_2']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_acc: s_id = s_id near by platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_2']))
                            else:
                                # other station
                                placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                                placeholder_segment['sub_type'] = "footway_place_holder"
                                if time_for_change < self.long_change_interval:
                                    cost += self.costs['change_not_enough_time']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_acc: s_id != s_id different platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                else:
                                    cost += self.costs['change_3']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_acc: s_id != s_id different platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_3']))

                        # tc1-tc1: no exact station positions known
                        else:
                            if last_arrival['station_id'] == departure['station_id']:
                                placeholder_segment['name'] = self.translator.translate("transport_creator", "nearby_station_no_exact_pos")
                                placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                                if time_for_change < self.short_change_interval:
                                    cost += self.costs['change_not_enough_time']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_noacc: s_id = s_id near by platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                else:
                                    cost += self.costs['change_3']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_noacc: s_id = s_id near by platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_3']))
                            else:
                                # other station
                                placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                                placeholder_segment['sub_type'] = "footway_place_holder"
                                if time_for_change < self.long_change_interval:
                                    cost += self.costs['change_not_enough_time']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_noacc: s_id != s_id different platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                                else:
                                    cost += self.costs['change_4']
                                    self.route_logger.append_to_log("%s - %s: tc1_noacc-tc1_noacc: s_id != s_id different platform (+%d)" % 
                                            (last_arrival['name'], departure['name'], self.costs['change_4']))

                    # tc1-tc2
                    elif last_arrival['transportation_class'] == 1 and departure['transportation_class'] == 2:
                        # station has entrances
                        placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                        placeholder_segment['sub_type'] = "footway_place_holder"
                        if departure['accuracy'] == True:
                            if time_for_change < self.short_change_interval:
                                cost += self.costs['change_not_enough_time']
                                self.route_logger.append_to_log("%s - %s: tc1-tc2+entr (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                            else:
                                cost += self.costs['change_3']
                                self.route_logger.append_to_log("%s - %s: tc1-tc2+entr (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_3']))
                        else:
                            if time_for_change < self.long_change_interval:
                                cost += self.costs['change_not_enough_time']
                                self.route_logger.append_to_log("%s - %s: tc1-tc2 no_entr (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                            else:
                                cost += self.costs['change_4']
                                self.route_logger.append_to_log("%s - %s: tc1-tc2 no_entr (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_4']))

                    # tc2-tc1
                    elif last_arrival['transportation_class'] == 2 and departure['transportation_class'] == 1:
                        # exact position of station known
                        placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                        placeholder_segment['sub_type'] = "footway_place_holder"
                        if departure['accuracy'] == True:
                            if time_for_change < self.short_change_interval:
                                cost += self.costs['change_not_enough_time']
                                self.route_logger.append_to_log("%s - %s: tc2-tc1+exact (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                            else:
                                cost += self.costs['change_2']
                                self.route_logger.append_to_log("%s - %s: tc2-tc1+exact (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_2']))
                        else:
                            if time_for_change < self.long_change_interval:
                                cost += self.costs['change_not_enough_time']
                                self.route_logger.append_to_log("%s - %s: tc2-tc1 not_exact (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                            else:
                                cost += self.costs['change_4']
                                self.route_logger.append_to_log("%s - %s: tc2-tc1 not_exact (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_4']))

                    # tc2-tc2
                    elif last_arrival['transportation_class'] == 2 and departure['transportation_class'] == 2:
                        if last_arrival['station_id'] == departure['station_id']:
                            placeholder_segment['name'] = self.translator.translate("transport_creator", "within_station")
                            placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                            if time_for_change < self.short_change_interval:
                                cost += self.costs['change_not_enough_time']
                                self.route_logger.append_to_log("%s - %s: tc2-tc2: same station id (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                            else:
                                cost += self.costs['change_3']
                                self.route_logger.append_to_log("%s - %s: tc2-tc2: same station id (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_3']))
                        else:
                            placeholder_segment['name'] = self.translator.translate("transport_creator", "different_station")
                            placeholder_segment['sub_type'] = self.translator.translate("highway", "footway")
                            if time_for_change < self.long_change_interval:
                                cost += self.costs['change_not_enough_time']
                                self.route_logger.append_to_log("%s - %s: tc2-tc2: diff station id (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_not_enough_time']))
                            else:
                                cost += self.costs['change_4']
                                self.route_logger.append_to_log("%s - %s: tc2-tc2: diff station id (+%d)" % 
                                        (last_arrival['name'], departure['name'], self.costs['change_4']))

                    # something went wrong with the transportation class
                    else:
                        print "parsing error"
                        # raise route_parsing_exception("blub")

                    # add segment and arrival
                    route.append(placeholder_segment)

                # add departure, transport_segment and arrival
                route.append(departure)
                route.append(transport_segment)
                route.append(arrival)

        # adding the last footway segment
        placeholder_segment = {"name":"", "type":"footway", "sub_type":"", "distance":0, "bearing":0}
        if "$Individual" in legs[-1].getClass().getName():
            placeholder_segment['distance'] = geometry.distance_between_two_points(
                    geometry.convert_coordinate_to_float(legs[-1].departure.lat),
                    geometry.convert_coordinate_to_float(legs[-1].departure.lon),
                    dest_point['lat'], dest_point['lon'] )
            walking_distance += placeholder_segment['distance']
            placeholder_segment['bearing'] = geometry.bearing_between_two_points(
                    geometry.convert_coordinate_to_float(legs[-1].departure.lat),
                    geometry.convert_coordinate_to_float(legs[-1].departure.lon),
                    dest_point['lat'], dest_point['lon'] )
            placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
            placeholder_segment['sub_type'] = "footway_place_holder"
            route.append(placeholder_segment)
            route.append(dest_point)
        else:
            placeholder_segment['distance'] = geometry.distance_between_two_points(
                    geometry.convert_coordinate_to_float(legs[-1].arrival.lat),
                    geometry.convert_coordinate_to_float(legs[-1].arrival.lon),
                    dest_point['lat'], dest_point['lon'] )
            placeholder_segment['bearing'] = geometry.bearing_between_two_points(
                    geometry.convert_coordinate_to_float(legs[-1].arrival.lat),
                    geometry.convert_coordinate_to_float(legs[-1].arrival.lon),
                    dest_point['lat'], dest_point['lon'] )
            if placeholder_segment['distance'] > 20:
                walking_distance += placeholder_segment['distance']
                placeholder_segment['name'] = self.translator.translate("transport_creator", "footway_place_holder")
                placeholder_segment['sub_type'] = "footway_place_holder"
                route.append(placeholder_segment)
                route.append(dest_point)

        end = time.time()
        cost += (walking_distance / self.costs['walk_dist_meters']) + 1
        self.route_logger.append_to_log("Fußweg insgesamt = %d, %d Punkte" % (walking_distance, (walking_distance/self.costs['walk_dist_meters'])+1))

        # time calculation
        departure_time = 0
        arrival_time = 0
        number_of_trips = 0
        transport_vehicles = []
        for part in route:
            if part['type'] == "transport":
                number_of_trips += 1
                transport_vehicles.append(part['line'])
                arrival_time = part['arrival_time_millis']
                if departure_time == 0:
                    departure_time = part['departure_time_millis']
        minutes_till_departure = (departure_time - int(time.time()*1000)) / 60000
        trip_length = (arrival_time - departure_time) / 60000
        cost += (minutes_till_departure / self.costs['min_departure']) + 1
        cost += (trip_length / self.costs['min_trip_length']) + 1
        self.route_logger.append_to_log("%d Minuten bis Abfahrt, %d Punkte"
                % (minutes_till_departure, (minutes_till_departure/self.costs['min_departure'])+1))
        self.route_logger.append_to_log("%d Minuten Dauer, %d Punkte"
                % (trip_length, (trip_length/self.costs['min_trip_length'])+1))

        # create and return transport route object
        route_description = self.translator.translate("transport_creator", "transport_route_description") \
                % (minutes_till_departure, trip_length, (number_of_trips-1),
                ' '.join(transport_vehicles), walking_distance)
        return RouteTransportCreator.TransportRouteObject(route, cost, route_description)

    class TransportRouteObject:
        def __init__(self, route, cost, route_description):
            self.route = route
            self.cost = cost
            self.description = route_description
