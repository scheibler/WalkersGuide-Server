WalkersGuide-Server
===================



Introduction
------------

WalkersGuide is a navigational aid primarily intended for blind and visual impaired pedestrians. It
calculates routes and shows nearby points of interest.  The project consists of an Android client
and a server component. The latter performs the route calculation. The map data is provided by
[OpenStreetMap](https://www.openstreetmap.org), a project to create a free map of the world.

This repository contains the server application. The following section gives an overview about the
project structure. The subsequent sections cover installation instructions and usage notes.

Please visit https://www.walkersguide.org for more information about the project.



Project structure
-----------------

The map data for the routing process comes from [OpenStreetMap](http://openstreetmap.org). A country
or continent is downloaded and stored in a local Postgresql database. The scripts from the
"sql_functions" and "shell" folders help you to get a local copy of the OpenStreetMap database on
your server. But they not only create the database but also calculate additional database tables
like intersections, poi and a routing graph. These tables are required to perform the creation of a
walkers route.

The "webserver" folder contains python scripts to query data from the database and calculate the actual
route. It starts a web server, which listens for client requests on a specific port, calls the
route creation functions and returns the results to the client.

The PublicTransportInterface "dist" folder holds a small Java program to query public transportation data
like routes and departure timetables. The program serves as a wrapper for the Java library
[public-transport-enabler](https://github.com/schildbach/public-transport-enabler). This library
fetches, among others, data from the German public transportation provider "Deutsche Bahn". Therefore the public
transportation functionality currently is limited outside of Germany.



Installation
------------

This section describes the installation process of the required software. The instructions cover the
Debian Buster operating system.


### Postgresql, Postgis and pgrouting ###

Install Postgresql, Postgis (an extension to handle spacial data types like points and lines) and
pgrouting. You may use every Postgresql version >= 9.1 and Postgis version >= 2.0:

```
root# apt-get install postgresql-11 postgresql-11-postgis-2.5 postgresql-11-pgrouting
```

Then create a new database user and assign a password. It must be a super user:

```
root# su postgres
postgres$ createuser -P -s wgs_writer
postgres$ exit
```

After that, change database access permissions in the file

```
root# vim /etc/postgresql/11/main/pg_hba.conf
```

to the following ones:

```
[...]
# TYPE  DATABASE        USER            ADDRESS                 METHOD
#
# "local" is for Unix domain socket connections only
#local   all             all                                     peer
#
# IPv4 local connections:
#host    all             all             127.0.0.1/32            md5
host    all             wgs_writer             127.0.0.1/32            md5
#
# IPv6 local connections:
#host    all             all             ::1/128                 md5
host    all             wgs_writer      ::1/128                 md5
#
# Allow replication connections from localhost, by a user with the
# replication privilege.
#local   replication     all                                     peer
#host    replication     all             127.0.0.1/32            md5
#host    replication     all             ::1/128                 md5
```

Now you have to change some settings in the Postgresql main config. The defaults are fairly
conservative and often don't fit the needs for a large db. The settings hardly depend on the
hardware of your server. These are mine for a server with a Ryzen 3600 CPU, 64 GB Ram and 2 TB SSD:

```
root# vim /etc/postgresql/11/main/postgresql.conf
[...]
#------------------------------------------------------------------------------
# CUSTOMIZED OPTIONS
#------------------------------------------------------------------------------
data_directory = '/mnt/navi/postgresql/11/main'
max_connections = 15
# buffers
effective_cache_size = 32GB
shared_buffers = 16GB
maintenance_work_mem = 6GB
work_mem = 768MB
temp_buffers = 64MB
# ssd
seq_page_cost = 1.0
random_page_cost = 1.0
# misc optimizations
checkpoint_completion_target = 0.9
default_statistics_target = 500
constraint_exclusion = on
enable_partitionwise_join = on
enable_partitionwise_aggregate = on
```

Add the following Linux kernel params to `/etc/sysctl.conf`:

```
vm.overcommit_memory=2
vm.overcommit_ratio=80
```

and apply:

```
root# sysctl -p /etc/sysctl.conf
```

The tuning tipps come from the [PostgreSQL
wiki](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server). Furthermore you can use the
[postgresqltuner](https://github.com/jfcoz/postgresqltuner) to check your postgresql configuration.

Lastly restart Postgresql:

```
root# service postgresql restart
```


### Java ###

Some operations like compiling the public transportation library require the Java JDK:

```
root# apt-get install default-jdk gradle
```


### Webserver installation ###

The WalkersGuide Android client requires a secure connection via SSL. Don't use
cherrypy's own SSL server for that but Install and configure a webserver like nginx instead. The
webserver should handle the SSL connection and redirect traffic to the WalkersGuide server
component, which only runs locally at a different port.

You can find a sample configuration for nginx at `config.example/nginx-walkersguide.org.conf.example`.


### OpenStreetMap tools ###

First install Osmosis, OSMFilter and OSMConvert:

```
root# apt-get install osmosis osmctools
```

Then download osm2po. The application creates a database table which represents the routing graph of
all streets and ways. This graph is needed by pgrouting to calculate a route from start to the point
of destination.

Create a tools folder and download osm2po (maybe update version number) and retrieve the program
from http://www.osm2po.de:

```
osm$ cd /mnt/navi
osm$ mkdir tools
osm$ cd tools
osm$ wget http://www.osm2po.de/releases/osm2po-5.2.43.zip
osm$ unzip osm2po-5.2.43.zip -d osm2po-5.2.43
osm$ rm osm2po-5.2.43.zip
```

To use osm2po you have to  accept its license once. To do so, enter the folder, start the
demo.sh script and type "yes" when instructed. After that you can cancel the process and delete the
already created folder.

```
osm$ cd osm2po-5.2.43
osm$ chmod +x demo.sh
osm$ ./demo.sh
     # type yes and cancel by pressing ^c
osm$ rm -R hh
```


### WalkersGuide ###

Install git, screen and python pip:

```
root# apt-get install git screen python-pip
root# pip install virtualenv
```

Create python virtual environment:

```
osm$ cd /mnt/navi
# create
osm$ mkdir virtualenv
osm$ cd virtualenv
osm$ virtualenv [-p python3] walkersguide
osm$ ./walkersguide/bin/pip install py4j requests configobj cherrypy psycopg2-binary
```

Clone the WalkersGuide-Server repository

```
osm$ cd /mnt/navi
osm$ git clone https://github.com/scheibler/WalkersGuide-Server.git walkersguide
```

Enter the project directory and create some folders:

```
cd walkersguide
mkdir config logs maps tmp
```

Copy the osm2po configuration file.  The config file from the example config
folder and the map creation scripts below work well with osm2po versions <=5.2.43.

```
osm$ cp config.example/osm2po_5.0.18.conf.example config/osm2po.conf
```

Lastly copy the WalkersGuide example config file and adapt it to your needs:

```
osm$ cp config.example/wg_server.conf.example config/wg_server.conf
```

The example config contains an entry for Germany under the "maps" section. You may find the maps of
other countries [here](http://download.geofabrik.de/).



Usage
-----

It's recommended to launch the map creation process and the webserver within a screen session:

```
osm$ screen -S walkersguide
```

Create a new country/region database:

```
osm$ cd /mnt/navi/walkersguide
osm$ /mnt/navi/virtualenv/walkersguide-dev/bin/python wg_server.py create-map-database germany
```

start the public transport wrapper in tty 1:

```
osm$ /mnt/navi/virtualenv/walkersguide-dev/bin/python wg_server.py start-public-transport-library
```

and launch the webserver in tty 2:

```
osm$ /mnt/navi/virtualenv/walkersguide-dev/bin/python wg_server.py start-webserver
```

Test with:

```
osm$ wget --header='Accept-Encoding: gzip' https://walkersguide.example.com/get_status -O - | gunzip
```

Optional: Add an alias to your shell configuration:

```
alias wg='/mnt/navi/virtualenv/walkersguide/bin/python wg_server.py'
```

