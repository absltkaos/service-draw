# Introduction
This is a service that provides a way to document service dependencies and then generate graphs from your document.  In my experience keeping diagrams of services and deployments has been very tricky. Usually it is done on a whiteboard Ad-Hoc during a training or discussion. Or one person creates a diagram in a tool like Visio,Dia, yED etc... then exports it to a common image format for everyone else to consume.

The problems with this are:

1. Ad-Hoc diagrams are great, but not persistent. The next time you need to explain something you have to try and recreate the diagram all over again
1. Creating a diagram in a tool like Visio can be time consuming.
1. Once a diagram has been created in a diagramming tool, it usually only resides on that single user's computer. The exported images are difficult for anyone to modify when new services are added or changed.
1. Even if the diagramming tool's saved file is shared, it isn't easy to see what was changed from one edit to another without opening all other revisions.
1. Even adding a saved file to an RCS like git, doesn't work as many formats are binary, so no diff... those that aren't usually are XML which diffing get ugly.

# Installing the service
## Debian Source
There are debian build files available, but they are currently unmaintained.

Docker Container is recommended

## Running via docker

Build the image:
```bash
docker build . -t service-draw:latest
```

Run container:
```bash
docker run --rm -it -v $PWD/services.d:/etc/service-draw/services.d -p 8080:8080 service-draw:latest
```

Then you should be able to load the UI by going to: http://localhost:8080

The override the following paths inside the container as needed:
* `/etc/service-draw/service-draw.conf` - The main config file (Overriding this may affect some of the paths below)
* `/etc/service-draw/service.d/` - The directory where service graphs are stored
* `/var/servicedraw/templates` - The directory where the html templates for the webui are loaded
* `/usr/local/service-draw/service-draw.py` - The main executable
* `/usr/local/service-draw/servicedraw/` - The module where all the logic is stored

# Solution
The problems mentioned above are addressed with this plugin. Here is how it works:

1. Install the service
1. Go to /etc/service-draw/services.d directory and create a new file <Product>.conf
1. Being adding in services and service groups. (See the "Service Config" section)

The .conf can be managed with and RCS and deployed with config management if wanted. Because the config is divided into sections, changes made by people (tracked in your RCS) are easy to see.

# Important information about how this works
This uses pydot >= 1.2.25 (which uses graphviz) to create elements of a .dot graph.

Because of this, there are times when options exposed via the config file and left up to the end-user could be non-parseable to graphiz. I've tried catching some common edge cases, but if pydot throws an InvocationError it is because pydot thinks everything looks good but graphviz doesn't agree. Frequently this is because of commas added to options that don't support them etc...

# Configuration
There are two type of configurations.

1. Config options for the service
1. Config or configs for Products/Services that are turned into graphs

## Service draw configuration
This is the easiest and simplest. The service just needs to have the following options set the config section "[main]":
```
log_level
listen
port
confs_path
templates_path
```

'log_level' is the log level to use
'listen' is the interface to listen on
'port'  is the port to listening on
'confs_path' is the path to where the Product/Service graph .confs(s) are stored
'templates_path' is the path to where template files are stored

## Service/Product Config
The [global] section defines some configuration for the overall graph
Options include:
```
  name #Title name to create for the graph
  layout #LR or TB. LR means arrow dependencies will go Left to Right, TB is  Top to Bottom. Default is TB
  fontcolor #Color to use for the main graph's label
  bgcolor #Color to use for the main graph
  default_service_color #Default color option for services (def=black)
  default_service_bgcolor #Default bgcolor option for services (def=white)
  default_service_fontcolor #Default fontcolor option for services (def=blue)
  default_service_shape #Default shape to use for services (def=ellipse)
  default_service_style #Default style for service_groups (def=filled)
  default_service_group_color #Default color option for service groups (def=black)
  default_service_group_bgcolor #Default bgcolor option for service groups (def=white)
  default_service_group_fontcolor #Default fontcolor option for service groups (def=black)
  default_service_group_style #Default style for service_groups (def=None)
```
Services or Service Groups are denoted with square brackets on the service name on their own line. Like so:
```
#[Service1]
```
Services can have attributes, all attributes are optional.
Current attributes are:
```
  depends #This is a semi-colon separated list of other Services.Each of these
          #depended upon service can have alternate list of ports. Defined
          #with square braces and list of comma separated ports. Preferred
          #syntax is <proto>-<port>
  infra_service #True/False whether the service is a supporting
                #infrastructure service. For example an HTTP proxy LB, etc..
  shape #Overrride auto selection of shapes for the service
  type  #Type of service, this can be one of "service_group" or "service" the
        #default is "service"
  member_of_group  #Define a name to group the service into. A service can
                   #only be a member of one group, but service_group can be a
                   #member of a group as well.
  color #Color to use for drawing service node shapes
  fontcolor #Font color to use. Default for Services is "blue" for
            #service_group is black
  bgcolor #Color to use for filling in the grouping or node with a color
  style #Styling for the service or group. Styling options are per:
        #http://www.graphviz.org/doc/info/attrs.html#k:style
        #Default for groups is not set, for services it is "filled"
```

### Sample configuration
```
[global]
name=Sample Service

[LB]
depends=Web Farm[tcp-8080,tcp-8443]
infra_service=True
member_of_group=External Zone

[Web Farm]
depends=Mysql-Master[tcp-3306];Mysql-Slaves[tcp-3306]
member_of_group=External Zone

[Mysql-Master]
shape=trapezium
member_of_group=Mysql

[Mysql-Slaves]
member_of_group=Mysql
shape=trapezium
depends=Mysql-Master[tcp-3306]

[DB-Backup]
depends=Mysql-Master[tcp-3306];Backup
member_of_group=Mysql

[Mysql]
type=service_group
member_of_group=Internal Zone

[Backup]
type=service_group
member_of_group=Internal Zone

[Backup-Hosts]
member_of_group=Backup
depends=NFS[tcp-2049,udp-2049,udp-1110]

[NFS]
member_of_group=Backup
```
