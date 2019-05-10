#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo "Started creation process at $(get_timestamp)"
# first, clean maps and temp folder
if [ "$(ls -A $maps_folder 2> /dev/null)" != "" ]; then
    rm -R -f $maps_folder/*
    if [[ $? != 0 ]]; then
        echo "Could not delete old data in the maps folder"
        exit 31
    fi
fi
if [ "$(ls -A $temp_folder 2> /dev/null)" != "" ]; then
    rm -R -f $temp_folder/*
    if [[ $? != 0 ]]; then
        echo "Could not delete old data in the temp folder"
        exit 31
    fi
fi

# prepare for differential map updates
"$osmosis_file" --rrii workingDirectory="$maps_folder"
if [[ $? != 0 ]]; then
    exit 31
fi
echo -e "baseUrl="$update_map_url"\nmaxInterval = 86400" > "$maps_folder/configuration.txt"
if [[ $? != 0 ]]; then
    exit 31
fi

# download new map and state file
echo "download new map -- started at $(get_timestamp)"
wget -q -O "$map_state_file" "$download_state_file_url"
if [ ! -f "$map_state_file" ]; then
    echo "Error: Could not download new map state file"
    exit 31
fi
wget -q -O "$pbf_osm_file" "$download_map_url"
if [ ! -f "$pbf_osm_file" ]; then
    echo "Error: Could not download new map data"
    exit 31
fi

# extract dumps from downloaded map file
echo -e "\nCreate database dumps -- started at $(get_timestamp)"
"$osmosis_file" --read-pbf-fast file="$pbf_osm_file" workers=4 --write-pgsql-dump directory="$temp_folder" enableLinestringBuilder=yes enableBboxBuilder=yes
if [[ $? != 0 ]]; then
    echo "Can't create dumps for import"
    exit 32
fi

# create new raw database
echo -e "\nCreate new raw osm database -- started at $(get_timestamp)"
# delete old one if available
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_raw_name ")
if [ ! -z "$result" ]; then
    # end all potential active connections to the raw database
    postgresql_version=$(psql --version | head -n 1 | awk '{print $3}' | awk -F "." '{print $1$2}')
    if (( $postgresql_version < 92)); then
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(procpid) from pg_stat_activity where datname = '$db_raw_name';"
    else
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db_raw_name';"
    fi
    # delete
    psql -h $server_address -U $user_name -d postgres -c "DROP DATABASE $db_raw_name;"
    if [[ $? != 0 ]]; then
        exit 33
    fi
fi
# create new db
createdb -h $server_address -U $user_name -O $user_name "$db_raw_name"
if [[ $? != 0 ]]; then
    exit 33
fi

# load extensions
echo -e "\nLoad database extensions"
psql -h $server_address -U $user_name -d $db_raw_name -c "CREATE EXTENSION postgis;"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_raw_name -c "CREATE EXTENSION hstore;"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_raw_name -c "CREATE EXTENSION pgrouting;"
if [[ $? != 0 ]]; then
    exit 33
fi

# load db schema
echo -e "\nCreate database schema"
psql -h $server_address -U $user_name -d $db_raw_name -X -v ON_ERROR_STOP=1 -f "$osmosis_folder/script/pgsnapshot_schema_0.6.sql"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_raw_name -X -v ON_ERROR_STOP=1 -f "$osmosis_folder/script/pgsnapshot_schema_0.6_action.sql"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_raw_name -X -v ON_ERROR_STOP=1 -f "$osmosis_folder/script/pgsnapshot_schema_0.6_bbox.sql"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_raw_name -X -v ON_ERROR_STOP=1 -f "$osmosis_folder/script/pgsnapshot_schema_0.6_linestring.sql"
if [[ $? != 0 ]]; then
    exit 33
fi

# load a few other sql helper functions
echo -e "\nload several sql helper functions"
psql -h $server_address -U $user_name -d $db_raw_name -X -v ON_ERROR_STOP=1 -f "$sql_files_folder/misc_functions.sql"
if [[ $? != 0 ]]; then
    exit 33
fi

# import database
echo -e "\nImport dumps into database -- started at $(get_timestamp)"
old_directory=$(pwd)
cd "$temp_folder"
psql -h $server_address -U $user_name -d $db_raw_name -X -v ON_ERROR_STOP=1 -f "$sql_files_folder/pgsnapshot_load_0.6.sql"
if [[ $? != 0 ]]; then
    exit 34
fi
cd "$old_directory"

# clean temp folder again
rm -R -f $temp_folder/*
if [[ $? != 0 ]]; then
    echo "Could not delete new data in the maps folder"
    exit 31
fi
echo -e "\nDatabase creation was successful at $(get_timestamp)"
exit 0
