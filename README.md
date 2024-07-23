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
or continent is downloaded and stored in a local Postgresql database. The bash script
`shell/create_complete_database.sh` creates a local copy of the OpenStreetMap database on your
server. Furthermore it calculates additional database tables like intersections, poi and a routing
graph. These tables are required to perform the creation of a walkers route.

The "webserver" folder contains python scripts to query data from the database and calculate the actual
route. It starts a web server, which listens for client requests on a specific port, calls the
route creation functions and returns the results to the client.



Installation
------------

This section lists the required steps to install the WalkersGuide server under Debian 12 (Bookworm).


### Postgresql, Postgis and pgrouting ###

Install Postgresql, Postgis (an extension to handle spacial data types like points and lines) and pgrouting.
You must at least use Postgresql >= 11, Postgis >= 2.5 and pgrouting >= 2.5:

```
root# apt install postgresql-15 postgresql-15-postgis-3 postgresql-15-pgrouting
```

Then create a new database user and assign a password. It must be a super user:

```
root# su postgres
postgres$ createuser -P -s wgs_writer
postgres$ exit
```

After that, change database access permissions in the file

```
root# vim /etc/postgresql/15/main/pg_hba.conf
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
hardware of your server. These are mine for a server with a Ryzen 3600 CPU, 64 GB Ram and 4 TB SSD:

```
root# vim /etc/postgresql/15/main/postgresql.conf
[...]
#------------------------------------------------------------------------------
# CUSTOMIZED OPTIONS
#------------------------------------------------------------------------------
data_directory = '/mnt/navi/postgresql/15/main'
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
effective_io_concurrency = 100
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
wiki](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server). Additionally you may use the
[postgresqltuner](https://github.com/jfcoz/postgresqltuner) to check and optimize your postgresql configuration.

Lastly restart Postgresql:

```
root# systemctl restart postgresql.service
```


### Webserver installation ###

The WalkersGuide Android client requires a secure connection via SSL. Don't use
cherrypy's own SSL server for that but Install and configure a webserver like nginx instead. The
webserver should handle the SSL connection and redirect traffic to the WalkersGuide server
component, which only runs locally at a different port.

You can find a sample configuration for nginx at `config.example/nginx-walkersguide.org.conf.example`.


### OpenStreetMap tools ###

First install Osmosis, OSMFilter, OSMConvert and Osmium:

```
root# apt install osmosis osmctools osmium-tool
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

Install git, pip, parallel and screen

```
root# apt install git python3-pip python3-venv moreutils screen
```

Clone the WalkersGuide-Server repository

```
osm$ cd /mnt/navi
osm$ git clone https://github.com/scheibler/WalkersGuide-Server.git walkersguide
```

Enter the project directory and create some folders:

```
cd walkersguide
mkdir config logs
```

Create python virtual environment and install dependencies:

```
osm$ python3 -m venv .
osm$ source ./bin/activate
(walkersguide) osm$ pip install requests configobj cherrypy psycopg2-binary
(walkersguide) osm$ deactivate
```

If you later want to remove the python virtual environment again:

```
osm$ cd /mnt/navi/walkersguide
osm$ rm -R bin include lib lib64 pyvenv.cfg
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
osm$ ./run create-map-database germany
```

Afterwards launch the webserver:

```
osm$ ./run start-webserver
```

Test with:

```
osm$ wget --header='Accept-Encoding: gzip' https://walkersguide.example.com/get_status -O - | gunzip
```

Since version 1.3.2 the WalkersGuide server provides some very basic map usage statistics:

```
osm$ ./run statistics
```

