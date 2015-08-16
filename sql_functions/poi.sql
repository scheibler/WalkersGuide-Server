SET client_min_messages TO WARNING;
-- SET log_min_duration_statement TO 50;

CREATE OR REPLACE FUNCTION is_station(hstore)
RETURNS BOOLEAN AS $$
DECLARE
    tags hstore;
BEGIN
    tags := $1;
    if tags->'highway' = 'bus_stop' THEN
        return true;
    ELSIF tags->'railway' = 'tram_stop' THEN
        return true;
    ELSIF tags->'railway' = 'halt' THEN
        return true;
    ELSIF tags->'railway' = 'station' THEN
        return true;
    ELSIF tags->'amenity' = 'ferry_terminal' THEN
        return true;
    ELSIF tags->'aerialway' = 'station' THEN
        return true;
    ELSIF tags->'public_transport' = 'stop_position' THEN
        return true;
    END IF;
    return false;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_number_of_public_transport_lines_at_station(bigint, bigint)
RETURNS bigint AS $$
DECLARE
    poi_id bigint;
    s_id bigint;
    number_of_lines int;
    route_ref text;
    row RECORD;
BEGIN
    poi_id := $1;
    s_id := $2;
    number_of_lines := 0;
    FOR row IN SELECT rs.id, rs.tags->'ref' as nr, rs.tags->'to' as direction, rs.tags->'route' as type
            from relations  rs JOIN relation_members rm ON rs.id = rm.relation_id
            WHERE rs.tags->'route' = ANY('{"bus", "trolleybus", "ferry", "train", "tram", "subway", "monorail", "aerialway"}')
                AND rs.tags->'type' = 'route' AND rm.member_id = s_id
    LOOP
        IF row.nr IS NULL OR row.nr = '' THEN
            BEGIN
                SELECT rs.tags->'ref' INTO STRICT route_ref
                        FROM relations rs JOIN relation_members  rm ON rs.id = rm.relation_id
                        WHERE rm.member_id = row.id;
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN
                        CONTINUE;
                    WHEN TOO_MANY_ROWS THEN
                        CONTINUE;
            END;
        ELSE
            route_ref := row.nr;
        END IF;
        INSERT INTO transport_lines VALUES(poi_id, row.id, route_ref, row.direction, row.type);
        number_of_lines := number_of_lines + 1;
    END LOOP;
    return number_of_lines;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION is_node_inside_building(geometry(Point,4326))
RETURNS bigint[] AS $$
DECLARE
    node_geom geometry(Point,4326);
    relation_id bigint;
    building_id bigint;
    building_tags hstore;
    return_tuple bigint[];
    allowed_tags text;
    row record;
BEGIN
    node_geom := $1;
    relation_id := 0;
    building_id := 0;
    return_tuple := '{ 0, 0}';
    --allowed_tags := "(tags->'building' != ''
    --        or tags->'amenity' != '' or tags->'shop' != '' or tags->'tourism' != ''
    --        or tags->'leisure' != '' or tags->'public_transport' = 'station'
    --        or tags->'railway' = 'station' or tags->'railway' = 'halt')";
    -- for all buildings, check, if the node geom lays inside the building bbox
    --FOR row IN select id, tags from ways where ST_IsClosed(linestring) AND st_contains(bbox, node_geom) = true
    --    ORDER BY bbox <-> node_geom LIMIT 3
    --LOOP
    --    if row.tags->'highway' != '' THEN
    --        CONTINUE;
    --    END IF;
    --    building_id := row.id;
    --    building_tags := row.tags;
    --    EXIT;
    --END LOOP;
    --if building_id = 0 THEN
    --    return return_tuple;
    --END IF;
    BEGIN
        SELECT id, tags INTO STRICT building_id, building_tags FROM tmp_outer_buildings
        where ST_IsClosed(linestring) AND st_contains(bbox, node_geom) = true
        ORDER BY bbox <-> node_geom LIMIT 1;
        EXCEPTION
        WHEN NO_DATA_FOUND THEN
            return return_tuple;
        WHEN TOO_MANY_ROWS THEN
            return return_tuple;
    END;
    BEGIN
        SELECT rm.relation_id INTO STRICT relation_id
        from relations rs JOIN relation_members rm on rs.id = rm.relation_id
        where rs.tags->'building' != '' AND rm.member_id = building_id AND rm.member_role = 'outer'
        LIMIT 1;
        EXCEPTION
        WHEN NO_DATA_FOUND THEN
            relation_id := 0;
        WHEN TOO_MANY_ROWS THEN
            relation_id := 0;
    END;
    IF relation_id > 0 OR building_tags->'building' != '' THEN
        return_tuple := '{}';
        return_tuple := array_append( return_tuple, relation_id);
        return_tuple := array_append( return_tuple, building_id);
    END IF;
    return return_tuple;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_number_of_entrances(bigint, bigint, bigint, hstore, geometry(Point,4326))
