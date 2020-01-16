CREATE OR REPLACE FUNCTION get_size_of_databases()
RETURNS void
AS $$
DECLARE
    row RECORD;
BEGIN
    FOR row in SELECT d.datname AS Name,  pg_catalog.pg_get_userbyid(d.datdba) AS Owner,
        CASE WHEN pg_catalog.has_database_privilege(d.datname, 'CONNECT')
            THEN pg_catalog.pg_size_pretty(pg_catalog.pg_database_size(d.datname))
            ELSE 'No Access'
        END AS Size
    FROM pg_catalog.pg_database d
        ORDER BY
        CASE WHEN pg_catalog.has_database_privilege(d.datname, 'CONNECT')
            THEN pg_catalog.pg_database_size(d.datname)
            ELSE NULL
        END DESC -- nulls first
        LIMIT 20
    LOOP
        RAISE NOTICE '%', row;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recreate_vertex_of_routing_table(regclass)
RETURNS void
AS $$
DECLARE
    row RECORD;
    vertex_storage hstore;
    new_vertex int;
BEGIN
    vertex_storage := ''::hstore;
    new_vertex := -1;
    FOR row in EXECUTE FORMAT('SELECT id, source, target FROM %I ORDER BY id', $1)
    LOOP
        IF NOT vertex_storage ? row.source::text THEN
            vertex_storage = vertex_storage || hstore(row.source::text, new_vertex::text);
            new_vertex := new_vertex - 1;
        END IF;
        IF NOT vertex_storage ? row.target::text THEN
            vertex_storage = vertex_storage || hstore(row.target::text, new_vertex::text);
            new_vertex := new_vertex - 1;
        END IF;
    END LOOP;
    -- remap
    FOR row IN SELECT key, value FROM EACH(vertex_storage)
    LOOP
        EXECUTE FORMAT('UPDATE %I SET source=$1 WHERE source = $2', $1) USING row.value::int, row.key::int;
        EXECUTE FORMAT('UPDATE %I SET target=$1 WHERE target = $2', $1) USING row.value::int, row.key::int;
    END LOOP;
    -- invert sign of source and target columns
    EXECUTE FORMAT('UPDATE %I SET source=source*(-1)', $1);
    EXECUTE FORMAT('UPDATE %I SET target=target*(-1)', $1);
END;
$$ LANGUAGE plpgsql;
