#!/bin/bash


# helper functions
# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"

# timestamp
get_timestamp() {
    year=$(date +%Y)
    month=$(date +%m)
    day=$(date +%d)
    hour=$(date +%H)
    minute=$(date +%M)
    second=$(date +%S)
    echo "$hour:$minute:$second $year.$month.$day"
}

get_local_map_sequence_number() {
    # check, if map state file exist
    if [ ! -f "$map_state_file" ]; then
        return 41
    fi
    # get sequence number
    local_map_version=$(grep "sequenceNumber" "$map_state_file" | cut -d '=' -f2)
    if [ -z "$local_map_version" ]; then
        return 42
    fi
    echo "$local_map_version"
    return 0
}

get_local_productive_map_sequence_number() {
    # , if map state file exist
    if [ ! -f "$productive_db_map_state_file" ]; then
        return 41
    fi
    # get sequence number
    productive_map_version=$(grep "sequenceNumber" "$productive_db_map_state_file" | cut -d '=' -f2)
    if [ -z "$productive_map_version" ]; then
        return 42
    fi
    echo "$productive_map_version"
    return 0
}

get_online_map_sequence_number() {
    online_map_version=$(wget -q -O - "$download_state_file_url" | grep "sequenceNumber" | cut -d '=' -f2)
    if [ -z "$online_map_version" ]; then
        return 44
    fi
    echo "$online_map_version"
    return 0
}