RETURNS int AS $$
DECLARE
    poi_id bigint;
    poi_tags hstore;
    poi_geom geometry(Point,4326);
    b_id bigint;
    r_id bigint;
    number_of_entrances int;
    row RECORD;
    is_subway bool;
    distance int;
    node_array bigint[];
BEGIN
    poi_id := $1;
    r_id := $2;
    b_id := $3;
    poi_tags := $4;
    poi_geom := $5;
    number_of_entrances := 0;
    -- first, collect subway entrances
    -- check if station has a subway
    is_subway := false;
    IF poi_tags->'railway' = 'halt' AND poi_tags->'subway' = 'yes' THEN
        is_subway := true;
    ELSIF poi_tags->'railway' = 'station' AND poi_tags->'subway' = 'yes' THEN
        is_subway := true;
    ELSIF poi_tags->'public_transport' = 'stop_position' AND poi_tags->'subway' = 'yes' THEN
        is_subway := true;
    END IF;
    -- if so...
    if is_subway THEN
        FOR row in SELECT id, tags, geom FROM tmp_subway_entrances ORDER BY poi_geom <-> geom LIMIT 10
        LOOP
            SELECT round(ST_DISTANCE(row.geom::geography, poi_geom::geography)) INTO distance
                FROM tmp_subway_entrances WHERE id = row.id;
            IF distance < 120 THEN
                INSERT INTO entrances VALUES( poi_id, row.id, 2, 'subway_entrance', row.tags, row.geom);
                number_of_entrances := number_of_entrances + 1;
            END IF;
        END LOOP;
    END IF;
    -- entrances of relation, if given
    IF r_id > 0 THEN
        for row IN SELECT n.id, n.tags, n.geom from relation_members rm JOIN tmp_building_entrances n ON rm.member_id = n.id
            where rm.relation_id = r_id and rm.member_role = 'entrance'
        LOOP
            IF row.tags->'entrance' = 'main' THEN
                INSERT INTO entrances VALUES( poi_id, row.id, 1, 'main', row.tags, row.geom);
                number_of_entrances := number_of_entrances + 1;
            ELSIF row.tags->'entrance' = 'yes' THEN
                INSERT INTO entrances VALUES( poi_id, row.id, 3, 'entrance', row.tags, row.geom);
                number_of_entrances := number_of_entrances + 1;
            ELSIF row.tags->'building' = 'entrance' THEN
                INSERT INTO entrances VALUES( poi_id, row.id, 3, 'entrance', row.tags, row.geom);
                number_of_entrances := number_of_entrances + 1;
            ELSIF row.tags->'entrance' = 'emergency' THEN
                INSERT INTO entrances VALUES( poi_id, row.id, 4, 'emergency', row.tags, row.geom);
                number_of_entrances := number_of_entrances + 1;
            ELSIF row.tags->'entrance' != '' THEN
                INSERT INTO entrances VALUES( poi_id, row.id, 5, row.tags->'entrance', row.tags, row.geom);
                number_of_entrances := number_of_entrances + 1;
            END IF;
        END LOOP;
    END IF;
    -- building entrances
    IF b_id > 0 THEN
        SELECT nodes INTO node_array FROM tmp_outer_buildings WHERE id = b_id;
        IF node_array IS NOT NULL THEN
            FOR i IN array_lower(node_array, 1) .. array_upper(node_array, 1)
            LOOP
                SELECT id, tags, geom INTO row FROM tmp_building_entrances WHERE id = node_array[i];
                IF row.tags->'entrance' = 'main' THEN
                    INSERT INTO entrances VALUES( poi_id, row.id, 1, 'main', row.tags, row.geom);
                    number_of_entrances := number_of_entrances + 1;
                ELSIF row.tags->'entrance' = 'yes' THEN
                    INSERT INTO entrances VALUES( poi_id, row.id, 3, 'entrance', row.tags, row.geom);
                    number_of_entrances := number_of_entrances + 1;
                ELSIF row.tags->'building' = 'entrance' THEN
                    INSERT INTO entrances VALUES( poi_id, row.id, 3, 'entrance', row.tags, row.geom);
                    number_of_entrances := number_of_entrances + 1;
                ELSIF row.tags->'entrance' = 'emergency' THEN
                    INSERT INTO entrances VALUES( poi_id, row.id, 4, 'emergency', row.tags, row.geom);
                    number_of_entrances := number_of_entrances + 1;
                ELSIF row.tags->'entrance' != '' THEN
                    INSERT INTO entrances VALUES( poi_id, row.id, 5, row.tags->'entrance', row.tags, row.geom);
                    number_of_entrances := number_of_entrances + 1;
                END IF;
            END LOOP;
        END IF;
    END IF;
    return number_of_entrances;
