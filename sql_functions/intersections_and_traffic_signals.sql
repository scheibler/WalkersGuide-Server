SET client_min_messages TO WARNING;

-- create intersection tables
DROP TABLE IF EXISTS intersection_data;
CREATE TABLE intersection_data(
    id bigint,
    way_id bigint,
    node_id bigint,
    direction character(1),
    way_tags hstore,
    node_tags hstore,
    geom geometry(Point,4326)
);

DROP TABLE IF EXISTS intersections;
CREATE TABLE intersections(
    id bigint,
    name text,
    number_of_streets int,
    number_of_streets_with_name int,
    number_of_traffic_signals int,
    tags hstore,
    geom geometry(Point,4326)
);

-- create temp table for potential intersections
CREATE TEMP TABLE tmp_intersection_data AS SELECT * FROM intersection_data LIMIT 0;
CREATE TEMP TABLE tmp_intersection_data_unique AS SELECT * FROM intersection_data LIMIT 0;

-- create temp table with all streets
CREATE TEMP TABLE tmp_highway_railway AS SELECT * FROM ways LIMIT 0;
INSERT INTO tmp_highway_railway SELECT * FROM ways where tags->'highway' != '' or tags->'railway' != '';
ALTER TABLE ONLY tmp_highway_railway ADD CONSTRAINT pk_tmp_highway_railway PRIMARY KEY (id);
CREATE INDEX idx_tmp_highway_railway_linestring ON tmp_highway_railway USING gist (linestring);
CLUSTER tmp_highway_railway USING idx_tmp_highway_railway_linestring;
ANALYSE tmp_highway_railway;

-- create temp node table
CREATE TEMP TABLE tmp_nodes AS SELECT * FROM nodes LIMIT 0;

DO $$
DECLARE
    street_names text[];
    street_types text[];
    intersection_name text;
    number_of_streets int;
    number_of_intersections int;
    number_of_tmp_table_rows int;
    number_of_streets_with_name int;
    last_intersection_id bigint;
    intersection_tags hstore;
    intersection_geom geometry(Point,4326);
    row RECORD;
    upper_lat real;
    lower_lat real;
    left_lon real;
    right_lon real;
    window_size real;
    start_time timestamptz;
    end_time timestamptz;
    start_tmp timestamptz;
    end_tmp timestamptz;
    delta_check double precision;
    delta_insert double precision;
