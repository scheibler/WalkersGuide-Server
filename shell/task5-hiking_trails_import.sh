#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo -e "\nImport hiking trails table -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -q -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/hiking_trails.sql"
if [[ $? != 0 ]]; then
    echo "Error during hiking trails import"
    exit 5
fi

echo -e "\nHiking table import successful -- started at $(get_timestamp)"
exit 0