END;
$$ LANGUAGE plpgsql;


-- print start time
DO $$
DECLARE
BEGIN
    RAISE WARNING 'Started at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;

-- create tables
-- poi node table
DROP TABLE IF EXISTS poi;
CREATE TABLE poi (
    id bigint NOT NULL,
    osm_id bigint,
    osm_type character(1),
    tags hstore,
    outer_building_id bigint NOT NULL,
    number_of_entrances   int,
    geom geometry(Point,4326)
);

DROP TABLE IF EXISTS stations;
CREATE TABLE stations (
    id bigint NOT NULL,
    osm_id bigint,
    osm_type character(1),
    tags hstore,
    outer_building_id bigint NOT NULL,
    number_of_entrances   int,
    number_of_lines   int,
    geom geometry(Point,4326)
);

DROP TABLE IF EXISTS entrances;
CREATE TABLE entrances(
    poi_id bigint,
    entrance_id bigint,
    class int,
    label text,
    tags hstore,
    geom geometry(Point,4326)
);

DROP TABLE IF EXISTS outer_buildings;
CREATE TABLE outer_buildings(
    id bigint,
    relation_id bigint,
    building_id bigint,
    tags hstore,
    geom geometry(Point,4326)
);
ALTER TABLE ONLY outer_buildings ADD CONSTRAINT pk_outer_buildings PRIMARY KEY (id);
CREATE INDEX idx_outer_buildings_relation_id ON outer_buildings(relation_id);
CREATE INDEX idx_outer_buildings_building_id ON outer_buildings(building_id);

DROP TABLE IF EXISTS transport_lines;
CREATE TABLE transport_lines(
    poi_id bigint,
    relation_id bigint,
    line text,
    direction text,
    type text
);

