#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

# create new productive database
echo "Create productive database -- started at $(get_timestamp)"

# delete old temp database if available
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_tmp_name ")
if [ ! -z "$result" ]; then
    # end all potential active connections to the backup database
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

# download new map, needed for route table creator
# make sure, that your raw database is at the latest version, before proceed
"$folder_name/update_raw_database.sh"
rc=$?
if [[ $rc != 0 ]]; then
    echo "Raw database not at the latest version, can't proceed."
    exit $rc
fi
if [ -f "$pbf_osm_file" ]; then
    rm -f "$pbf_osm_file"
    if [[ $? != 0 ]]; then
        echo "Could not delete old maps file"
        exit 22
    fi
fi
echo "download new map -- started at $(get_timestamp)"
wget -q -O "$pbf_osm_file" "$download_map_url"
if [ ! -f "$pbf_osm_file" ]; then
    echo "Error: Could not download new map data"
    exit 22
fi

# convert to o5m
if [ -f "$o5m_osm_file" ]; then
    rm -f "$o5m_osm_file"
    if [[ $? != 0 ]]; then
        echo "Could not delete old o5m maps file"
        exit 22
    fi
fi
"$osmconvert_file" "$pbf_osm_file" -o="$o5m_osm_file"
if [ ! -f "$o5m_osm_file" ]; then
    echo "o5m file could not be created"
    exit 22
fi

# create new db from raw db template
echo -e "\nCreate new temp osm database -- started at $(get_timestamp)"
createdb -h $server_address -U $user_name -O $user_name -T "$db_raw_name" "$db_tmp_name"
if [[ $? != 0 ]]; then
    echo "Can't create temp database from raw database template"
    exit 21
fi

# create route table and import into database
echo -e "\nCreate route table and import into database -- started at $(get_timestamp)"
prefix="$db_prefix"
sufix="_2po_4pgr"
routing_table_name="$prefix$sufix"
# remove old data
if [ -d "$temp_folder/$db_prefix" ]; then
    rm -R "$temp_folder/$db_prefix"
    if [[ $? != 0 ]]; then
        echo "Could not delete old temp osm2po route folder"
        exit 23
    fi
fi
current_folder="$(pwd)"
cd "$temp_folder"
java -Xmx$ram -jar "$osm2po_file" config="$osm2po_config" prefix="$db_prefix" cmd=tjsgp "$pbf_osm_file"
rc=$?
cd "$current_folder"
if [[ $rc != 0 ]]; then
    echo -e "\nError during routing table creation"
    exit 23
fi
if [ ! -d "$temp_folder/$db_prefix" ]; then
    echo "Error: Could not create osm2po routing table folder"
    exit 23
fi

# delete last 6 lines from sql script
head -n -6 "$temp_folder/$db_prefix/$routing_table_name.sql" > "$temp_folder/$db_prefix/$routing_table_name.sql.new"
if [[ $? != 0 ]]; then
    echo "Can't delete last 6 lines from routing table sql script"
    exit 23
fi
rm "$temp_folder/$db_prefix/$routing_table_name.sql"
if [[ $? != 0 ]]; then
    echo "Can't delete old routing table sql script"
    exit 23
fi
mv "$temp_folder/$db_prefix/$routing_table_name.sql.new" "$temp_folder/$db_prefix/$routing_table_name.sql"
if [[ $? != 0 ]]; then
    echo "Can't rename new routing table sql script"
    exit 23
fi

