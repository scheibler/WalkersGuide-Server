server_version = '1.0.0'
supported_api_version_list = [ 1 ]
supported_map_version_list = [ 1 ]
# supported user languages
supported_language_list = ["en", "de"]
# supported public transport provider
supported_public_transport_provider_list = ["db", "vbb"]
# routing constants
max_distance_between_start_and_destination_in_meters = 25000
supported_route_point_object_list = ["point", "entrance", "gps", "intersection", "pedestrian_crossing", "poi", "station", "street_address"]
supported_route_segment_object_list = ["footway", "footway_intersection", "footway_route", "transport"]
supported_indirection_factor_list = [1.0, 1.5, 2.0, 3.0, 4.0]
supported_way_class_list = ["big_streets", "small_streets", "paved_ways", "unpaved_ways", "unclassified_ways", "steps"]
# poi constants
supported_poi_category_listp = ["transport_bus_tram", "transport_train_lightrail_subway",
        "transport_airport_ferry_aerialway", "transport_taxi", "food", "entertainment",
        "tourism", "nature", "finance", "shop", "health", "education", "public_service",
        "all_buildings_with_name", "entrance", "surveillance", "bench", "trash", "bridge",
        "named_intersection", "other_intersection", "pedestrian_crossings"]