-- load temp tables
CREATE TEMP TABLE tmp_subway_entrances AS SELECT * FROM nodes LIMIT 0;
\copy tmp_subway_entrances FROM 'subway_entrances.txt'
ALTER TABLE ONLY tmp_subway_entrances ADD CONSTRAINT pk_tmp_subway_entrances PRIMARY KEY (id);
CREATE INDEX idx_tmp_subway_entrances_geom ON tmp_subway_entrances USING gist (geom);
CLUSTER tmp_subway_entrances USING idx_tmp_subway_entrances_geom;
ANALYSE tmp_subway_entrances;

CREATE TEMP TABLE tmp_building_entrances AS SELECT * FROM nodes LIMIT 0;
\copy tmp_building_entrances FROM 'building_entrances.txt'
ALTER TABLE ONLY tmp_building_entrances ADD CONSTRAINT pk_tmp_building_entrances PRIMARY KEY (id);
CREATE INDEX idx_tmp_building_entrances_geom ON tmp_building_entrances USING gist (geom);
CLUSTER tmp_building_entrances USING idx_tmp_building_entrances_geom;
ANALYSE tmp_building_entrances;

CREATE TEMP TABLE tmp_outer_buildings AS SELECT * FROM ways LIMIT 0;
\copy tmp_outer_buildings FROM 'outer_buildings.txt'
ALTER TABLE ONLY tmp_outer_buildings ADD CONSTRAINT pk_tmp_outer_buildings PRIMARY KEY (id);
CREATE INDEX idx_tmp_outer_buildings_bbox ON tmp_outer_buildings USING gist (bbox);
CLUSTER tmp_outer_buildings USING idx_tmp_outer_buildings_bbox;
ANALYSE tmp_outer_buildings;

DO $$
DECLARE
BEGIN
    RAISE WARNING 'Temp tables loaded at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;


-- main part
-- node poi
CREATE TEMP TABLE tmp_poi_nodes AS SELECT * FROM nodes LIMIT 0;
\copy tmp_poi_nodes FROM 'poi_nodes.txt'
ALTER TABLE ONLY tmp_poi_nodes ADD CONSTRAINT pk_tmp_poi_nodes PRIMARY KEY (id);
CREATE INDEX idx_tmp_poi_nodes_geom ON tmp_poi_nodes USING gist (geom);
CLUSTER tmp_poi_nodes USING idx_tmp_poi_nodes_geom;
ANALYSE tmp_poi_nodes;

DO $$
DECLARE
BEGIN
    RAISE WARNING 'node temp table loaded at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;

DO $$
DECLARE
    unique_poi_id bigint;
    unique_outer_building_id bigint;
    row RECORD;
    result bool;
    tmp_bigint_value bigint;
    relation_ids bigint[];
    building_tags hstore;
    building_center_geom geometry(Point,4326);
    building_id_to_insert bigint;
    number_of_entrances_to_insert int;
    number_of_lines_to_insert int;

    start_time timestamptz;
    end_time timestamptz;
    start_outer timestamptz;
    end_outer timestamptz;
    start_tmp timestamptz;
    end_tmp timestamptz;
    start_entrance timestamptz;
    end_entrance timestamptz;
    start_insert_poi timestamptz;
    end_insert_poi timestamptz;
    delta_outer double precision;
    delta_frel double precision;
    delta_fbuil double precision;
    delta_check double precision;
    delta_insert double precision;
    delta_entrance double precision;
    delta_entcheck1 double precision;
    delta_entcheck2 double precision;
    delta_entrel double precision;
    delta_entbui double precision;
    delta_insert_poi double precision;
