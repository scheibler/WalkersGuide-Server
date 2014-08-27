#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo "Database update process started"
local_map_version=$(get_map_sequence_number)
if [ -z "$local_map_version" ]; then
    echo "Can't get local map sequence number"
    exit 11
fi
online_map_version=$(wget -q -O - "$download_state_file_url" | grep "sequenceNumber" | cut -d '=' -f2)
if [ -z "$online_map_version" ]; then
    echo "Can't get online map sequence number"
    exit 11
fi

counter=1
while (( local_map_version < online_map_version )); do
    echo "database is at state $local_map_version, must be updated to state $online_map_version"
    "$osmosis_folder/bin/osmosis" --rri workingDirectory="$maps_folder" --simplify-change --wpc user="$user_name" database="$db_raw_name" password="$password"
    if [[ $? != 0 ]]; then
        echo "Error during update process"
        exit 12
    fi
    if (( counter > number_of_map_updates )); then
        echo "Max number of update cycles reached. Counter = $counter"
        exit 12
    fi
    local_map_version=$(grep "sequenceNumber" "$map_state_file" | cut -d '=' -f2)
    let counter=$counter+1
done

local_map_version=$(grep "sequenceNumber" "$map_state_file" | cut -d '=' -f2)
online_map_version=$(wget -q -O - "$download_state_file_url" | grep "sequenceNumber" | cut -d '=' -f2)
echo "Database now at state $local_map_version / $online_map_version"
exit 0
