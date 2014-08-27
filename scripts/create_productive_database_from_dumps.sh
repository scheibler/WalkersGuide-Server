#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

# create new productive database from dumps
# delete old one if available
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_tmp_name ")
if [ ! -z "$result" ]; then
    psql -h $server_address -U $user_name -d postgres -c "DROP DATABASE $db_tmp_name;"
    if [[ $? != 0 ]]; then
        exit 21
    fi
fi

# copy map state file to provide the productive db version information
cp "$map_state_file" "$productive_db_map_state_file"

# create new db from raw db template
echo -e "\nCreate new temp osm database -- started at $(get_timestamp)"
createdb -h $server_address -U $user_name -O $user_name -T "$db_raw_name" "$db_tmp_name"
if [[ $? != 0 ]]; then
    echo "Can't create temp database from raw database template"
    exit 22
fi

# check for dump_tables file
if [ ! -f "$dumped_tables_file" ]; then
    echo "dumped_tables file missing"
    exit 23
fi

# import into temp database
echo -e "\nImport dumped tables into database -- started at $(get_timestamp)"
pg_restore -h $server_address -U $user_name -d $db_tmp_name -e -1 $dumped_tables_file
if [[ $? != 0 ]]; then
    echo "Can't import dumped tables into temp database"
    exit 24
fi

# clean up new database
echo -e "\nanalyse database -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -c "ANALYZE;"
if [[ $? != 0 ]]; then
    echo "Error during analyse"
    exit 26
fi

# delete old backup and move current db to backup
echo -e "\nrename databases -- started at $(get_timestamp)"
# first, end all active connections to the database
postgresql_version=$(psql --version | head -n 1 | awk '{print $3}' | awk -F "." '{print $1$2}')
if (( $postgresql_version < 92)); then
    psql -h $server_address -U $user_name -d postgres \
        -c "select pg_terminate_backend(procpid) from pg_stat_activity where datname = '$db_active_name';"
else
    psql -h $server_address -U $user_name -d postgres \
        -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db_active_name';"
fi

# delete previous backup database if available
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_backup_name")
if [ ! -z "$result" ]; then
    psql -h $server_address -U $user_name -d postgres -c "DROP DATABASE $db_backup_name;"
    if [[ $? != 0 ]]; then
        echo -e "\nCan't delete old backup database"
        exit 27
    fi
fi

# rename previous current db to backup db
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_active_name ")
if [ ! -z "$result" ]; then
    psql -h $server_address -U $user_name -d postgres -c "ALTER DATABASE $db_active_name RENAME TO $db_backup_name;"
    if [[ $? != 0 ]]; then
        echo -e "\nCan't rename old active database to backup database"
        exit 27
    fi
fi

# rename temp db to active db
psql -h $server_address -U $user_name -d postgres -c "ALTER DATABASE $db_tmp_name RENAME TO $db_active_name;"
if [[ $? != 0 ]]; then
    echo -e "\nCan't rename temp database to active one"
    exit 27
fi

echo -e "\nProductive database created from dumps at $(get_timestamp)"
exit 0