BEGIN
    unique_poi_id := 1;
    unique_outer_building_id := 1;
    delta_outer := 0.0;
    delta_frel := 0.0;
    delta_fbuil := 0.0;
    delta_check := 0.0;
    delta_insert := 0.0;
    delta_entrance := 0.0;
    delta_entcheck1 := 0.0;
    delta_entcheck2 := 0.0;
    delta_entrel := 0.0;
    delta_entbui := 0.0;
    delta_insert_poi := 0.0;
    start_time := clock_timestamp();
    FOR row IN SELECT id, tags, geom from tmp_poi_nodes
    LOOP
        IF (unique_poi_id % 500000) = 0 THEN
            RAISE WARNING '% nodes processed at %', unique_poi_id, to_char(clock_timestamp(), 'HH24:MI:SS');
            raise warning 'outer building frel: %', delta_frel;
            raise warning 'outer building check: %', delta_check;
            raise warning 'outer building insert: %', delta_insert;
            raise warning 'outer building gesamt: %', delta_outer;
            --raise warning 'entrances check 1: %', delta_entcheck1;
            --raise warning 'entrances function relations: %', delta_entrel;
            --raise warning 'entrances check 2: %', delta_entcheck2;
            --raise warning 'entrances function buildings: %', delta_entbui;
            raise warning 'entrances: %', delta_entrance;
            raise warning 'insert poi: %', delta_insert_poi;
            raise warning 'gesamt: %', ( extract(epoch from clock_timestamp()) - extract(epoch from start_time) );
            raise warning '----------';
        END IF;
        -- try to find building or relation for node
        start_outer := clock_timestamp();
        building_id_to_insert := 0;
        IF row.tags ? 'highway' THEN
            relation_ids := '{ 0, 0}';
        ELSE
            start_tmp := clock_timestamp();
            SELECT is_node_inside_building(row.geom) INTO relation_ids;
            end_tmp := clock_timestamp();
            delta_frel := delta_frel + ( extract(epoch from end_tmp) - extract(epoch from start_tmp) );
        END IF;
        IF relation_ids[2] > 0 THEN
            start_tmp := clock_timestamp();
            SELECT id INTO building_id_to_insert from outer_buildings where building_id = relation_ids[2];
            end_tmp := clock_timestamp();
            delta_check := delta_check + ( extract(epoch from end_tmp) - extract(epoch from start_tmp) );
            IF building_id_to_insert IS NULL THEN
                -- get tags from relation and center from building
                start_tmp := clock_timestamp();
                IF relation_ids[1] > 0 THEN
                    SELECT tags INTO building_tags FROM relations WHERE id = relation_ids[1];
                ELSE
                    SELECT tags INTO building_tags FROM tmp_outer_buildings WHERE id = relation_ids[2];
                END IF;
                SELECT ST_Centroid(bbox) INTO building_center_geom FROM tmp_outer_buildings where id = relation_ids[2];
                building_id_to_insert := unique_outer_building_id;
                unique_outer_building_id := unique_outer_building_id + 1;
                INSERT INTO outer_buildings VALUES( building_id_to_insert, relation_ids[1],
                    relation_ids[2], building_tags, building_center_geom);
                end_tmp := clock_timestamp();
                delta_insert := delta_insert + ( extract(epoch from end_tmp) - extract(epoch from start_tmp) );
            END IF;
        END IF;
        end_outer := clock_timestamp();
        delta_outer := delta_outer + ( extract(epoch from end_outer) - extract(epoch from start_outer) );

        -- get entrances if we found a building
        start_entrance := clock_timestamp();
        SELECT get_number_of_entrances(unique_poi_id, relation_ids[1], relation_ids[2], row.tags, row.geom) INTO number_of_entrances_to_insert;
        end_entrance := clock_timestamp();
        delta_entrance := delta_entrance + ( extract(epoch from end_entrance) - extract(epoch from start_entrance) );

        -- decide if poi is a station
        start_insert_poi := clock_timestamp();
        SELECT is_station(row.tags) INTO result;
        IF result THEN
            -- transport lines
            SELECT get_number_of_public_transport_lines_at_station(unique_poi_id, row.id) INTO number_of_lines_to_insert;
            -- insert into stations table
            INSERT INTO stations VALUES( unique_poi_id, row.id, 'N', row.tags, building_id_to_insert,
                number_of_entrances_to_insert, number_of_lines_to_insert, row.geom);
        ELSE
            -- insert into poi table
            INSERT INTO poi VALUES( unique_poi_id, row.id, 'N', row.tags, building_id_to_insert,
                number_of_entrances_to_insert, row.geom);
        END IF;
        unique_poi_id := unique_poi_id + 1;
        end_insert_poi := clock_timestamp();
        delta_insert_poi := delta_insert_poi + ( extract(epoch from end_insert_poi) - extract(epoch from start_insert_poi) );
    END LOOP;
    end_time := clock_timestamp();
    raise warning 'outer building frel: %', delta_frel;
    raise warning 'outer building check: %', delta_check;
    raise warning 'outer building insert: %', delta_insert;
    raise warning 'outer building gesamt: %', delta_outer;
    raise warning 'entrances: %', delta_entrance;
    raise warning 'insert poi: %', delta_insert_poi;
    raise warning 'gesamt: %', ( extract(epoch from end_time) - extract(epoch from start_time) );
