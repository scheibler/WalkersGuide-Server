#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

if [[ "$1" == "create_raw" ]]; then
    if [ -f "$lock_file" ]; then
        echo -e "$(<$lock_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: $1: program busy" "$recipient_mail_address"
        echo "$(get_timestamp)   $1: program busy: $(<$lock_file)" >> "$log_file"
        exit 1
    fi
    echo "Raw database creation in progress" > "$lock_file"
    "$folder_name/create_raw_database.sh" > "$temp_log_file" 2>&1
    rc=$?
    if [[ $rc != 0 ]]; then
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: raw database creation failed" "$recipient_mail_address"
        echo "$(get_timestamp)   OSM raw database creation failed" >> "$log_file"
    else
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: raw database creation successful" "$recipient_mail_address"
        echo "$(get_timestamp)   OSM raw database creation successful" >> "$log_file"
    fi
    rm "$lock_file"
    exit $rc
fi

if [[ "$1" == "update_raw" ]]; then
    if [ -f "$lock_file" ]; then
        echo -e "$(<$lock_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: $1: program busy" "$recipient_mail_address"
        echo "$(get_timestamp)   $1: program busy: $(<$lock_file)" >> "$log_file"
        exit 1
    fi
    echo "Raw database update in progress" > "$lock_file"
    "$folder_name/update_raw_database.sh" > "$temp_log_file" 2>&1
    rc=$?
    if [[ $rc != 0 ]]; then
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: raw database update failed" "$recipient_mail_address"
        echo "$(get_timestamp)   OSM raw database update failed" >> "$log_file"
    else
        #echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: raw database update successful" "$recipient_mail_address"
        echo "$(get_timestamp)   OSM raw database update successful" >> "$log_file"
    fi
    rm "$lock_file"
    exit $rc
fi

if [[ "$1" == "create_productive" ]]; then
    if [ -f "$lock_file" ]; then
        echo -e "$(<$lock_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: $1: program busy" "$recipient_mail_address"
        echo "$(get_timestamp)   $1: program busy: $(<$lock_file)" >> "$log_file"
        exit 1
    fi
    echo "Creation of productive database in progress" > "$lock_file"
    "$folder_name/create_productive_database.sh" > "$temp_log_file" 2>&1
    rc=$?
    if [[ $rc != 0 ]]; then
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: Creation of productive  OSM database failed" "$recipient_mail_address"
        echo "$(get_timestamp)  Creation of productive  OSM database failed" >> "$log_file"
    else
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: Creation of productive  OSM database successful" "$recipient_mail_address"
        echo "$(get_timestamp)   Creation of productive  OSM database successful" >> "$log_file"
    fi
    rm "$lock_file"
    exit $rc
fi

if [[ "$1" == "create_productive_from_dumps" ]]; then
    if [ -f "$lock_file" ]; then
        echo -e "$(<$lock_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: $1: program busy" "$recipient_mail_address"
        echo "$(get_timestamp)   $1: program busy: $(<$lock_file)" >> "$log_file"
        exit 1
    fi
    echo "Creation of productive database from dumps in progress" > "$lock_file"
    "$folder_name/create_productive_database_from_dumps.sh" > "$temp_log_file" 2>&1
    rc=$?
    if [[ $rc != 0 ]]; then
        echo -e "$(<$temp_log_file)" | mail -s "osm database wrapper: Creation of productive  OSM database from dumps failed" \
            -aFrom:$sender_mail_address "$recipient_mail_address"
        echo "$(get_timestamp)  Creation of productive  OSM database from dumps failed" >> "$log_file"
    else
        echo -e "$(<$temp_log_file)" | mail -s "osm database wrapper: Creation of productive  OSM database from dumps successful" \
            -aFrom:$sender_mail_address "$recipient_mail_address"
        echo "$(get_timestamp)   Creation of productive  OSM database from dumps successful" >> "$log_file"
    fi
    rm "$lock_file"
    exit $rc
fi

if [[ "$1" == "transfer_productive" ]]; then
    if [ -f "$lock_file" ]; then
        echo -e "program is locked, cancel transfer to remote server" \
            | mail -s "osm database wrapper: Transfer to remote server failed" \
            -aFrom:$sender_mail_address "$recipient_mail_address"
        echo "$(get_timestamp)   $1: program is locked, cancel transfer to remote server" >> "$log_file"
        exit 5
    fi
    echo "Transfer productive db to remote server in progress" > "$lock_file"
    "$folder_name/transfer_productive_database.sh" > "$temp_log_file" 2>&1
    rc=$?
    if [[ $rc != 0 ]]; then
        echo -e "$(<$temp_log_file)" | mail \
            -s "osm database wrapper: Transfer productive db to remote server failed" \
            -aFrom:$sender_mail_address "$recipient_mail_address"
        echo "$(get_timestamp)  Transfer productive db to remote server failed" >> "$log_file"
    else
        echo -e "$(<$temp_log_file)" | mail \
            -s "osm database wrapper: Transfer productive db to remote server successful" \
            -aFrom:$sender_mail_address "$recipient_mail_address"
        echo "$(get_timestamp)   Transfer productive db to remote server successful" >> "$log_file"
    fi
    rm "$lock_file"
    exit $rc
fi

if [[ "$1" == "create_complete" ]]; then
    if [ -f "$lock_file" ]; then
        echo -e "$(<$lock_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: $1: program busy" "$recipient_mail_address"
        echo "$(get_timestamp)   $1: program busy: $(<$lock_file)" >> "$log_file"
        exit 1
    fi
    echo "Creation of complete database in progress" > "$lock_file"
    "$folder_name/create_complete_database.sh" > "$temp_log_file" 2>&1
    rc=$?
    if [[ $rc != 0 ]]; then
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: Creation of complete  OSM database failed" "$recipient_mail_address"
        echo "$(get_timestamp)  Creation of complete  OSM database failed" >> "$log_file"
    else
        echo -e "$(<$temp_log_file)" | mail -aFrom:$sender_mail_address -s "osm database wrapper: Creation of complete  OSM database successful" "$recipient_mail_address"
        echo "$(get_timestamp)   Creation of complete  OSM database successful" >> "$log_file"
    fi
    rm "$lock_file"
    exit $rc
fi

echo -e "$1 is no valid option" | mail -aFrom:$sender_mail_address -s "osm database wrapper: invalid option" "$recipient_mail_address"
echo "$(get_timestamp)   $1 is no valid option" >> "$log_file"
exit 3
