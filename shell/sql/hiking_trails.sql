SET client_min_messages TO WARNING;

-- create hiking trail table
DROP TABLE IF EXISTS hiking_trails;
CREATE TABLE hiking_trails(
    relation_id bigint,
    tags hstore,
    geom geometry(LineString,4326));

-- insert hiking trails
INSERT INTO hiking_trails (relation_id, tags, geom)
    SELECT
            r.id AS relation_id,
            r.tags AS tags,
            (
                SELECT ST_MakeLine(
                    array(
                        SELECT w.linestring
                            FROM relation_members  rm JOIN ways w ON rm.member_id = w.id
                            WHERE rm.relation_id = r.id AND rm.member_type = 'W'
                            ORDER BY rm.sequence_id)
                    )
                ) AS geom
        FROM relations r
        WHERE tags->'route' = ANY('{"foot", "hiking"}');

-- cleanup
DELETE FROM hiking_trails  where geom IS NULL;

-- add primary key and index
ALTER TABLE ONLY hiking_trails ADD CONSTRAINT pk_hiking_trails PRIMARY KEY (relation_id);
CREATE INDEX idx_hiking_trails_geom ON hiking_trails USING gist (geom);
CLUSTER hiking_trails USING idx_hiking_trails_geom;
ANALYSE hiking_trails;