# append some lines to the created sql routing table import script
commands="\
-- enable timing\n\
\\\timing\n\
\n\
-- update kmh table\n\
-- set all cycleways (foot=yes), footways, tracks and paths with good smoothness,\n\
-- hard surface, grade1 or grade2 to class 3 (paved ways)\n\
update $routing_table_name set kmh=3 where \n\
    (get_bit(flags::bit(16), 12) = 1 or get_bit(flags::bit(16), 10) = 1 or get_bit(flags::bit(16), 8) = 1)\n\
    and (\n\
        (kmh = 5 and clazz >= 13 and clazz <= 15)\n\
        or (kmh = 7 and clazz = 17 and get_bit(flags::bit(16), 14) = 1)\n\
    );\n\
-- set all cycleways (foot=yes), footways, services, tracks and paths with bad smoothness,\n\
-- soft surface, grade3,4,5 to class 4 (unpaved ways)\n\
update $routing_table_name set kmh=4 where \n\
    (get_bit(flags::bit(16), 11) = 1 or get_bit(flags::bit(16), 9) = 1 or get_bit(flags::bit(16), 7) = 1)\n\
    and (\n\
        (kmh = 3 and clazz = 12)\n\
        or (kmh = 5 and clazz >= 13 and clazz <= 15)\n\
        or (kmh = 7 and clazz = 17 and get_bit(flags::bit(16), 14) = 1)\n\
    );\n\
-- set all service roads with name to class 2 (small streets)\n\
update $routing_table_name set kmh=2 where kmh = 3 and clazz = 12 and get_bit(flags::bit(16), 6) = 1;\n\
-- set all other cycleways with foot = yes to class 5 (unclassified ways)\n\
update $routing_table_name set kmh=5 where kmh = 7 and clazz = 17 and get_bit(flags::bit(16), 14) = 1;\n\
-- set all ways with foot = no to class 7 (impassable)\n\
update $routing_table_name set kmh=7 where get_bit(flags::bit(16), 13) = 1;\n\
-- set all ways with access = no and foot != yes to class 7 (impassable)\n\
update $routing_table_name set kmh=7 where get_bit(flags::bit(16), 4) = 1 AND get_bit(flags::bit(16), 14) = 0;\n\
\n\
-- create index\n\
ALTER TABLE $routing_table_name ADD CONSTRAINT pkey_"$routing_table_name" PRIMARY KEY(id);\n\
CREATE INDEX idx_"$routing_table_name"_source ON $routing_table_name(source);\n\
CREATE INDEX idx_"$routing_table_name"_target ON $routing_table_name(target);\n\
CREATE INDEX idx_"$routing_table_name"_osm_source_id ON $routing_table_name(osm_source_id);\n\
CREATE INDEX idx_"$routing_table_name"_osm_target_id ON $routing_table_name(osm_target_id);\n\
CREATE INDEX idx_"$routing_table_name"_geom_way  ON $routing_table_name USING GIST (geom_way);\n\
\n\
-- cluster and analyse\n\
cluster $routing_table_name USING idx_"$routing_table_name"_geom_way;\n\
ANALYSE $routing_table_name;\n\
\n\
-- create and fill way class weights for several factors\n\
DROP TABLE IF EXISTS way_class_weights;\n\
CREATE TABLE way_class_weights(\n\
    id int,\n\
    x4 int,\n\
    x3 int,\n\
    x2 int,\n\
    x1_5 int,\n\
    x1 int );\n\
CREATE UNIQUE INDEX way_class_weights_idx ON way_class_weights (id);\n\
INSERT INTO way_class_weights VALUES (1, 60, 50, 33, 20, 0);\n\
INSERT INTO way_class_weights VALUES (2, 0, 0, 0, 0, 0);\n\
INSERT INTO way_class_weights VALUES (3, -60, -50, -33, -20, 0);\n\
INSERT INTO way_class_weights VALUES (4, 101, 101, 101, 101, 101);"
echo -e "$commands" >> "$temp_folder/$db_prefix/$routing_table_name.sql"

# import data into database
psql -h $server_address -U $user_name -d $db_tmp_name -1 -q -X -v ON_ERROR_STOP=1 -f "$temp_folder/$db_prefix/$routing_table_name.sql"
if [[ $? != 0 ]]; then
    exit 23
fi

