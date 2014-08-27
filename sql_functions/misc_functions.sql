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
