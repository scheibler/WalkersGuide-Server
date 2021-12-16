#!/bin/bash

# import configuration data
folder_name=$(dirname "$0")
source "$folder_name/configuration.sh"
source "$folder_name/helper_functions.sh"


###
# routing table
###

echo -e "\nCreate route table and import into database -- started at $(get_timestamp)"
cd "$poi_temp_subfolder"
java $osm2po_ram_param -jar "$osm2po_executable" \
    config="$osm2po_config" prefix="$db_prefix" cmd=tjsgp "$pbf_osm_file" \
    postp.0.class=de.cm.osm2po.plugins.postp.PgRoutingWriter
if [ ! -d "$db_prefix" ]; then
    echo "Error: Could not create osm2po routing table folder"
    exit 3
fi

# delete last 6 lines from sql script
head -n -6 "$db_prefix/$db_routing_table.sql" > "$db_prefix/$db_routing_table.sql.new"
if [[ $? != 0 ]]; then
    echo "Can't delete last 6 lines from routing table sql script"
    exit 3
fi
rm "$db_prefix/$db_routing_table.sql"
mv "$db_prefix/$db_routing_table.sql.new" "$db_prefix/$db_routing_table.sql"

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
echo -e "$commands" >> "$db_prefix/$db_routing_table.sql"

# import data into database
psql -d $db_tmp_name -1 -q -X -v ON_ERROR_STOP=1 \
    -f "$db_prefix/$db_routing_table.sql"
if [[ $? != 0 ]]; then
    echo "\nError during routing table import"
    exit 3
fi
rm -R "$db_prefix"


###
# poi and intersection data dumps
###

echo -e "\nCreate poi dumps -- started at $(get_timestamp)"
# convert map to o5m
osmconvert "$pbf_osm_file" -o="$o5m_osm_file"
if [ ! -f "$o5m_osm_file" ]; then
    echo "o5m file could not be created"
    exit 4
fi

# pedestrian crossings
filter="highway=crossing or railway=crossing or crossing="
osmfilter "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| osmosis --read-xml file=- \
    --write-pgsql-dump directory="$poi_temp_subfolder"
mv nodes.txt pedestrian_crossings.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# outer buildings
filter="building= or amenity= or shop= or tourism= or leisure= or public_transport=station or railway=station =halt"
osmfilter "$o5m_osm_file" --keep-nodes= --keep-ways="$filter" --keep-relations="$filter" \
| osmosis --read-xml file=- \
    --write-pgsql-dump directory="$poi_temp_subfolder" enableLinestringBuilder=yes enableBboxBuilder=yes
mv ways.txt outer_buildings.txt
rm nodes.txt relation_members.txt relations.txt users.txt way_nodes.txt

# subway entrances
filter="railway=subway_entrance"
osmfilter "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| osmosis --read-xml file=- \
    --write-pgsql-dump directory="$poi_temp_subfolder"
mv nodes.txt subway_entrances.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# building entrances
filter="entrance= building=entrance"
osmfilter "$o5m_osm_file" --keep-nodes="$filter" --keep-ways= --keep-relations= \
| osmosis --read-xml file=- \
    --write-pgsql-dump directory="$poi_temp_subfolder"
mv nodes.txt building_entrances.txt
rm ways.txt relation_members.txt relations.txt users.txt way_nodes.txt

# poi from nodes, ways and relations
filter="building=apartments =dormitory =hotel =retail =cathedral =chapel =church =civic =hospital =school =university =public or \
building= and name= or place= and name= or \
amenity= or shop= or tourism= or leisure= or office= or craft= or natural= or \
historic= or man_made= or bridge= or healthcare= or \
public_transport=stop_position =station or aeroway=terminal =aerodrom =helipad or aerialway=station or \
highway=bus_stop =crossing =traffic_signals or railway=halt =station =tram_stop =crossing"

# ways
osmfilter "$o5m_osm_file" --keep-nodes= --keep-ways="$filter" --keep-relations= \
| osmosis --read-xml file=- \
    --write-pgsql-dump directory="$poi_temp_subfolder" enableLinestringBuilder=yes enableBboxBuilder=yes
mv ways.txt poi_ways.txt
rm nodes.txt relation_members.txt relations.txt users.txt way_nodes.txt

# nodes and relations
osmfilter "$o5m_osm_file" --ignore-dependencies \
    --keep-nodes="$filter" --keep-ways= --keep-relations="$filter" \
| osmosis --read-xml file=- \
    --write-pgsql-dump directory="$poi_temp_subfolder"
mv nodes.txt poi_nodes.txt
mv relations.txt poi_relations.txt
rm relation_members.txt users.txt way_nodes.txt ways.txt "$o5m_osm_file"

echo -e "\nRouting table import and poi data extraction successful -- started at $(get_timestamp)"
exit 0
