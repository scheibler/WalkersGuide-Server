server_version = '1.4.2'
supported_api_version_list = [ 3, 4 ]
supported_map_version_list = [ 2, 3 ]
supported_language_list = ["en", "de"]
supported_feedback_token_list = ["question", "map_request", "pt_provider_request"]
# routing constants
max_distance_between_start_and_destination_in_meters = 30000
supported_route_point_object_list = ["point", "entrance", "gps", "intersection", "pedestrian_crossing", "poi", "station", "street_address"]
supported_way_class_list = ["big_streets", "small_streets", "paved_ways", "unpaved_ways", "unclassified_ways", "steps"]
# poi constants
supported_poi_category_listp = ["transport_bus_tram", "transport_train_lightrail_subway",
        "transport_airport_ferry_aerialway", "transport_taxi",
        "food", "entertainment", "finance", "shop", "health", "education", "public_service",
        "tourism", "all_buildings_with_name", "entrance", "surveillance", "bench", "trash",
        "named_intersection", "other_intersection", "pedestrian_crossings", "bridge"]

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
    MAP_OUTDATED       = 557
    # poi
    NO_POI_TAGS_SELECTED = 560
    # route calculation
    START_OR_DESTINATION_MISSING = 570
    START_AND_DESTINATION_TOO_FAR_AWAY = 571
    TOO_MANY_WAY_CLASSES_IGNORED = 572
    NO_ROUTE_BETWEEN_START_AND_DESTINATION = 573

