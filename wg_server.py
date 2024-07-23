#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse, datetime, logging, time
import os, sys
from subprocess import Popen, STDOUT

import webserver.statistics as statistics
import webserver.webserver as webserver
from webserver.config import Config
from webserver.db_control import DBControl
from webserver.constants import server_version, supported_api_version_list, supported_map_version_list
from webserver.helper import exit, pretty_print_table, send_email


def list_map_ids():
    return ', '.join(list(Config().maps.keys()))


def create_map_database(map_id):
    map = Config().maps.get(map_id)

    # check for running map creation process
    if os.path.exists(Config().paths.get("shell_lock_file")):
        exit("Already running map creation process found.", prefix="Map Creation failed\n")
    # create lock file
    with open(Config().paths.get("shell_lock_file"), "w") as lock_file:
        lock_file.write("Creation of map %s in progress" % map_id)

    # create configuration file for the shell script
    shell_config = []
    shell_config += ['# specify folders']
    shell_config += ['sql_files_folder="%s"' % Config().paths.get("sql_files_folder")]
    shell_config += ['temp_folder="%s"' % Config().paths.get("temp_folder")]
    shell_config += ['maps_temp_subfolder="$temp_folder/maps"' ]
    shell_config += ['osm_data_temp_subfolder="$temp_folder/osm_data"' ]
    shell_config += ['poi_temp_subfolder="$temp_folder/poi"' ]
    # osm2po
    shell_config += ['\n# osm2po']
    shell_config += ['osm2po_executable="%s"' % Config().java.get("osm2po_executable")]
    shell_config += ['osm2po_config="%s"' % Config().java.get("osm2po_config")]
    # database connection
    shell_config += ['\n# database connection']
    shell_config += ['export PGHOST="%s"' % Config().database.get("host_name")]
    shell_config += ['export PGPORT=%d' % Config().database.get("port")]
    shell_config += ['export PGUSER="%s"' % Config().database.get("user")]
    shell_config += ['export PGPASSWORD="%s"' % Config().database.get("password")]
    # database settings
    shell_config += ['\n# database settings']
    shell_config += ['db_active_name="%s"' % map_id]
    shell_config += ['db_tmp_name="%s_tmp"' % map_id]
    shell_config += ['db_owner="%s"' % Config().database.get("user")]
    shell_config += ['db_prefix="%s"' % Config().database.get("routing_prefix")]
    shell_config += ['db_routing_table="%s"' % Config().database.get("routing_table")]
    shell_config += ['db_access_statistics_table="%s"' % Config().database.get("access_statistics_table")]
    shell_config += ['db_map_info="%s"' % Config().database.get("map_info")]
    shell_config += ['db_map_version=%s' % supported_map_version_list[-1]]
    # Java options
    shell_config += ['\n# Java options']
    shell_config += ['osm2po_ram_param="-Xmx%dg"' % Config().java.get("ram_in_gb")]
    shell_config += ['export JAVACMD_OPTIONS="-server -Xmx%dG -Djava.io.tmpdir=%s"' \
            % (Config().java.get("ram_in_gb"), Config().paths.get("temp_folder")) ]
    # map settings
    shell_config += ['\n# maps']
    shell_config += ['download_map_urls=("%s")' % '" "'.join(map.get("urls"))]
    shell_config += ['pbf_osm_file="$maps_temp_subfolder/map.osm.pbf"']
    shell_config += ['o5m_osm_file="$maps_temp_subfolder/map.o5m"']
    # write shell configuration script
    with open(Config().paths.get("shell_config"), "w") as f:
        f.write('\n'.join(shell_config))

    # create map database
    # log file
    date = datetime.datetime.now()
    log_file = os.path.join(
            Config().paths.get("maps_log_folder"),
            "%04d-%02d-%02d_%02d-%02d-%02d.create.%s.log" % (date.year,
                date.month, date.day, date.hour, date.minute, date.second, map_id))
    # start map creation shell script
    with open(log_file,"wb") as out:
        map_creation_process= Popen(
                [Config().paths.get("shell_create_map_database")], stdout=out, stderr=STDOUT)
    return_code = map_creation_process.wait()
    # send email
    # subject
    if return_code != 0:
        email_subject = "%s: Creation of complete  OSM database failed" % map_id
    else:
        email_subject = "%s: Creation of complete  OSM database successful" % map_id
    # body
    with open(log_file, "r") as lf:
        email_body = lf.read()
    send_email(email_subject, email_body)
    os.remove(Config().paths.get("shell_lock_file"))