# create poi tables
echo -e "\nCreate poi dumps -- started at $(get_timestamp)"
# clean temp folder
if [ "$(ls -A $temp_folder 2> /dev/null)" != "" ]; then
    rm -R -f $temp_folder/*
    if [[ $? != 0 ]]; then
        echo "Could not delete old data in the local temp folder"
        exit 25
    fi
fi
old_directory=$(pwd)
cd "$temp_folder"

# traffic signals
filter="highway=traffic_signals or crossing=traffic_signals"
"$osmfilter_file" "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| "$osmosis_file" --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt traffic_signals.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# outer buildings
filter="building= or amenity= or shop= or tourism= or leisure= or public_transport=station or railway=station =halt"
"$osmfilter_file" "$o5m_osm_file" --keep-nodes= --keep-ways="$filter" --keep-relations="$filter" \
| "$osmosis_file" --read-xml file=- \
--write-pgsql-dump directory="$temp_folder" enableLinestringBuilder=yes enableBboxBuilder=yes
mv ways.txt outer_buildings.txt
rm nodes.txt relation_members.txt relations.txt users.txt way_nodes.txt

# subway entrances
filter="railway=subway_entrance"
"$osmfilter_file" "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| "$osmosis_file" --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt subway_entrances.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# building entrances
filter="entrance= building=entrance"
"$osmfilter_file" "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| "$osmosis_file" --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt building_entrances.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# poi from nodes, ways and relations
filter="building=apartments =dormitory =hotel =retail =cathedral =chapel =church =civic =hospital =school =university =public or \
building= and name= or amenity= or shop= or tourism= or leisure= or office= or craft= or natural= or historic= or \
public_transport=stop_position =station or aeroway=terminal or aerialway=station or \
highway=bus_stop =crossing =traffic_signals or railway=halt =station =tram_stop =crossing or crossing="
# ways
"$osmfilter_file" "$o5m_osm_file" --keep-nodes= --keep-ways="$filter" --keep-relations= \
| "$osmosis_file" --read-xml file=- \
--write-pgsql-dump directory="$temp_folder" enableLinestringBuilder=yes enableBboxBuilder=yes
mv ways.txt poi_ways.txt
rm nodes.txt relation_members.txt relations.txt users.txt way_nodes.txt

# nodes and relations
"$osmfilter_file" "$o5m_osm_file" --ignore-dependencies \
--keep-nodes="$filter" --keep-ways= --keep-relations="$filter" \
| "$osmosis_file" --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt poi_nodes.txt
mv relations.txt poi_relations.txt
rm relation_members.txt users.txt way_nodes.txt ways.txt

# import into database
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 -f "$sql_files_folder/poi.sql"
if [[ $? != 0 ]]; then
    echo "Error during poi import"
    exit 25
fi

# create intersections table
echo -e "\nCreate intersections table -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -q -X -v ON_ERROR_STOP=1 -f "$sql_files_folder/intersections_and_traffic_signals.sql"
if [[ $? != 0 ]]; then
    exit 24
fi
cd "$old_directory"

# clean up new database
echo -e "\nanalyse database -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -c "VACUUM ANALYZE;"
if [[ $? != 0 ]]; then
    echo "Error during analyse"
    exit 26
fi

echo -e "\nrename databases -- started at $(get_timestamp)"
# delete previous backup database if available
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_backup_name")
if [ ! -z "$result" ]; then
    # end all potential active connections to the backup database
    postgresql_version=$(psql --version | head -n 1 | awk '{print $3}' | awk -F "." '{print $1$2}')
    if (( $postgresql_version < 92)); then
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(procpid) from pg_stat_activity where datname = '$db_backup_name';"
    else
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db_backup_name';"
    fi
    # delete
    psql -h $server_address -U $user_name -d postgres -c "DROP DATABASE $db_backup_name;"
    if [[ $? != 0 ]]; then
        echo -e "\nCan't delete old backup database"
        exit 27
    fi
fi
# rename previous current db to backup db
result=$(psql -h $server_address -U $user_name -l | grep -i "$db_active_name ")
if [ ! -z "$result" ]; then
    # end all active connections to the active database
    postgresql_version=$(psql --version | head -n 1 | awk '{print $3}' | awk -F "." '{print $1$2}')
    if (( $postgresql_version < 92)); then
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(procpid) from pg_stat_activity where datname = '$db_active_name';"
    else
        psql -h $server_address -U $user_name -d postgres \
            -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$db_active_name';"
    fi
    # rename
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

# copy map state file to provide the productive db version information
cp "$map_state_file" "$productive_db_map_state_file"
if [[ $? != 0 ]]; then
    echo "Can't copy map state file"
    exit 28
fi

# remove o5m map file
rm -f "$o5m_osm_file"

# and rename pbf map file
local_map_version=$(get_local_map_sequence_number)
if [[ $? != 0 ]]; then
    echo "Can't get local map state version"
    exit 28
fi
mv "$pbf_osm_file" "${pbf_osm_file:0:-4}.$local_map_version.pbf"

echo -e "\nProductive database created at $(get_timestamp)"
exit 0
