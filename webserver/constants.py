server_version = '1.1.0'
supported_api_version_list = [ 1, 2 ]
supported_map_version_list = [ 2 ]
supported_language_list = ["en", "de"]
# routing constants
max_distance_between_start_and_destination_in_meters = 30000
supported_route_point_object_list = ["point", "entrance", "gps", "intersection", "pedestrian_crossing", "poi", "station", "street_address"]
# poi constants
supported_poi_category_listp = ["transport_bus_tram", "transport_train_lightrail_subway",
        "transport_airport_ferry_aerialway", "transport_taxi", "food", "entertainment",
        "tourism", "nature", "finance", "shop", "health", "education", "public_service",
        "all_buildings_with_name", "entrance", "surveillance", "bench", "trash", "bridge",
        "named_intersection", "other_intersection", "pedestrian_crossings"]

# webserver return codes
class ReturnCode:
    # default http response codes
    BAD_REQUEST = 400
    REQUEST_IN_PROGRESS = 429
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    # walkersguide specific errors
    # misc
    CANCELLED_BY_CLIENT = 550
    # map
    MAP_LOADING_FAILED = 555
    WRONG_MAP_SELECTED = 556
    # poi
    NO_POI_TAGS_SELECTED = 560
    # public transport
    PUBLIC_TRANSPORT_PROVIDER_LOADING_FAILED = 565
    PUBLIC_TRANSPORT_STATION_NOT_FOUND = 566
    # route calculation
    START_OR_DESTINATION_MISSING = 570
    START_AND_DESTINATION_TOO_FAR_AWAY = 571
    TOO_MANY_WAY_CLASSES_IGNORED = 572
    NO_ROUTE_BETWEEN_START_AND_DESTINATION = 573



# deprecated params
#
# in api version 2
supported_indirection_factor_list = [1.0, 1.5, 2.0, 3.0, 4.0]
supported_way_class_list = ["big_streets", "small_streets", "paved_ways", "unpaved_ways", "unclassified_ways", "steps"]
supported_route_segment_object_list = ["footway", "footway_intersection", "footway_route", "transport"]

