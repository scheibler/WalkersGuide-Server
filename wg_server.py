#!/usr/bin/python
# -*- coding: utf-8 -*-


import argparse
import datetime
import os
from subprocess import Popen, STDOUT

import webserver.webserver as webserver
from webserver.config import Config
from webserver.constants import server_version, supported_api_version_list, supported_map_version_list
from webserver.helper import exit, send_email


def create_map_database(map_id):
    # check for running map creation process
    if os.path.exists(Config().paths.get("shell_lock_file")):
        exit("Already running map creation process found.", prefix="Map Creation failed\n")
    with open(Config().paths.get("shell_lock_file"), "w") as lock_file:
        lock_file.write("Creation of map %s in progress" % map_id)
    # load map
    map = Config().maps.get(map_id)
    if not map:
        exit("Map id %s not found in config file" % map_id, prefix="Map Creation failed\n")

    # create configuration file for the shell script
    shell_config = []
    shell_config += ['# specify folders']
    shell_config += ['working_folder="%s"' % Config().paths.get("project_root")]
    shell_config += ['log_folder="%s"' % Config().paths.get("log_folder")]
    shell_config += ['maps_folder="%s"' % Config().paths.get("maps_folder")]
    shell_config += ['sql_files_folder="%s"' % Config().paths.get("sql_files_folder")]
    shell_config += ['temp_folder="%s"' % Config().paths.get("temp_folder")]
    shell_config += ['tools_folder="%s"' % Config().paths.get("tools_folder")]
    # helper programs
    shell_config += ['\n# some helper programs']
    shell_config += ['osmfilter_file="$tools_folder/osmfilter"']
    shell_config += ['osmconvert_file="$tools_folder/osmconvert"']
    shell_config += ['osmosis_folder="$tools_folder/osmosis"']
    shell_config += ['osmosis_file="$osmosis_folder/bin/osmosis"']
    shell_config += ['osm2po_folder="$tools_folder/osm2po"']
    shell_config += ['osm2po_file="$osm2po_folder/osm2po-core-5.0.18-signed.jar"']
    shell_config += ['osm2po_config="$osm2po_folder/osm2po.config"']
    # database settings
    shell_config += ['\n# database settings']
    shell_config += ['server_address="%s"' % Config().database.get("host_name")]
    shell_config += ['server_port=%d' % Config().database.get("port")]
    shell_config += ['user_name="%s"' % Config().database.get("user")]
    shell_config += ['password="%s"' % Config().database.get("password")]
    shell_config += ['db_active_name="%s"' % map_id]
    shell_config += ['db_tmp_name="%s_tmp"' % map_id]
    shell_config += ['db_prefix="%s"' % Config().database.get("routing_prefix")]
    shell_config += ['db_routing_table="%s"' % Config().database.get("routing_table")]
    shell_config += ['db_map_info="%s"' % Config().database.get("map_info")]
    shell_config += ['db_map_version=%s' % supported_map_version_list[-1]]
    shell_config += ['export PGPASSWORD=$password']
    # Java options
    shell_config += ['\n# Java options']
    shell_config += ['ram="%s"' % Config().java.get("ram")]
    shell_config += ['export JAVACMD_OPTIONS="-server -Xmx$ram -Djava.io.tmpdir=$temp_folder"']
    # map settings
    shell_config += ['\n# maps']
    shell_config += ['download_map_url="%s"' % map.get("urls")]
    shell_config += ['pbf_osm_file="$maps_folder/map.osm.pbf"']
    shell_config += ['o5m_osm_file="$maps_folder/map.o5m"']
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


def start_public_transport_library():
    executable = Config().paths.get("public_transport_library_executable")
    gateway_port = Config().java.get("gateway_port")
    if not os.path.exists(executable):
        exit("Public transport library executable %s not available" % executable, prefix="")
    elif gateway_port == 0:
        exit("Public transport library gateway port not available", prefix="")
    else:
        child = Popen(["java", "-jar", executable, str(gateway_port)])
        child.communicate()


def start_webserver():
    webserver.start()


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
    create_database = subparsers.add_parser(
            "create-map-database",
            description="Start a script to create a new map database thats already in the config file",
            help="Start a script to create a new map database thats already in the config file")
    create_database.add_argument(
            'map_id', nargs='?', help='The map id from config')
    # start public transport library sub parser
    subparsers.add_parser(
            "start-public-transport-library",
            description="Start public transport library",
            help="Start public transport library")
    # start webserver
    subparsers.add_parser(
            "start-webserver",
            description="Start webserver for client communication",
            help="Start webserver for client communication")

    args = parser.parse_args()
    if args.action == "create-map-database":
        create_map_database(args.map_id)
    elif args.action == "start-public-transport-library":
        start_public_transport_library()
    elif args.action == "start-webserver":
        start_webserver()


if __name__ == '__main__':
    main()
