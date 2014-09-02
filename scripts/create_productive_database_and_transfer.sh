#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

if [[ $remote_user == "" || $remote_host == "" || $remote_port == "" || $remote_identity_keyfile == "" ]]; then
    echo "Options for remote server connection missing"
    exit 50
fi

# get map versions
local_map_version=$(get_map_sequence_number)
if [ -z "$local_map_version" ]; then
    echo "Could not get local map sequence number"
    exit 51
fi
remote_map_version=$($remote_full_ssh_command $remote_script_path/osm_database_wrapper.sh map_version)
if [[ $? != 0 ]]; then
    echo "Could not get remote map sequence number"
    exit 51
fi
# compare
if [[ $local_map_version != $remote_map_version ]]; then
    echo -e "The local and remote maps are at different versions, cant proceed\nLocal = $local_map_version\nRemote = $remote_map_version"
    exit 51
fi

# lock remote server
$remote_full_ssh_command $remote_script_path/osm_database_wrapper.sh lock
if [[ $? != 0 ]]; then
    echo "Could not lock remote server"
    exit 52
fi

# now, raw osm maps of local and remote server are at same version
# next step is to create necessary tables like poi and intersections from the raw database
# this process runs locally
"$folder_name/create_productive_database.sh"
rc=$?
if [[ $rc != 0 ]]; then
    $remote_full_ssh_command $remote_script_path/osm_database_wrapper.sh unlock
    echo "Error during productive database creation"
    exit $rc
fi

# create dumps of new database tables
echo "create dumps of new database tables"
tables="-t entrances -t "$db_prefix"_2po_4pgr -t intersections -t intersection_data \
-t outer_buildings -t poi -t stations -t traffic_signals -t transport_lines -t way_class_weights"
pg_dump -h $server_address -U $user_name -b -C -Fc -Z9 $tables $db_active_name -f $dumped_tables_file
if [[ $? != 0 ]]; then
    $remote_full_ssh_command $remote_script_path/osm_database_wrapper.sh unlock
    echo "Error during database dumping"
    exit 53
fi

# transfer to remote server via rsync
echo "transfer to remote server via rsync"
i=0
max_restarts=3
last_exit_code=1
while [ $i -le $max_restarts ]
do
    i=$(( $i + 1 ))
    rsync --partial -e "ssh $remote_ssh_options" $dumped_tables_file $remote_ssh_destination:$remote_tmp_path/
    last_exit_code=$?
    if [ $last_exit_code -eq 0 ]; then
        break
    fi
    sleep 30
done
if [[ $last_exit_code != 0 ]]; then
    $remote_full_ssh_command $remote_script_path/osm_database_wrapper.sh unlock
    echo "Error during dump file upload"
    exit 54
fi

# start import script on remote server
echo "start import script at remote server"
$remote_full_ssh_command "nohup $remote_script_path/osm_database_wrapper.sh create_productive_from_dumps &" &

# clean dump tables file
#rm -R -f $dumped_tables_file
#if [[ $? != 0 ]]; then
#    $remote_full_ssh_command $remote_script_path/osm_database_wrapper.sh unlock
#    echo "Could not delete dumped_tables file"
#    exit 55
#fi
exit 0
