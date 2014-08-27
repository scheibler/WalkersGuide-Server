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

get_map_sequence_number() {
    # first check, if database and map state file exist
    if [ -z "$(psql -h $server_address -U $user_name -l | grep -i $db_raw_name)" ]; then
        return 41
    fi
    if [ ! -f "$map_state_file" ]; then
        return 42
    fi

    # get sequence number
    echo $(grep "sequenceNumber" "$map_state_file" | cut -d '=' -f2)
    return 0
}