BEGIN
    window_size := 4.0;
    lower_lat := -90.0;
    upper_lat := -89.995 + window_size;
    WHILE (lower_lat < 90.0)
    LOOP
        RAISE WARNING '   latitude: % to %     (%)', lower_lat, upper_lat, to_char(clock_timestamp(), 'HH24:MI:SS');
        left_lon := -180.0;
        right_lon := -179.995 + window_size;
        WHILE (left_lon < 180.0)
        LOOP
            intersection_tags := '';
            intersection_geom := NULL;
            FOR row IN SELECT id, tags, nodes from tmp_highway_railway
                where linestring && ST_MakeEnvelope(left_lon, lower_lat, right_lon, upper_lat)
            LOOP
                FOR i IN array_lower(row.nodes, 1) .. array_upper(row.nodes, 1)
                LOOP
                    -- if the node in array has a predecessor
                    IF i > array_lower(row.nodes, 1) THEN
                        INSERT INTO tmp_intersection_data VALUES (row.nodes[i], row.id,
                            row.nodes[i-1], 'B', row.tags, intersection_tags, intersection_geom);
                    END IF;
                    -- if the node in array has a successor
                    IF i < array_upper(row.nodes, 1) THEN
                        INSERT INTO tmp_intersection_data VALUES (row.nodes[i], row.id,
                            row.nodes[i+1], 'F', row.tags, intersection_tags, intersection_geom);
                    END IF;
                END LOOP;
            END LOOP;
            -- temp table size
            BEGIN
                SELECT COUNT(*) INTO STRICT number_of_tmp_table_rows FROM tmp_intersection_data;
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN
                        number_of_tmp_table_rows := -1;
                    WHEN TOO_MANY_ROWS THEN
                        number_of_tmp_table_rows := -1;
            END;
            IF number_of_tmp_table_rows < 1 THEN
                left_lon := left_lon + window_size;
                right_lon := right_lon + window_size;
                CONTINUE;
            END IF;
            -- insert a dummy row at the max integer value
            -- otherwise the last intersection is skipped by the following for loop
            INSERT INTO tmp_intersection_data VALUES (9223372036854775807, 0, 0, '', '', '', NULL);
            ANALYSE tmp_intersection_data;
            -- clean duplicate rows
            INSERT INTO tmp_intersection_data_unique SELECT DISTINCT ON (id, way_id, node_id) * FROM tmp_intersection_data;
            ALTER TABLE tmp_intersection_data RENAME TO tmp_intersection_data_tmp;
            ALTER TABLE tmp_intersection_data_unique RENAME TO tmp_intersection_data;
            ALTER TABLE tmp_intersection_data_tmp RENAME TO tmp_intersection_data_unique;
            -- add primary key and index
            ALTER TABLE ONLY tmp_intersection_data ADD CONSTRAINT pk_tmp_intersection_data PRIMARY KEY (id, way_id, node_id);
            CREATE INDEX idx_tmp_intersection_data_id ON tmp_intersection_data USING btree (id);
            CREATE INDEX idx_tmp_intersection_data_node_id ON tmp_intersection_data USING btree (node_id);
            ANALYSE tmp_intersection_data;
            -- fill temp node array
            INSERT INTO tmp_nodes SELECT * FROM nodes
                where geom && ST_MakeEnvelope(left_lon, lower_lat, right_lon, upper_lat);
            ALTER TABLE ONLY tmp_nodes ADD CONSTRAINT pk_tmp_nodes PRIMARY KEY (id);
            ANALYSE tmp_nodes;

            -- walk through the whole tmp_intersection table and process every potential intersection id
            last_intersection_id = -1;
            number_of_streets := 0;
            street_names := '{}';
            street_types := '{}';
            FOR row IN SELECT id, way_id, node_id, way_tags, way_tags->'highway' AS highway, way_tags->'tracktype' AS tracktype
                from tmp_intersection_data order by id
            LOOP
                IF row.id <> last_intersection_id THEN
                    -- if there are more than 2 entries for the given node id, it's a crossing
                    IF number_of_streets > 2 THEN
                        -- filter the duplicated street names
                        SELECT ARRAY(SELECT DISTINCT UNNEST(street_names) a) AS unique_values INTO street_names;
                        IF array_length(street_names, 1) > 0 THEN
                            intersection_name := array_to_string(street_names, ', ') || ', ' || array_to_string(street_types, ', ');
                            number_of_streets_with_name := array_length(street_names, 1);
                        ELSE
                            intersection_name := array_to_string(street_types, ', ');
                            number_of_streets_with_name := 0;
                        END IF;
                        -- get geom for intersection
                        BEGIN
                            SELECT tags, geom INTO STRICT intersection_tags, intersection_geom from tmp_nodes where id = last_intersection_id;
                            EXCEPTION
                                WHEN NO_DATA_FOUND THEN
                                    intersection_tags := '';
                                    intersection_geom := NULL;
                                WHEN TOO_MANY_ROWS THEN
                                    intersection_tags := '';
                                    intersection_geom := NULL;
                        END;
                        INSERT INTO intersections VALUES (last_intersection_id, intersection_name, number_of_streets,
                            number_of_streets_with_name, 0, intersection_tags, intersection_geom);
                        INSERT INTO intersection_data (id, way_id, node_id, direction, way_tags, node_tags, geom)
                            SELECT i.id, i.way_id, i.node_id, i.direction, i.way_tags, n.tags, n.geom
                                from tmp_intersection_data i JOIN tmp_nodes n ON i.node_id = n.id
                                where i.id = last_intersection_id;
                    END IF;
                    last_intersection_id := row.id;
                    number_of_streets := 0;
                    street_names := '{}';
                    street_types := '{}';
                END IF;
                number_of_streets := number_of_streets + 1;
                IF row.way_tags->'name' != '' THEN
                    street_names := array_append(street_names, row.way_tags->'name'::text);
                ELSIF row.way_tags->'highway' != '' THEN
                    IF row.way_tags->'tracktype' != '' THEN
                        street_types := array_append(street_types, row.highway::text
                            || ' (' || row.tracktype::text || ')');
                    ELSE
                        street_types := array_append(street_types, row.way_tags->'highway'::text);
                    END IF;
                ELSE
                    street_types := array_append(street_types, row.way_tags->'railway'::text);
                END IF;
            END LOOP;
            -- clean temp tables
            DROP INDEX idx_tmp_intersection_data_id;
            DROP INDEX idx_tmp_intersection_data_node_id;
            ALTER TABLE tmp_intersection_data DROP CONSTRAINT pk_tmp_intersection_data;
            TRUNCATE TABLE tmp_intersection_data;
            TRUNCATE TABLE tmp_intersection_data_unique;
            ALTER TABLE tmp_nodes DROP CONSTRAINT pk_tmp_nodes;
            TRUNCATE TABLE tmp_nodes;
            left_lon := left_lon + window_size;
            right_lon := right_lon + window_size;
            -- output temp table size
            RAISE WARNING '        size: %    % to %    (%)', number_of_tmp_table_rows, left_lon, right_lon, to_char(clock_timestamp(), 'HH24:MI:SS');
        END LOOP;
        upper_lat := upper_lat + window_size;
        lower_lat := lower_lat + window_size;
    END LOOP;
    RAISE WARNING 'Ready at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;

