#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo "Database update process started"
counter=1
while ((1))
do
    # get current local and online map version from state.txt files
    local_map_version=$(get_local_map_sequence_number)
    if [[ $? != 0 ]]; then
        echo "Can't get local map sequence number"
        exit 11
    fi
    online_map_version=$(get_online_map_sequence_number)
    if [[ $? != 0 ]]; then
        echo "Can't get online map sequence number"
        exit 11
    fi
    if ((local_map_version == online_map_version)); then
        if ((counter == 1)); then
            echo "Raw database already up to date. Version: $local_map_version"
        else
            echo "Raw database updated successfully. Version: $online_map_version"
        fi
        exit 0
    fi
    echo "database is at state $local_map_version, must be updated to state $online_map_version"
    if (( counter > number_of_map_updates )); then
        echo "Max number of update cycles reached. Counter = $counter"
        exit 12
    fi
    "$osmosis_folder/bin/osmosis" --rri workingDirectory="$maps_folder" --simplify-change \
        --wpc host="$server_address" database="$db_raw_name" user="$user_name" password="$password"
    if [[ $? != 0 ]]; then
        echo "Error during update process"
        exit 12
    fi
    let counter=$counter+1
done
