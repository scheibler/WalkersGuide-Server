#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo "Create database $db_active_name at $(get_timestamp)"
# configure temp folder
if [ -d "$temp_folder" ]; then
    # clean up
    rm -R -f $temp_folder/*
    if [[ $? != 0 ]]; then
        echo "Could not clean temp folder $temp_folder"
        exit 1
    fi
else
    # create temp folder
    mkdir "$temp_folder"
    if [[ $? != 0 ]]; then
        echo "Could not create temp folder $temp_folder"
        exit 1
    fi
fi
# create temp subfolders
mkdir "$maps_temp_subfolder" "$osm_data_temp_subfolder" "$poi_temp_subfolder"

# download map(s)
echo "download new map(s) -- started at $(get_timestamp)"
for url in "${download_map_urls[@]}"
do
    echo "Download $url"
    wget -q --directory-prefix "$maps_temp_subfolder" "$url"
    wget_rc=$?
    if [[ $wget_rc != 0 ]]; then
        echo "Error during download: wget rc = $wget_rc"
        exit 1
    fi
done

# merge or rename map(s)
number_of_downloaded_maps=$(ls -1 "$maps_temp_subfolder" | wc -l)
if [[ $number_of_downloaded_maps = 1 ]]; then
    # rename to $pbf_osm_file
    mv "$maps_temp_subfolder/$(ls -1 "$maps_temp_subfolder" | head -n 1)" "$pbf_osm_file"
elif [[ $number_of_downloaded_maps > 1 ]]; then
    # merge into single .pbf file
    osmium merge "$maps_temp_subfolder"/* -o "$pbf_osm_file"
fi
if [ ! -f "$pbf_osm_file" ]; then
    echo "Map file $pbf_osm_file could not be created"
    exit 1
fi

# create new tmp database
echo -e "\nCreate new tmp osm database -- started at $(get_timestamp)"

# delete old temp database if available
result=$(psql -h $server_address -U $user_name -l | cut -d '|' -f1 | tr -d ' ' | grep "^$db_tmp_name$")
if [ ! -z "$result" ]; then
    # end all potential active connections to the tmp database
    postgresql_version=$(psql --version | head -n 1 | awk '{print $3}' | awk -F "." '{print $1$2}')
    if (( $postgresql_version < 92)); then
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(procpid) from pg_stat_activity where datname = '$db_tmp_name';"
    else
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db_tmp_name';"
    fi
    # delete
    psql -h $server_address -U $user_name -d postgres -c "DROP DATABASE $db_tmp_name;"
    if [[ $? != 0 ]]; then
        exit 21
    fi
fi

# create new db
createdb -h $server_address -U $user_name -O $user_name "$db_tmp_name"
if [[ $? != 0 ]]; then
    exit 1
fi

# load extensions
echo -e "\nLoad database extensions"
psql -h $server_address -U $user_name -d $db_tmp_name -c "CREATE EXTENSION postgis;"
if [[ $? != 0 ]]; then
    exit 1
fi
psql -h $server_address -U $user_name -d $db_tmp_name -c "CREATE EXTENSION hstore;"
if [[ $? != 0 ]]; then
    exit 1
fi
psql -h $server_address -U $user_name -d $db_tmp_name -c "CREATE EXTENSION pgrouting;"
if [[ $? != 0 ]]; then
    exit 1
fi

# load db schema
echo -e "\nCreate database schema"
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6.sql"
if [[ $? != 0 ]]; then
    exit 1
fi
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6_action.sql"
if [[ $? != 0 ]]; then
    exit 1
fi
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6_bbox.sql"
if [[ $? != 0 ]]; then
    exit 1
fi
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6_linestring.sql"
if [[ $? != 0 ]]; then
    exit 1
fi

# load sql helper functions
echo -e "\nload several sql helper functions"
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/misc_functions.sql"
if [[ $? != 0 ]]; then
    exit 1
fi

# import osm data and create routing and poi tables in parallel
old_directory=$(pwd)
parallel -- "$folder_name/task1-osm_data_import.sh" "$folder_name/task2-routing_table_import.sh"
if [[ $? != 0 ]]; then
    echo "\nError during parallel execution of osm_data_import and routing_table_import"
    exit 1
fi

# import poi and intersection tables in parallel
parallel -- "$folder_name/task3-poi_table_import.sh" "$folder_name/task4-intersection_table_import.sh" "$folder_name/task5-hiking_trails_import.sh"
if [[ $? != 0 ]]; then
    echo "\nError during parallel execution of poi_table_import and intersection_table_import"
    exit 1
fi
cd "$old_directory"

# create wg_map_version table
create_map_version_table="\
DROP TABLE IF EXISTS $db_map_info;
CREATE TABLE $db_map_info (id text, version integer, created bigint);"
psql -h $server_address -U $user_name -d $db_tmp_name -c "$create_map_version_table"
if [[ $? != 0 ]]; then
    exit 1
fi
insert_version_information="\
INSERT INTO $db_map_info VALUES ('$db_active_name', $db_map_version, $(date +%s%3N));"
psql -h $server_address -U $user_name -d $db_tmp_name -c "$insert_version_information"
if [[ $? != 0 ]]; then
    exit 1
fi

# rescue access statistics table from active database
check_if_access_statistics_table_exists_command="SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename  = '$db_access_statistics_table');"
if [ "$( psql -A -t -h $server_address -U $user_name -d $db_active_name -c "$check_if_access_statistics_table_exists_command" )" = 't' ]; then
    pg_dump -h $server_address -U $user_name -d $db_active_name -t $db_access_statistics_table \
        | psql -h $server_address -U $user_name -d $db_tmp_name
    echo -e "\nRescued access statistics table"
fi

# clean up new database
echo -e "\nanalyse database -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -c "VACUUM ANALYZE;"
if [[ $? != 0 ]]; then
    echo "Error during analyse"
    exit 1
fi

echo -e "\nrename databases -- started at $(get_timestamp)"
# delete previous productive database if available
result=$(psql -h $server_address -U $user_name -l | cut -d '|' -f1 | tr -d ' ' | grep "^$db_active_name$")
if [ ! -z "$result" ]; then
    # end all potential active connections to the productive database
    postgresql_version=$(psql --version | head -n 1 | awk '{print $3}' | awk -F "." '{print $1$2}')
    if (( $postgresql_version < 92)); then
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(procpid) from pg_stat_activity where datname = '$db_active_name';"
    else
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db_active_name';"
    fi
    # delete
    psql -h $server_address -U $user_name -d postgres -c "DROP DATABASE $db_active_name;"
    if [[ $? != 0 ]]; then
        echo -e "\nCan't delete old productive database"
        exit 1
    fi
fi
# rename temp db to active db
psql -h $server_address -U $user_name -d postgres -c "ALTER DATABASE $db_tmp_name RENAME TO $db_active_name;"
if [[ $? != 0 ]]; then
    echo -e "\nCan't rename temp database to active one"
    exit 1
fi

# cleanup
# remove config file
rm "$folder_name/configuration.sh"
# clean temp folder
rm -R -f $temp_folder/*

echo -e "\nProductive database created at $(get_timestamp)"
exit 0