-- enable timing
\timing

-- filter out duplicates from intersections table
ANALYSE intersections;
DELETE FROM intersections USING intersections it2
        where intersections.id = it2.id and intersections.number_of_streets < it2.number_of_streets;
CREATE TABLE intersections_unique AS SELECT * FROM intersections LIMIT 0;
INSERT INTO intersections_unique SELECT DISTINCT ON (id) * FROM intersections;
DROP TABLE intersections;
ALTER TABLE intersections_unique RENAME TO intersections;

-- filter out duplicates from intersection_data table
ANALYSE intersection_data;
CREATE TABLE intersection_data_unique AS SELECT * FROM intersection_data LIMIT 0;
INSERT INTO intersection_data_unique SELECT DISTINCT ON (id, way_id, node_id) * FROM intersection_data;
DROP TABLE intersection_data;
ALTER TABLE intersection_data_unique RENAME TO intersection_data;

-- add index
ALTER TABLE ONLY intersections ADD CONSTRAINT pk_intersections PRIMARY KEY (id);
CREATE INDEX idx_intersections_geom ON intersections USING gist (geom);
CLUSTER intersections USING idx_intersections_geom;
ANALYSE intersections;

ALTER TABLE ONLY intersection_data ADD CONSTRAINT pk_intersection_data PRIMARY KEY (id, way_id, node_id);
CREATE INDEX idx_intersection_data_intersection_id ON intersection_data USING btree (id);
ANALYSE intersection_data;

-- traffic signals
CREATE TEMP TABLE tmp_traffic_signals AS SELECT * FROM nodes LIMIT 0;
\copy tmp_traffic_signals FROM 'traffic_signals.txt'
ALTER TABLE ONLY tmp_traffic_signals ADD CONSTRAINT pk_tmp_traffic_signals PRIMARY KEY (id);
CREATE INDEX idx_tmp_traffic_signals_geom ON tmp_traffic_signals USING gist (geom);
CLUSTER tmp_traffic_signals USING idx_tmp_traffic_signals_geom;
ANALYSE tmp_traffic_signals;