def start_webserver():
    webserver.start()


def show_statistics():
    access_statistics = dict()
    for map_id, map_data in Config().maps.items():
        try:
            access_statistics[map_data['name']] = \
                    statistics.get_access_statistics(DBControl(map_id))
        except Exception as e:
            logging.error(
                    "Failed to get access statistics for map {}\nError: {}".format(map_id, e))
            sys.exit(1)

    table = list()
    # header
    table.append(
            ["map", "last 30 days", "last six months", "last year", "total"])
    # body
    current_timestamp = int(time.time())
    for map_name, timestamp_list in access_statistics.items():
        last_thirty_days = last_six_months = last_year = 0
        for timestamp in timestamp_list:
            if current_timestamp - timestamp < 30*24*60*60:
                last_thirty_days += 1
            if current_timestamp - timestamp < 182*24*60*60:
                last_six_months += 1
            if current_timestamp - timestamp < 365*24*60*60:
                last_year += 1
        total = len(timestamp_list)
        # add
        table.append(
                [map_name, last_thirty_days, last_six_months, last_year, total])
    print(pretty_print_table(table))


def print_version_info():
    return "WalkersGuide-Server version: %s     (API versions: %s;   Map versions: %s)" \
            % (server_version, ','.join([str(x) for x in supported_api_version_list]),
                    ','.join([str(x) for x in supported_map_version_list]))


def main():
    # load config
    Config()
    # create cli parser
    parser = argparse.ArgumentParser(description="WalkersGuide-Server")
    parser.add_argument("-v", "--version", action="version", version=print_version_info())

    subparsers = parser.add_subparsers(dest="action")
    create_database_aliases = ['create', 'cmd']
    create_database = subparsers.add_parser(
            "create-map-database", aliases=create_database_aliases,
            description="Start a script to create a new map database thats already in the config file",
            help="Start a script to create a new map database thats already in the config file")
    create_database.add_argument(
            '--all', action='store_true', help='Create all databases listed in the config file')
    create_database.add_argument(
            'map_ids', nargs='*', help='The map id from config')
    # list maps
    list_databases_aliases = ['list', 'lmd', 'ls']
    subparsers.add_parser(
            "list-map-databases", aliases=list_databases_aliases,
            description="List map ids from config file",
            help="List map ids from config file")
    # start webserver
    start_webserver_aliases = ['start']
    subparsers.add_parser(
            "start-webserver", aliases=start_webserver_aliases,
            description="Start webserver for client communication",
            help="Start webserver for client communication")
    # statistics
    statistics_aliases = ['stats']
    subparsers.add_parser(
            "statistics", aliases=statistics_aliases,
            description="Show usage statistics",
            help="Show usage statistics")
    args = parser.parse_args()

    if args.action == "create-map-database" \
            or args.action in create_database_aliases:
        if not args.map_ids:
            if args.all:
                args.map_ids = list(Config().maps.keys())
            else:
                exit("No map ids given.\nAvailable maps: {}".format(
                        list_map_ids()), prefix="Map Creation failed\n")
        for map_id in args.map_ids:
            if map_id not in Config().maps.keys():
                exit("Map id {} not found in config file.\nAvailable maps: {}".format(
                        map_id, list_map_ids()), prefix="Map Creation failed\n")
        # create maps
        for map_id in args.map_ids:
            create_map_database(map_id)

    elif args.action == "list-map-databases" \
            or args.action in list_databases_aliases:
        print(list_map_ids())
    elif args.action == "start-webserver" \
            or args.action in start_webserver_aliases:
        start_webserver()
    elif args.action == "statistics" \
            or args.action in statistics_aliases:
        show_statistics()


if __name__ == '__main__':
    main()