END $$;

DO $$
DECLARE
BEGIN
    RAISE WARNING 'nodes loaded at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;


-- ways poi
CREATE TEMP TABLE tmp_poi_ways AS SELECT * FROM ways LIMIT 0;
\copy tmp_poi_ways FROM 'poi_ways.txt'
ALTER TABLE ONLY tmp_poi_ways ADD CONSTRAINT pk_tmp_poi_ways PRIMARY KEY (id);
CREATE INDEX idx_tmp_poi_ways_bbox ON tmp_poi_ways USING gist (bbox);
CLUSTER tmp_poi_ways USING idx_tmp_poi_ways_bbox;
ANALYSE tmp_poi_ways;

DO $$
DECLARE
    unique_poi_id bigint;
    row RECORD;
    result bool;
    tmp_bigint_value bigint;
    number_of_entrances_to_insert int;
    number_of_lines_to_insert int;
BEGIN
    SELECT id INTO unique_poi_id from poi ORDER BY id DESC limit 1;
    SELECT id INTO tmp_bigint_value from stations ORDER BY id DESC limit 1;
    IF tmp_bigint_value > unique_poi_id THEN
        unique_poi_id := tmp_bigint_value + 1;
    ELSE
        unique_poi_id := unique_poi_id + 1;
    END IF;
    FOR row IN SELECT id, tags, ST_Centroid(bbox) AS geom from tmp_poi_ways
        WHERE GeometryType(ST_Centroid(bbox)) = 'POINT'
    LOOP
        SELECT get_number_of_entrances(unique_poi_id, 0, row.id, row.tags, row.geom) INTO number_of_entrances_to_insert;
        -- decide if poi is a station
        SELECT is_station(row.tags) INTO result;
        IF result THEN
            SELECT get_number_of_public_transport_lines_at_station(unique_poi_id, row.id) INTO number_of_lines_to_insert;
            -- insert into stations table
            INSERT INTO stations VALUES( unique_poi_id, row.id, 'W', row.tags, 0,
                number_of_entrances_to_insert, number_of_lines_to_insert, row.geom);
        ELSE
            INSERT INTO poi VALUES( unique_poi_id, row.id, 'W', row.tags, 0,
                number_of_entrances_to_insert, row.geom);
        END IF;
        unique_poi_id := unique_poi_id + 1;
    END LOOP;
END $$;

DO $$
DECLARE
BEGIN
    RAISE WARNING 'ways loaded at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;

-- poi relations
CREATE TEMP TABLE tmp_poi_relations AS SELECT * FROM relations LIMIT 0;
\copy tmp_poi_relations FROM 'poi_relations.txt'
ALTER TABLE ONLY tmp_poi_relations ADD CONSTRAINT pk_tmp_poi_relations PRIMARY KEY (id);
ANALYSE tmp_poi_relations;

DO $$
DECLARE
    unique_poi_id bigint;
    row RECORD;
    result bool;
    tmp_bigint_value bigint;
    number_of_entrances_to_insert int;
    number_of_lines_to_insert int;
