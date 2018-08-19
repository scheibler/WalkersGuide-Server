#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo -e "Start transfer of current productive database to destination machine -- started at $(get_timestamp)"
if [[ $remote_user == "" || $remote_host == "" || $remote_port == "" || $remote_identity_keyfile == "" ]]; then
    echo "Options for remote server connection missing"
    exit 50
fi

# clean local temp folder
if [ "$(ls -A $temp_folder 2> /dev/null)" != "" ]; then
    rm -R -f $temp_folder/*
    if [[ $? != 0 ]]; then
        echo "Could not delete old data in the local temp folder"
        exit 51
    fi
fi

# create dump of productive database
pg_dump -h $server_address -U $user_name -b -Fc -f "$dumped_tables_file" "$db_active_name"
if [[ $? != 0 ]]; then
    echo "Error during database dumping"
    exit 52
fi

# switch into temp folder
old_directory=$(pwd)
cd "$temp_folder"

# split dump file
split -b 2GB -d "$dumped_tables_file" "$(basename $dumped_tables_file).s"
if [[ $? != 0 ]]; then
    echo "Error during split"
    cd "$old_directory"
    exit 53
fi

# calculate checksum of whole dump file
md5sum "$(basename $dumped_tables_file)" > "$dumped_tables_file.md5"
if [[ $? != 0 ]]; then
    echo "Could not calculate the check sum of the database dump file"
    cd "$old_directory"
    exit 54
fi

# remove big dumped_tables_file
rm -f "$dumped_tables_file"
if [[ $? != 0 ]]; then
    echo "Could not delete dumped tables file"
    exit 55
fi

# switch back into current folder
cd "$old_directory"

# copy state file
cp "$productive_db_map_state_file" "$temp_folder/$(basename $productive_db_map_state_file)"
if [[ $? != 0 ]]; then
    echo "Could not copy the map state file to the temp folder"
    exit 56
fi

# clean remote temp folder
if [ "$($remote_full_ssh_command ls -A $remote_tmp_path 2> /dev/null)" != "" ]; then
    $remote_full_ssh_command rm -R -f $remote_tmp_path/*
    if [[ $? != 0 ]]; then
        echo "Could not delete old data in the remote temp folder"
        exit 57
    fi
fi

# transfer temp folder to remote server via rsync
echo -e "\ntransfer to remote server via rsync -- started at $(get_timestamp)"
i=0
max_restarts=3
while [ $i -le $max_restarts ]
do
    rsync --append --archive --bwlimit=$max_upload_speed --partial -e "ssh $remote_ssh_options" \
        "$temp_folder/" $remote_ssh_destination:$remote_tmp_path/
    if [ $? -eq 0 ]; then
        echo "Productive database transfered successfully at $(get_timestamp). Please start import script at the destination machine to import dump"
        exit 0
    fi
    sleep 300
    i=$(( $i + 1 ))
done
echo "Error during dump file upload at $(get_timestamp)"
exit 58
