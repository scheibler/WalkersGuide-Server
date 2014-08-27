#!/usr/bin/python
# -*- coding: utf-8 -*-

# api description
# https://developers.google.com/maps/documentation/geocoding/

import requests, geometry

def get_address(lat, lon, sensor=False):
    language = "de"
    r = requests.get("https://maps.googleapis.com/maps/api/geocode/json?latlng=%f,%f&sensor=%s&language=%s" \
                    % (lat, lon, str.lower(str(sensor)), language))
    contents = r.json()
    if contents['status'] == "OK":
        try:
            location = contents['results'][0]['geometry']['location']
            distance = geometry.distance_between_two_points(lat, lon, location['lat'], location['lng'])
            print "dist = %d" % distance
            if distance < 50:
                return contents['results'][0]['formatted_address']
        except KeyError as e:
            print e
            return None
        except IndexError as e:
            print e
            return None
    return None

def get_latlon(address, sensor=False):
    language = "de"
    r = requests.get("https://maps.googleapis.com/maps/api/geocode/json?address=%s&sensor=%s&language=%s" \
                    % (address.replace(" ", "+"), str.lower(str(sensor)), language))
    contents = r.json()
    if contents['status'] == "OK":
        try:
            contents = contents['results'][0]
            location = contents['geometry']['location']
            return {'lat':location['lat'], 'lon':location['lng']}
        except KeyError as e:
            print e
            return None
        except IndexError as e:
            print e
            return None
    return None

