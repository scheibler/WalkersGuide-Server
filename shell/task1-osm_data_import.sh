#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

# extract dumps from downloaded map file
echo -e "\nCreate database dumps -- started at $(get_timestamp)"
osmosis --read-pbf file="$pbf_osm_file" \
    --write-pgsql-dump directory="$osm_data_temp_subfolder" enableLinestringBuilder=yes enableBboxBuilder=yes
if [[ $? != 0 ]]; then
    echo "Can't create dumps for import"
    exit 2
fi

# import
echo -e "\nImport dumps into database -- started at $(get_timestamp)"
cd "$osm_data_temp_subfolder"
psql -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_load_0.6.sql"
if [[ $? != 0 ]]; then
    echo "Error during osm data import"
    exit 2
fi

echo -e "\nImport successful -- started at $(get_timestamp)"
exit 0
