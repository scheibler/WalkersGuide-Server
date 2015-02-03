#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo "Start transfer of current productive database to destination machine"
if [[ $remote_user == "" || $remote_host == "" || $remote_port == "" || $remote_identity_keyfile == "" ]]; then
    echo "Options for remote server connection missing"
    exit 50
fi

# clean temp folder
rm -R -f $temp_folder/*
if [[ $? != 0 ]]; then
    echo "Could not delete old data in the temp folder"
    exit 51
fi

# create dump of productive database
echo "create dump of productive database"
pg_dump -h $server_address -U $user_name -b -Fc -f "$dumped_tables_file" "$db_active_name"
if [[ $? != 0 ]]; then
    echo "Error during database dumping"
    exit 52
fi

# calculate checksum
old_directory=$(pwd)
cd "$temp_folder"
md5sum "$(basename $dumped_tables_file)" > "$dumped_tables_file.md5"
if [[ $? != 0 ]]; then
    echo "Could not calculate the check sum of the database dump file"
    cd "$old_directory"
    exit 53
fi
cd "$old_directory"

# copy state file
cp "$productive_db_map_state_file" "$temp_folder/$(basename $productive_db_map_state_file)"
if [[ $? != 0 ]]; then
    echo "Could not copy the map state file to the temp folder"
    exit 54
fi

# transfer temp folder to remote server via rsync
echo "transfer to remote server via rsync"
i=0
max_restarts=3
last_exit_code=1
while [ $i -le $max_restarts ]
do
    i=$(( $i + 1 ))
    if ((max_upload_speed == 0)); then
        rsync --archive --delete --partial -e "ssh $remote_ssh_options" \
            "$temp_folder/" $remote_ssh_destination:$remote_tmp_path/
    else
        echo "limited"
        rsync --archive --delete --bwlimit=$max_upload_speed --partial -e "ssh $remote_ssh_options" \
            "$temp_folder/" $remote_ssh_destination:$remote_tmp_path/
    fi
    last_exit_code=$?
    if [ $last_exit_code -eq 0 ]; then
        echo "Productive database transfered successfully. Please start import script at the destination machine to import dump"
        exit 0
    fi
    sleep 30
done
echo "Error during dump file upload"
exit 55
