#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"

echo "Create raw and productive database $db_active_name in one step at $(get_timestamp)"

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

# download new map(s)
echo "download new map(s) -- started at $(get_timestamp)"
maps_parts_folder="$maps_folder/parts"
mkdir "$maps_parts_folder"
for url in "${download_map_urls[@]}"
do
    echo "Download $url"
    wget -q --directory-prefix "$maps_parts_folder" "$url"
    wget_rc=$?
    if [[ $wget_rc != 0 ]]; then
        echo "Error during download: wget rc = $wget_rc"
        exit 1
    fi
done

# merge or rename
number_of_downloaded_maps=$(ls -1 "$maps_parts_folder" | wc -l)
if [[ $number_of_downloaded_maps = 1 ]]; then
    # rename to $pbf_osm_file
    mv "$maps_parts_folder/$(ls -1 "$maps_parts_folder" | head -n 1)" "$pbf_osm_file"
elif [[ $number_of_downloaded_maps > 1 ]]; then
    # merge into single .pbf file
    osmium merge "$maps_parts_folder"/* -o "$pbf_osm_file"
fi
if [ ! -f "$pbf_osm_file" ]; then
    echo "Map file $pbf_osm_file could not be created"
    exit 1
fi
rm -R "$maps_parts_folder"

# convert to o5m
if [ -f "$o5m_osm_file" ]; then
    rm -f "$o5m_osm_file"
    if [[ $? != 0 ]]; then
        echo "Could not delete old o5m maps file"
        exit 22
    fi
fi
osmconvert "$pbf_osm_file" -o="$o5m_osm_file"
if [ ! -f "$o5m_osm_file" ]; then
    echo "o5m file could not be created"
    exit 22
fi

# extract dumps from downloaded map file
echo -e "\nCreate database dumps -- started at $(get_timestamp)"
osmosis --read-pbf-fast file="$pbf_osm_file" workers=8 --write-pgsql-dump directory="$temp_folder" enableLinestringBuilder=yes enableBboxBuilder=yes
if [[ $? != 0 ]]; then
    echo "Can't create dumps for import"
    exit 32
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
    exit 33
fi

# load extensions
echo -e "\nLoad database extensions"
psql -h $server_address -U $user_name -d $db_tmp_name -c "CREATE EXTENSION postgis;"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_tmp_name -c "CREATE EXTENSION hstore;"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_tmp_name -c "CREATE EXTENSION pgrouting;"
if [[ $? != 0 ]]; then
    exit 33
fi

# load db schema
echo -e "\nCreate database schema"
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6.sql"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6_action.sql"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6_bbox.sql"
if [[ $? != 0 ]]; then
    exit 33
fi
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_schema_0.6_linestring.sql"
if [[ $? != 0 ]]; then
    exit 33
fi

# load a few other sql helper functions
echo -e "\nload several sql helper functions"
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/misc_functions.sql"
if [[ $? != 0 ]]; then
    exit 33
fi

# import database
echo -e "\nImport dumps into database -- started at $(get_timestamp)"
old_directory=$(pwd)
cd "$temp_folder"
psql -h $server_address -U $user_name -d $db_tmp_name -X -v ON_ERROR_STOP=1 \
    -f "$sql_files_folder/pgsnapshot/pgsnapshot_load_0.6.sql"
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
echo -e "\nRaw database creation was successful at $(get_timestamp)"

# create route table and import into database
echo -e "\nCreate route table and import into database -- started at $(get_timestamp)"
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
java -Xmx$ram -jar "$osm2po_executable" \
    config="$osm2po_config" prefix="$db_prefix" cmd=tjsgp "$pbf_osm_file" \
    postp.0.class=de.cm.osm2po.plugins.postp.PgRoutingWriter
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
head -n -6 "$temp_folder/$db_prefix/$db_routing_table.sql" > "$temp_folder/$db_prefix/$db_routing_table.sql.new"
if [[ $? != 0 ]]; then
    echo "Can't delete last 6 lines from routing table sql script"
    exit 23
fi
rm "$temp_folder/$db_prefix/$db_routing_table.sql"
if [[ $? != 0 ]]; then
    echo "Can't delete old routing table sql script"
    exit 23
fi
mv "$temp_folder/$db_prefix/$db_routing_table.sql.new" "$temp_folder/$db_prefix/$db_routing_table.sql"
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
update $db_routing_table set kmh=3 where \n\
    (get_bit(flags::bit(16), 12) = 1 or get_bit(flags::bit(16), 10) = 1 or get_bit(flags::bit(16), 8) = 1)\n\
    and (\n\
        (kmh = 5 and clazz >= 13 and clazz <= 15)\n\
        or (kmh = 7 and clazz = 17 and get_bit(flags::bit(16), 14) = 1)\n\
    );\n\
-- set all cycleways (foot=yes), footways, services, tracks and paths with bad smoothness,\n\
-- soft surface, grade3,4,5 to class 4 (unpaved ways)\n\
update $db_routing_table set kmh=4 where \n\
    (get_bit(flags::bit(16), 11) = 1 or get_bit(flags::bit(16), 9) = 1 or get_bit(flags::bit(16), 7) = 1)\n\
    and (\n\
        (kmh = 3 and clazz = 12)\n\
        or (kmh = 5 and clazz >= 13 and clazz <= 15)\n\
        or (kmh = 7 and clazz = 17 and get_bit(flags::bit(16), 14) = 1)\n\
    );\n\
-- set all service roads with name to class 2 (small streets)\n\
update $db_routing_table set kmh=2 where kmh = 3 and clazz = 12 and get_bit(flags::bit(16), 6) = 1;\n\
-- set all other cycleways with foot = yes to class 5 (unclassified ways)\n\
update $db_routing_table set kmh=5 where kmh = 7 and clazz = 17 and get_bit(flags::bit(16), 14) = 1;\n\
-- set all ways with foot = no to class 7 (impassable)\n\
update $db_routing_table set kmh=7 where get_bit(flags::bit(16), 13) = 1;\n\
-- set all ways with access = no and foot != yes to class 7 (impassable)\n\
update $db_routing_table set kmh=7 where get_bit(flags::bit(16), 4) = 1 AND get_bit(flags::bit(16), 14) = 0;\n\
-- update cost table\n\
-- set cost of impassable ways to -1\n\
update $db_routing_table set cost=-1.0 where kmh = 7;\n\
\n\
-- create index\n\
ALTER TABLE $db_routing_table ADD CONSTRAINT pkey_"$db_routing_table" PRIMARY KEY(id);\n\
CREATE INDEX idx_"$db_routing_table"_source ON $db_routing_table(source);\n\
CREATE INDEX idx_"$db_routing_table"_target ON $db_routing_table(target);\n\
CREATE INDEX idx_"$db_routing_table"_osm_source_id ON $db_routing_table(osm_source_id);\n\
CREATE INDEX idx_"$db_routing_table"_osm_target_id ON $db_routing_table(osm_target_id);\n\
CREATE INDEX idx_"$db_routing_table"_geom_way  ON $db_routing_table USING GIST (geom_way);\n\
\n\
-- cluster and analyse\n\
cluster $db_routing_table USING idx_"$db_routing_table"_geom_way;\n\
ANALYSE $db_routing_table;"
echo -e "$commands" >> "$temp_folder/$db_prefix/$db_routing_table.sql"

# import data into database
psql -h $server_address -U $user_name -d $db_tmp_name -1 -q -X -v ON_ERROR_STOP=1 -f "$temp_folder/$db_prefix/$db_routing_table.sql"
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

# pedestrian crossings
filter="highway=crossing or railway=crossing or crossing="
osmfilter "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| osmosis --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt pedestrian_crossings.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# outer buildings
filter="building= or amenity= or shop= or tourism= or leisure= or public_transport=station or railway=station =halt"
osmfilter "$o5m_osm_file" --keep-nodes= --keep-ways="$filter" --keep-relations="$filter" \
| osmosis --read-xml file=- \
--write-pgsql-dump directory="$temp_folder" enableLinestringBuilder=yes enableBboxBuilder=yes
mv ways.txt outer_buildings.txt
rm nodes.txt relation_members.txt relations.txt users.txt way_nodes.txt

# subway entrances
filter="railway=subway_entrance"
osmfilter "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| osmosis --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt subway_entrances.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# building entrances
filter="entrance= building=entrance"
osmfilter "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| osmosis --read-xml file=- \
--write-pgsql-dump directory="$temp_folder"
mv nodes.txt building_entrances.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# poi from nodes, ways and relations
filter="building=apartments =dormitory =hotel =retail =cathedral =chapel =church =civic =hospital =school =university =public or \
building= and name= or amenity= or shop= or tourism= or leisure= or office= or craft= or natural= or historic= or \
man_made=beacon =campanile =communications_tower =lighthouse =surveillance =watermill =windmill or bridge= or \
public_transport=stop_position =station or aeroway=terminal =aerodrom =helipad or aerialway=station or \
highway=bus_stop =crossing =traffic_signals or railway=halt =station =tram_stop =crossing"

# ways
osmfilter "$o5m_osm_file" --keep-nodes= --keep-ways="$filter" --keep-relations= \
| osmosis --read-xml file=- \
--write-pgsql-dump directory="$temp_folder" enableLinestringBuilder=yes enableBboxBuilder=yes
mv ways.txt poi_ways.txt
rm nodes.txt relation_members.txt relations.txt users.txt way_nodes.txt

# nodes and relations
osmfilter "$o5m_osm_file" --ignore-dependencies \
--keep-nodes="$filter" --keep-ways= --keep-relations="$filter" \
| osmosis --read-xml file=- \
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

# create wg_map_version table
create_map_version_table="\
DROP TABLE IF EXISTS $db_map_info;
CREATE TABLE $db_map_info (id text, version integer, created bigint);"
psql -h $server_address -U $user_name -d $db_tmp_name -c "$create_map_version_table"
if [[ $? != 0 ]]; then
    exit 23
fi
insert_version_information="\
INSERT INTO $db_map_info VALUES ('$db_active_name', $db_map_version, $(date +%s%3N));"
psql -h $server_address -U $user_name -d $db_tmp_name -c "$insert_version_information"
if [[ $? != 0 ]]; then
    exit 23
fi

# clean up new database
echo -e "\nanalyse database -- started at $(get_timestamp)"
psql -h $server_address -U $user_name -d $db_tmp_name -c "VACUUM ANALYZE;"
if [[ $? != 0 ]]; then
    echo "Error during analyse"
    exit 26
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
        exit 27
    fi
fi
# rename temp db to active db
psql -h $server_address -U $user_name -d postgres -c "ALTER DATABASE $db_tmp_name RENAME TO $db_active_name;"
if [[ $? != 0 ]]; then
    echo -e "\nCan't rename temp database to active one"
    exit 27
fi

# cleanup
# rename pbf map file
mv "$pbf_osm_file" "${pbf_osm_file:0:-4}.$db_active_name.$(get_current_date).pbf"
# remove o5m map file
rm -f "$o5m_osm_file"
# remove config file
rm "$folder_name/configuration.sh"
# clean temp folder again
rm -R -f $temp_folder/*

echo -e "\nProductive database created at $(get_timestamp)"
exit 0