DROP TABLE IF EXISTS traffic_signals;
CREATE TABLE traffic_signals(
    id bigint NOT NULL,
    crossing_street_name text,
    way_id bigint,
    intersection_id bigint,
    tags hstore,
    geom geometry(Point,4326)
);

do $$
DECLARE
    signals_row record;
    intersection_row record;
    signals_way_id bigint;
    signals_way_name text;
    intersection_near_by int;
    processed_signals int;
BEGIN
    processed_signals := 0;
    FOR signals_row IN SELECT id, tags, geom FROM tmp_traffic_signals
    LOOP
        WITH closest_ways AS (
            SELECT way_id from way_nodes  where node_id = signals_row.id
        )
        SELECT w.id, w.tags->'name' INTO signals_way_id, signals_way_name
            FROM closest_ways cw JOIN ways w ON cw.way_id = w.id
            where tags->'name' != '' LIMIT 1;
        IF signals_way_id IS NULL THEN
            signals_way_id := 0;
        END IF;
        intersection_near_by := 0;
        FOR intersection_row IN
            with closest_intersections as (
                SELECT * from intersections where number_of_streets_with_name > 0
                    ORDER BY geom <-> signals_row.geom LIMIT 10
            )
            SELECT * FROM closest_intersections
                WHERE ST_DISTANCE(geom, signals_row.geom) < 25.0
        LOOP
            intersection_near_by := 1;
            IF intersection_row.number_of_streets_with_name = 1 AND intersection_row.id = signals_row.id THEN
                INSERT INTO traffic_signals VALUES(signals_row.id, signals_way_name,
                    signals_way_id, intersection_row.id, signals_row.tags, signals_row.geom);
            END IF;
            IF intersection_row.number_of_streets_with_name > 1 AND intersection_row.id != signals_row.id THEN
                IF EXISTS(SELECT * FROM intersection_data
                    WHERE id = intersection_row.id AND way_id = signals_way_id) THEN
                    INSERT INTO traffic_signals VALUES(signals_row.id, signals_way_name,
                        signals_way_id, intersection_row.id, signals_row.tags, signals_row.geom);
                END IF;
            END IF;
        END LOOP;
        IF intersection_near_by = 0 THEN
            INSERT INTO traffic_signals VALUES(signals_row.id, signals_way_name,
                signals_way_id, 0, signals_row.tags, signals_row.geom);
        END IF;
        IF (processed_signals % 25000) = 0 THEN
            RAISE WARNING '% traffic signals processed at %', processed_signals, to_char(clock_timestamp(), 'HH24:MI:SS');
        END IF;
        processed_signals := processed_signals + 1;
    END LOOP;
END $$;

ALTER TABLE ONLY traffic_signals ADD CONSTRAINT pk_traffic_signals PRIMARY KEY (id, intersection_id);
CREATE INDEX idx_traffic_signals_intersection_id ON traffic_signals USING btree (intersection_id);
CREATE INDEX idx_traffic_signals_geom ON traffic_signals USING gist (geom);
CLUSTER traffic_signals USING idx_traffic_signals_geom;
ANALYSE traffic_signals;

-- update number_of_traffic_signals column of the intersections table
do $$
DECLARE
    row record;
BEGIN
    FOR row IN SELECT distinct on (intersection_id) count(*) AS number_of_signals, intersection_id
        from traffic_signals  group by intersection_id
    LOOP
        UPDATE intersections SET number_of_traffic_signals = row.number_of_signals
            WHERE id = row.intersection_id;
    END LOOP;
END $$;

DO $$
DECLARE
BEGIN
    RAISE WARNING 'Ready at %', to_char(clock_timestamp(), 'HH24:MI:SS');
END $$;
