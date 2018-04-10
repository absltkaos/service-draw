# vim:set et ts=4 sw=4:
from configparser import SafeConfigParser
import logging
import sys
import re
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from servicedraw import pydot

__version__='1.0.0'

def_service_opts={
    'depends': {},
    'reverse_depends': {},
    'infra_service': False,
    'color': 'auto',
    'fontcolor': 'blue',
    'bgcolor': 'white',
    'shape': 'ellipse',
    'type': 'service',
    'member_of_group': '',
    'style': 'filled'
}

def_service_group_opts={
    'color': 'black',
    'fontcolor': 'black',
    'bgcolor': 'white',
    'style': None,
    'type': 'service_group',
}

def_graph_opts={
    'name': 'Service Dependency Graph',
    'layout': 'TB',
    'fontcolor': 'black',
    'bgcolor': None
}

class Draw:
    def __init__(self,config,url_base='',url_tail='',logger=None,default_service_opts=None,default_service_group_opts=None):
        self.services=dict()
        self.service_groups=dict()
        self.url=dict()
        if url_base or url_tail:
            self.url['base']=url_base
            self.url['tail']=url_tail
        self.graph_opts=dict()
        if logger:
            self.logger=logger
        else:
            self.logger=logging.getLogger('servicedraw.Draw')

        if hasattr(config,'sections'):
            try:
                s_count=len(config.sections())
                self.conf=config
            except:
                raise RuntimeError("Passed config is neither a file path, nor a SafeConfigParser object: {}".format(config))
        else:
            self.conf = SafeConfigParser()
            if self.conf.read((config)) == []:
                raise RuntimeError('Could not load config from: {}'.format(config))

        #Merge our defaults into two complete dicts where the service one is
        #the more complete one, and service_group just adds/overrides from
        #the service one
        self.def_service_opts=dict(def_service_opts)
        self.def_service_group_opts=dict(def_service_opts)
        for def_opt in def_service_group_opts:
            self.def_service_group_opts[def_opt]=def_service_group_opts[def_opt]
        #If we had default opts dicts passed, load them in:
        if default_service_opts:
            for opt in default_service_opts:
                self.def_service_opts[opt]=default_service_opts[opt]
        if default_service_group_opts:
            for opt in default_service_group_opts:
                self.def_service_group_opts[opt]=default_service_group_opts[opt]

        #Load up our global vars
        for opt,val in self.conf.items('global'):
            self.graph_opts[opt]=val
        for def_gopt in def_graph_opts:
            try:
                tmp=self.graph_opts[def_gopt]
            except KeyError:
                self.graph_opts[def_gopt]=def_graph_opts[def_gopt]
        #Override any service or service_group defaults passed from global
        for opt in self.graph_opts:
            if opt.startswith('default_service_'):
                if opt.startswith('default_service_group_'):
                    #Override service_group opt
                    oopt=opt[len('default_service_group_'):]
                    self.def_service_group_opts[oopt]=self.graph_opts[opt]
                else:
                    #Override service opt
                    oopt=opt[len('default_service_'):]
                    self.def_service_opts[oopt]=self.graph_opts[opt]

        #Load up our services data from the config
        for section in self.conf.sections():
            #Set global graph settings and pull in any missing from defaults
            if section == 'global':
                continue
            #Our default opts will default to a service type instead of service
            #group
            def_opts=self.def_service_opts

            #Make a new services entry
            self.services[section]={}
            #Add in passed values to the entry
            self.logger.debug("{}{}".format("Creating services entry for: ",section))
            for opt,val in self.conf.items(section):
                self.services[section][opt]=val
            #Set service_group defaults in services dict
            try:
                t=self.services[section]['type']
                #Looks like service_group was set so pull in service_group
                #defaults
                if t == 'service_group':
                    def_opts=self.def_service_group_opts
            except KeyError:
                pass
            #Set defaults of options if not set in conf
            for def_opt in def_opts:
                try:
                    tmp=self.services[section][def_opt]
                except KeyError:
                    self.logger.trace("Setting default opt for Service: {} opt: {} to: {}".format(section,def_opt,def_opts[def_opt]))
                    self.services[section][def_opt]=def_opts[def_opt]
            self.services[section]['reverse_depends']=dict()
        
        #Update Logger name
        #self.logger.name+='.{}'.format(self.graph_opts['name'])

        #Make a new graph
        self.graph = self._new_graph()

        #Find and create any inferred service_groups that aren't explicitely defined
        for svc in dict(self.services):
            mg=self.services[svc]['member_of_group']
            #Inferred service_group
            if mg and mg not in self.services:
                self.logger.debug("Creating services entry for inferred service_group 1st pass: {}".format(mg))
                self.services[mg]=dict(self.def_service_group_opts)

        #Process dependencies and any inferred nodes
        for svc in self.services:
            #Parse out and generate the depends service and port structure
            if self.services[svc]["depends"]:
                deps_dict={}
                deps=self.services[svc]["depends"]
                for d_p in deps.split(';'):
                    d_p_split=d_p.strip(']').split('[')
                    d=d_p_split[0]
                    if len(d_p_split) > 1:
                        p=d_p_split[1].split(',')
                    else:
                        p=[]
                    deps_dict[d]={}
                    deps_dict[d]['ports']=p
                    #Create inferred node
                    try:
                        tmp=self.services[d]["depends"]
                    except KeyError:
                        self.logger.debug("Creating inferred inferred service entry: {}".format(d))
                        self.services[d]=dict(self.def_service_opts)
                        self.services[d]['reverse_depends']=dict()
                    #Create a depends_by dictionary for dependency back svc
                    try:
                        self.logger.debug("Creating reverse dependancy. Service: {} -> {}. So Adding from {} -> {}".format(svc,d,d,svc))
                        tmp=self.services[d]["reverse_depends"][svc]
                        tmp["ports"] + p
                    except KeyError:
                        self.services[d]["reverse_depends"][svc]={}
                        self.services[d]["reverse_depends"][svc]["ports"]=list(p)
                self.services[svc]["depends"]=deps_dict

        #Generate our service_groups dictionary and make empty Cluster subgraphs
        for svc in self.services:
            svc_canon=re.sub('[ .!@#$%^&*():-]','_',svc)
            #Define args to pass to pydot.Cluster
            kwargs={}
            kwargs['labeljust']="left"
            kwargs['labelfontsize']="15"
            #Type has been explicitely set to service_group
            if self.services[svc]["type"] == "service_group":
                try:
                    tmp=self.service_groups[svc]["cluster_obj"]
                except KeyError:
                    kwargs['label']=svc
                    kwargs['fontcolor']=self.services[svc]['fontcolor']
                    kwargs['color']=self.services[svc]['color']
                    kwargs['bgcolor']=self.services[svc]['bgcolor']
                    kwargs['style']=self.services[svc]['style']
                    if self.url:
                        url_svc=dict(self.url)
                        url_svc['svc']=svc
                        kwargs['href']="{base}{svc}{tail}".format(**url_svc)
                    self.logger.debug("Creating service_group entry for explicitly defined service_group: {}".format(svc))
                    self.service_groups[svc]=dict()
                    self.service_groups[svc]["cluster_obj"]=pydot.Cluster(svc_canon,**kwargs)
                    self.service_groups[svc]["canon_name"]=svc_canon
                    self.service_groups[svc]["null_node_name"]="{}_group".format(svc_canon)
                    self.service_groups[svc]["members"]=[]
                    self.service_groups[svc]["svc_members"]=[]
                    #Add in an empty node
                    self.service_groups[svc]["cluster_obj"].add_node(pydot.Node("{}_group".format(svc_canon),label='""',shape="none"))
            else:
                #See if we have discovered depenended up inferred service_group
                #then create the entry in the service_groups dict as well as a
                #new entry into services dict
                if self.services[svc]["member_of_group"]:
                    mg=self.services[svc]["member_of_group"]
                    mg_canon=re.sub('[ .!@#$%^&*():-]','_',mg)
                    #Create the service_group entry if it doesn't exist
                    try:
                        tmp=self.service_groups[mg]["cluster_obj"]
                    except KeyError:
                        kwargs['label']=mg
                        kwargs['fontcolor']=self.services[mg]['fontcolor']
                        kwargs['color']=self.services[mg]['color']
                        kwargs['bgcolor']=self.services[mg]['bgcolor']
                        kwargs['style']=self.services[mg]['style']
                        if self.url:
                            url_svc=dict(self.url)
                            url_svc['svc']=mg
                            kwargs['href']="{base}{svc}{tail}".format(**url_svc)
                        self.logger.debug("Creating service_group entry for inferred service_group: {}".format(mg))
                        self.service_groups[mg]=dict()
                        self.service_groups[mg]["cluster_obj"]=pydot.Cluster(mg_canon,**kwargs)
                        self.service_groups[mg]["canon_name"]=mg_canon
                        self.service_groups[mg]["null_node_name"]="{}_group".format(mg_canon)
                        self.service_groups[mg]["members"]=[]
                        self.service_groups[mg]["svc_members"]=[]
                        #Add in an empty node
                        self.service_groups[mg]["cluster_obj"].add_node(pydot.Node("{}_group".format(mg_canon),label='""',shape="none"))

        #Loop through service_groups dictionary to generate the cluster's cluster member list:
        for sg in self.service_groups:
            self.service_groups[sg]["member_of_group"]=self.services[sg]["member_of_group"]
            if self.services[sg]["member_of_group"]:
                self.logger.debug("Adding group: {} to Group: {}".format(sg,self.services[sg]["member_of_group"]))
                self.service_groups[self.services[sg]["member_of_group"]]["members"].append(sg)
        #Loop through services dictionary to add svc members to service_groups dict
        for svc in self.services:
            if svc in self.service_groups:
                continue
            mg=self.services[svc]['member_of_group']
            if mg:
                self.logger.debug("Adding Service: {} to Service Group: {}".format(svc,mg))
                self.service_groups[mg]['svc_members'].append(svc)

    def _new_graph(self):
        g=pydot.Dot(graph_type='digraph',graph_name="Main Graph",label=self.graph_opts['name'],fontcolor=self.graph_opts['fontcolor'],bgcolor=self.graph_opts['bgcolor'],rankdir=self.graph_opts['layout'],compound=True)
        return g

    def _create_nodes(self):
        #Generate the graph by adding nodes to the graph or a cluster
        for node in self.services:
            if self.services[node]["type"] == "service_group":
                continue
            if self.services[node]["member_of_group"]:
                g=self.service_groups[self.services[node]["member_of_group"]]["cluster_obj"]
            else:
                g=self.graph
            shape=self.services[node]["shape"]
            if self.services[node]["infra_service"]:
                shape="diamond"
            if self.services[node]["shape"] != self.def_service_opts['shape']:
                shape=self.services[node]["shape"]
            self.logger.debug("Adding node: {} to graph: {}".format(node,g.get_label()))
            
            #build our argument list for pydot Node creation
            kwargs={}
            if self.url:
                url_svc=dict(self.url)
                url_svc['svc']=node
                kwargs['href']="{base}{svc}{tail}".format(**url_svc)
            kwargs['color']=self.services[node]["color"]
            kwargs['shape']=shape
            kwargs['fontcolor']=self.services[node]["fontcolor"]
            kwargs['fillcolor']=self.services[node]["bgcolor"]
            kwargs['style']='"{}"'.format(self.services[node]["style"])
            if kwargs['color'] == "auto":
                kwargs['color'] = "black"
            node_obj = pydot.Node(node,**kwargs)
            self.services[node]["node_obj"]=node_obj
            g.add_node(node_obj)

    def _add_cluster(self,cluster,processed,svc_groups):
        procd=processed
        if cluster in procd:
            return procd
        if not svc_groups[cluster]["members"]:
            self.logger.debug("Cluster: {} has no members".format(cluster))
            if not svc_groups[cluster]["member_of_group"]:
                #This cluster is not a member of any group, add to main graph
                self.logger.debug("Cluster: {} has no parent, setting parent to main graph".format(cluster))
                parent_cluster=self.graph
            else:
                #No members, add to parent member_of_group
                parent_cluster_name=svc_groups[cluster]["member_of_group"]
                parent_cluster=svc_groups[parent_cluster_name]["cluster_obj"]
                self.logger.debug("Cluster: {} has a parent, setting parent to: {}".format(cluster,parent_cluster_name))
            self.logger.debug("Adding cluster: {} to cluster_group: {}".format(svc_groups[cluster]["cluster_obj"].get_label(),parent_cluster.get_label()))
            parent_cluster.add_subgraph(svc_groups[cluster]["cluster_obj"])
            #Add to processed Set
            procd.add(cluster)
        else:
            self.logger.debug("Cluster: {} has members".format(cluster))
            #There are members to work through
            for membr in svc_groups[cluster]["members"]:
                if membr in procd:
                    continue
                #Recurse on membr
                self.logger.debug("Recursing on member: {}".format(membr))
                procd.union(self._add_cluster(membr,procd,svc_groups))
            if not svc_groups[cluster]["member_of_group"]:
                self.logger.debug("Cluster with members: {} has no parent, setting parent to main graph".format(cluster))
                #This has no parent, add to main graph
                parent_cluster=self.graph
            else:
                #This has a parent, add it to its parent
                parent_cluster_name=svc_groups[cluster]["member_of_group"]
                parent_cluster=self.service_groups[parent_cluster_name]["cluster_obj"]
                self.logger.debug("Cluster with members: {} has a parent, setting parent to: {}".format(cluster,parent_cluster_name))
            self.logger.debug("Adding cluster: {} to cluster_group: {}".format(self.service_groups[cluster]["cluster_obj"].get_label(),parent_cluster.get_label()))
            parent_cluster.add_subgraph(svc_groups[cluster]["cluster_obj"])
            procd.add(cluster)
        return procd

    def _dump_svcs_dict(self):
        import json
        import copy
        d=copy.deepcopy(self.service_groups)
        s=copy.deepcopy(self.services)
        for k in d:
            d[k]["cluster_obj"]=str(d[k]["cluster_obj"])
        for k in s:
            if s[k]['type'] != 'service_group':
                try:
                    s[k]["node_obj"]=str(s[k]["node_obj"])
                except KeyError:
                    s[k]["node_obj"]=''
        self.logger.trace("{}".format(json.dumps(d,indent=4)))
        self.logger.trace("{}".format(json.dumps(s,indent=4)))

    def build_graph(self,from_obj=None,reverse_deps=False):
        self._create_nodes()
        nodes=list(self.services.keys())
        cust_nodes=[]
        cluster_list=list(self.service_groups.keys())
        cust_cluster=False
        if from_obj:
            self.graph.set_label("{} from({})".format(from_obj,self.graph_opts['name']))
            #See if root is a service_group(cluster) or a service(node)
            nodes=[]
            cluster_list=[]
            if from_obj in self.service_groups:
                cust_cluster=True
                root_cluster=[from_obj]
                cluster_list=[from_obj]
                nodes=list(self.service_groups[from_obj]['svc_members'])
                #Add member clusters
                for c in self.service_groups[from_obj]['members']:
                    if c != from_obj:
                        nodes+=self.service_groups[c]['svc_members']
                        cluster_list.append(c)
                #Add dependent nodes:
                for n in list(nodes):
                    for dn in self.services[n]['depends']:
                        if dn != from_obj:
                            if dn in self.service_groups:
                                cluster_list.append(dn)
                            else:
                                cust_nodes.append(dn)
                    if reverse_deps:
                        for dn in self.services[n]['reverse_depends']:
                            if dn != from_obj:
                                if dn in self.service_groups:
                                    cluster_list.append(dn)
                                else:
                                    cust_nodes.append(dn)
            else:
                try:
                    node=self.services[from_obj]
                    if node['type'] == "service":
                        nodes=[from_obj]
                        root_cluster=[]
                        for d in self.services[from_obj]['depends']:
                            if d != from_obj:
                                if d in self.service_groups:
                                    cluster_list.append(d)
                                    root_cluster.append(d)
                                    cust_cluster=True
                                else:
                                    nodes.append(d)
                        if reverse_deps:
                            for d in self.services[from_obj]['reverse_depends']:
                                if d != from_obj:
                                    if d in self.service_groups:
                                        cluster_list.append(d)
                                        root_cluster.append(d)
                                        cust_cluster=True
                                    else:
                                        nodes.append(d)
                except KeyError:
                    pass
                cust_nodes=nodes
        clust_processed=set()
        clusters=set(cluster_list)
        while clusters:
            cluster=clusters.pop()
            clust_processed.union(self._add_cluster(cluster,clust_processed,self.service_groups))
            clusters=clusters.difference(clust_processed)

        if cust_cluster:
            for rc in root_cluster:
                self.graph.add_subgraph(self.service_groups[rc]["cluster_obj"])

        if cust_nodes:
            for n in cust_nodes:
                self.graph.add_node(self.services[n]["node_obj"])

        #Draw Edges from cluster service_groups dependencies to clusters/nodes
        for cluster in cluster_list:
            cl=self.service_groups[cluster]["cluster_obj"]
            #See if we should add edges to our clusters
            if self.services[cluster]["depends"]:
                for dep in self.services[cluster]["depends"]:
                    kwargs={}
                    kwargs['src']=self.service_groups[cluster]["null_node_name"]
                    kwargs['dst']=dep
                    kwargs['ltail']=cl.get_name()
                    self.logger.debug("Drawing Edge from cluster: {} to {}".format(kwargs['src'],kwargs['dst']))
                    if dep in self.service_groups:
                        #Dependency is a cluster
                        kwargs['dst']=self.service_groups[dep]["null_node_name"]
                        kwargs['lhead']=self.service_groups[dep]["cluster_obj"].get_name()
                    edge = pydot.Edge(**kwargs)
                self.graph.add_edge(edge)

        #Draw Edges from nodes to nodes/clusters
        for node in nodes:
            if self.services[node]["type"] not in [ "service", "infra_service" ]:
                continue
            for dep in self.services[node]["depends"]:
                kwargs={}
                kwargs['src']=node
                kwargs['dst']=dep
                if self.services[node]["depends"][dep]["ports"]:
                    kwargs['label']='\n'.join(self.services[node]["depends"][dep]["ports"])
                if dep in self.service_groups:
                    kwargs['dst']=self.service_groups[dep]["null_node_name"]
                    kwargs['lhead']=self.service_groups[dep]["cluster_obj"].get_name()
                self.logger.debug("Drawing Edge from node: {} to {}".format(kwargs['src'],kwargs['dst']))
                edge = pydot.Edge(**kwargs)
                self.graph.add_edge(edge)
        return self.graph

    def draw(self,from_obj=None,format="svg",reverse_deps=False):
        self.build_graph(from_obj=from_obj,reverse_deps=reverse_deps)
        result=self.graph.create(format=format)
        del(self.graph)
        self.graph=self._new_graph()
        return(result)

## Functions ##
def logger_trace(self,message,*args,**kws):
    if self.isEnabledFor(9):
        self._log(9, message, args, **kws)

if not hasattr(logging.Logger,'trace'):
    logging.addLevelName(9, "TRACE")
    logging.Logger.trace = logger_trace