BEGIN
    number_of_lines_to_insert := 0;
    SELECT id INTO unique_poi_id from poi ORDER BY id DESC limit 1;
    SELECT id INTO tmp_bigint_value from stations ORDER BY id DESC limit 1;
    IF tmp_bigint_value > unique_poi_id THEN
        unique_poi_id := tmp_bigint_value + 1;
    ELSE
        unique_poi_id := unique_poi_id + 1;
    END IF;
    -- first try to find a boundary of one of the dedicated relation members
    -- mostly the outer boundary of a building
    -- if it exists, take the centroid of the poligon
    FOR row IN SELECT rs.id AS relation_id, w.id AS building_id, rs.tags, ST_Centroid(w.bbox) AS geom
        from tmp_poi_relations rs JOIN relation_members rm ON rs.id = rm.relation_id JOIN ways w ON rm.member_id = w.id
        where rm.member_role = 'outer' AND GeometryType(ST_Centroid(w.bbox)) = 'POINT'
    LOOP
        -- entrances of building
        SELECT get_number_of_entrances(unique_poi_id, row.relation_id, row.building_id, row.tags, row.geom) INTO number_of_entrances_to_insert;
        -- decide if poi is a station
        SELECT is_station(row.tags) INTO result;
        IF result THEN
            INSERT INTO stations VALUES( unique_poi_id, row.relation_id, 'R', row.tags, 0,
                number_of_entrances_to_insert, number_of_lines_to_insert, row.geom);
        ELSE
            INSERT INTO poi VALUES( unique_poi_id, row.relation_id, 'R', row.tags, 0,
                number_of_entrances_to_insert, row.geom);
        END IF;
        unique_poi_id := unique_poi_id + 1;
    END LOOP;
END $$;

DO $$
DECLARE
BEGIN
    RAISE WARNING 'relations loaded at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;


-- post processing
-- add index
-- poi table
ALTER TABLE ONLY poi ADD CONSTRAINT pk_poi PRIMARY KEY (id);
CREATE INDEX idx_poi_geom ON poi USING gist (geom);
CLUSTER poi USING idx_poi_geom;

-- stations
ALTER TABLE ONLY stations ADD CONSTRAINT pk_stations PRIMARY KEY (id);
CREATE INDEX idx_stations_geom ON stations USING gist (geom);
CLUSTER stations USING idx_stations_geom;

-- entrance table
DELETE FROM entrances USING entrances entr2
    where entrances.poi_id = entr2.poi_id and entrances.entrance_id = entr2.entrance_id
        AND entrances.class > entr2.class;
CREATE TABLE entrances_unique AS SELECT * FROM entrances LIMIT 0;
INSERT INTO entrances_unique SELECT DISTINCT * FROM entrances;
DROP TABLE entrances;
ALTER TABLE entrances_unique RENAME TO entrances;
ALTER TABLE ONLY entrances ADD CONSTRAINT pk_entrances PRIMARY KEY (poi_id, entrance_id);
CREATE INDEX idx_entrances_geom ON entrances USING gist (geom);
CLUSTER entrances USING idx_entrances_geom;

-- transport_lines table
CREATE TABLE transport_lines_unique AS SELECT * FROM transport_lines LIMIT 0;
INSERT INTO transport_lines_unique SELECT DISTINCT * FROM transport_lines;
DROP TABLE transport_lines;
ALTER TABLE transport_lines_unique RENAME TO transport_lines;
ALTER TABLE ONLY transport_lines ADD CONSTRAINT pk_transport_lines PRIMARY KEY (poi_id, relation_id);

-- outer buildings
CREATE INDEX idx_outer_buildings ON outer_buildings USING gist (geom);
CLUSTER outer_buildings USING idx_outer_buildings;

-- print finish time
DO $$
DECLARE
BEGIN
    RAISE WARNING 'Ready at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;
