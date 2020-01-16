#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

cd "$poi_temp_subfolder"
echo -e "\nImport poi tables -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -q -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/poi.sql"
if [[ $? != 0 ]]; then
    echo "Error during poi import"
    exit 4
fi

echo -e "\nPOI import successful -- started at $(get_timestamp)"
exit 0
