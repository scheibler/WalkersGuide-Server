#!/usr/bin/python
# -*- coding: utf-8 -*-

import math

def bearing_between_two_points(lat1, lon1, lat2, lon2):
    """
    Calculates the bearing between two points.

    The formulae used is the following:
        θ = atan2(sin(Δlong).cos(lat2),
                  cos(lat1).sin(lat2) − sin(lat1).cos(lat2).cos(Δlong))

    :Parameters:
      - `pointA: The tuple representing the latitude/longitude for the
        first point. Latitude and longitude must be in decimal degrees
      - `pointB: The tuple representing the latitude/longitude for the
        second point. Latitude and longitude must be in decimal degrees

    :Returns:
      The bearing in degrees
    """
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    diffLong = math.radians(lon2 - lon1)

    x = math.sin(diffLong) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1)
            * math.cos(lat2) * math.cos(diffLong))

    initial_bearing = math.atan2(x, y)

    # Now we have the initial bearing but math.atan2 return values
    # from -180° to + 180° which is not what we want for a compass bearing
    # The solution is to normalize the initial bearing as shown below
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    return int(compass_bearing)

def turn_between_two_segments(bearing_new, bearing_old):
    turn = bearing_new - bearing_old
    if turn < 0:
        turn += 360
    return turn

def distance_between_two_points(lat1, lon1, lat2, lon2):
    return int(distance_between_two_points_as_float(lat1, lon1, lat2, lon2))

def distance_between_two_points_as_float(lat1, lon1, lat2, lon2):
    """
        Calculate the great circle distance between two points
        on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6367 * c * 1000

def get_center_point(lat1, lon1, lat2, lon2):
    center_point = {}
    if lat1 < lat2:
        center_point['lat'] = lat1 + math.fabs(lat1-lat2)/2
    else:
        center_point['lat'] = lat2 + math.fabs(lat1-lat2)/2
    if lon1 < lon2:
        center_point['lon'] = lon1 + math.fabs(lon1-lon2)/2
    else:
        center_point['lon'] = lon2 + math.fabs(lon1-lon2)/2
    return center_point

def get_boundary_box(lat, lon, radius):
    lat_diff = radius / distance_between_two_points_as_float(
            lat, lon, lat+1.0, lon)
    lon_diff = radius / distance_between_two_points_as_float(
            lat, lon, lat, lon+1.0)
    return {'bottom':lat-lat_diff, 'top':lat+lat_diff, 'left':lon-lon_diff, 'right':lon+lon_diff}

def convert_coordinate_to_float(coordinate):
    if type(coordinate) == type(0.0):
        return coordinate
    try:
        coordinate = int(coordinate)
        divisor = 1000000
        return float(coordinate) / divisor
    except ValueError as e:
        return None

def convert_coordinate_to_int(coordinate):
    if type(coordinate) == type(0):
        return coordinate
    try:
        return int(coordinate*1000000)
    except ValueError as e:
        return None

