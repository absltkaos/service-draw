#!/usr/bin/python3
# vim:set et ts=4 sw=4:
from flask import Flask, request, render_template, Response, Markup
from configparser import ConfigParser
from servicedraw import dynamic_table
from werkzeug.utils import secure_filename
import gevent.subprocess as subprocess
import gevent.pywsgi
import logging
import os
import servicedraw
import signal
import traceback
import types


###-Vars-###
__version__='1.0.0'
DEFAULT_CONFIG='./service-draw.conf'
mount_point_href=""
descr="Generate/draw graphs of services"
name="Service Draw"
running=True
log_level = logging.INFO
logging_levels = {
    'trace': 9,
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL,
    'notset': logging.NOTSET
}
wsgi_opts = {}

#Define global vars
global confs_path

###-Classes-###

###-Functions-###
def sig_shutdown():
    global running
    logger.info("Signaling Shutdown")
    running = False

def logger_write_wrapper(self,msg,**kwargs):
    self.info(msg.strip(),**kwargs)

def gen_graph(pname,ext='svg',from_obj=None,reverse_deps=False,tail_opts=''):
    global confs_path
    failures=False

    path_to_conf="{}/{}.conf".format(confs_path,pname)
    if os.path.isfile(path_to_conf):
        try:
            sd=servicedraw.Draw(path_to_conf,logger=logging.getLogger('servicedraw.Draw({})'.format(pname)),url_base="{}/draw/{}/".format(mount_point_href,pname),url_tail=tail_opts)
            if ext == 'pydot':
                res=sd.build_graph().to_string()
            else:
                res=sd.draw(format=ext,from_obj=from_obj,reverse_deps=reverse_deps)
            del(sd)
        except Exception as ex:
            failures=True
            message=traceback.format_exc().splitlines()
            res="""
<svg height="60" width="500">
    <text x="0" y="15" fill="red">Error loading graph data: {}</text>
</svg>""".format('<br />\n'.join(message))
    else:
        res="""
<svg height="60" width="500">
    <text x="0" y="15" fill="red">Unknown Product/Service name requested: {}</text>
</svg>""".format(pname)
    return (failures,res)

#This is the main "init" method that sets us up
def init(conf_dict):
    global confs_path

    conf=conf_dict['conf']
    logger=logging.getLogger('ServiceDraw-API')
    confs_path=conf.get('main','confs_path')

    #Create a Bottle object
    app=Flask('ServiceDraw-API',template_folder=conf.get('main','templates_path'))
    app.log=logger

    #Add some routes
    @app.route("/")
    def index():
        dict_vars={
                'mount_point': mount_point_href,
                'table_data': ''
                }
        t=dynamic_table.Table(dynamic_table.RenderHTML(table_attr="class=\"table\""))
        t.set_col_names(['Product/Service','Services', 'Services Groups'])
        #Define our table rows, which is basically our menu here
        dirlist=os.listdir(confs_path)
        if dirlist:
            dirlist.sort()
        for f in dirlist:
            if os.path.isfile("{}/{}".format(confs_path,f)):
                name, ext = os.path.splitext(f)
                if ext == '.conf':
                    pdt_conf=ConfigParser()
                    if pdt_conf.read(('{}/{}'.format(confs_path,f))) == []:
                        raise RuntimeError('Could not load Product configuration from file: {}/{}'.format(confs_path,f))
                    try:
                        product_name=pdt_conf.get('global','name')
                    except:
                        product_name=name
                    #Use servicedraw to get basic service and service group information
                    try:
                        sd=servicedraw.Draw(pdt_conf,logger=logging.getLogger('servicedraw.Draw({})'.format(pdt_conf)))
                        sg_cnt=len(sd.service_groups)
                        s_cnt=len(sd.services) - sg_cnt
                        del(sd)
                    except Exception as ex:
                        msg=ex.args[0]
                        sg_cnt='Error loading service info: {}'.format(msg)
                        s_cnt='Error loading service info: {}'.format(msg)
                    t.add_row([ '<a href="{href}/draw/{name}">{name}({pname})</a>'.format(href=mount_point_href,name=name,pname=product_name), s_cnt, sg_cnt ])
        dict_vars['table_data']=Markup(str(t))
        return render_template('index.html',**dict_vars)

    @app.route("/draw/<name>")
    @app.route("/draw/<name>/<sub_name>")
    def draw(name,sub_name=None):
        dict_vars={
            'mount_point': mount_point_href,
            'graph_name': name,
            'name': name,
            'svg_data': '',
            'jump_to_list': """<li><a href="{}/draw/{}">All</a></li>""".format(mount_point_href,name),
            'cur_view': 'All',
            'svc_info_table': '',
            'svc_deps_table': '',
            'svc_rdeps_table': '',
            'dl_formats_links': '',
            'xtra_dropdown1': ''
        }
        rev_deps=request.args.get('rev_deps','f')
        jl_append=''
        reverse_deps=False
        if sub_name:
            dict_vars['cur_view']=sub_name
            if rev_deps == 't':
                rev_dep_val="On"
                reverse_deps=True
                jl_append='?rev_deps=t'
            else:
                rev_dep_val="Off"
            dict_vars['xtra_dropdown1']="""
                <button class="dropdown-toggle btn btn-default" type="button" data-toggle="dropdown">Reverse Dependencies: {} <span class="caret"></span></button>
                <ul class="dropdown-menu">
                    <li><a href="?rev_deps=t">On</a></li>
                    <li><a href="?rev_deps=f">Off</a></li>
                </ul>
            """.format(rev_dep_val)
        path_to_conf="{}/{}.conf".format(confs_path,name)
        if os.path.isfile(path_to_conf):
            try:
                c=ConfigParser()
                c.read(path_to_conf)
                try:
                    data=gen_graph(name,from_obj=sub_name,reverse_deps=reverse_deps,tail_opts=jl_append)[1]
                    if hasattr(data, 'decode'):
                        data=data.decode()
                    dict_vars['svg_data']=data
                except:
                    app.log.error(traceback.format_exc())
                try:
                    dict_vars['graph_name'] = c.get('global','name')
                except:
                    pass
                try:
                    sd=servicedraw.Draw(c)
                    dl=dict_vars['dl_formats_links']
                    dl_append=''
                    dl_fmts=[ 'pydot' ] + sd.graph.formats
                    jl=dict_vars['jump_to_list']
                    svcs=list(sd.services.keys())
                    svcs.sort()
                    if sub_name:
                        dl_append="/{}".format(sub_name)
                        try:
                            svc_info=sd.services[sub_name]
                            t=dynamic_table.Table(dynamic_table.RenderHTML(table_attr="class=\"table\""))
                            t.set_col_names(['Service Attribute','Value'])
                            td=dynamic_table.Table(dynamic_table.RenderHTML(table_attr="class=\"table\""))
                            td.set_col_names(['Depends on Service','Port'])
                            trd=dynamic_table.Table(dynamic_table.RenderHTML(table_attr="class=\"table\""))
                            trd.set_col_names(['Depended on by Service','To Port'])
                            for k in svc_info:
                                if k == 'depends':
                                    if svc_info[k]:
                                        for d in svc_info[k]:
                                            if svc_info[k][d]['ports']:
                                                for p in svc_info[k][d]['ports']:
                                                    td.add_row([d,p])
                                            else:
                                                td.add_row([d,'N/A'])
                                    else:
                                        td.add_row(['None Defined',''])
                                elif k == 'reverse_depends':
                                    if svc_info[k]:
                                        for d in svc_info[k]:
                                            if svc_info[k][d]['ports']:
                                                for p in svc_info[k][d]['ports']:
                                                    trd.add_row([d,p])
                                            else:
                                                trd.add_row([d,'N/A'])
                                    else:
                                        trd.add_row(['None Defined',''])
                                else:
                                    t.add_row([k,svc_info[k]])
                            dict_vars['svc_info_table']=str(t)
                            dict_vars['svc_deps_table']=str(td)
                            dict_vars['svc_rdeps_table']=str(trd)
                        except:
                            pass
                    del(sd)
                    for svc in svcs:
                        jl+="""<li><a href="{href}/draw/{name}/{svc}{jl}">{svc} </a></li>""".format(href=mount_point_href,name=name,svc=svc,jl=jl_append)
                    dict_vars['jump_to_list']=jl
                    del(jl)
                    for fmt in dl_fmts:
                        f=fmt.upper()
                        dl+="""<li><a href="{}/drawgraph/{}{}.{}?download=t">{}</a></li>""".format(mount_point_href,name,dl_append,fmt,f)
                    dict_vars['dl_formats_links']=dl
                    del(dl)
                except:
                    dict_vars['graph_name'] = "Error loading info for Product/Service: {}".format(name)
                    dict_vars['jump_to_list'] = "<li>N/A</li>"
                    app.log.error(traceback.format_exc())
            except:
                app.log.error(traceback.format_exc())
                dict_vars['graph_name'] = "Error loading info for Product/Service: {}".format(name)
        for m in [ 'jump_to_list', 'svg_data', 'svc_info_table', 'svc_deps_table', 'svc_rdeps_table','dl_formats_links','xtra_dropdown1' ]:
            dict_vars[m] = Markup(dict_vars[m])
        return render_template('draw_graph.html',**dict_vars)

    @app.route("/drawgraph/<pname>.<ext>")
    @app.route("/drawgraph/<pname>/<sub_name>.<ext>")
    def drawgraph(pname,ext='svg',sub_name=None):
        fn=pname
        if sub_name:
            fn+="_{}".format(sub_name)
        fn+=".{}".format(ext)
        try:
            data=gen_graph(pname,ext,from_obj=sub_name)
        except:
            raise
        if ext in [ 'dot', 'pydot' ]:
            ext_type = 'text/plain'
        elif ext == 'svg':
            ext_type = 'text/html'
        else:
            ext_type='image/{}'.format(ext)
        if data[0]:
            ext_type='text/html'
        resp = Response(response=data[1],content_type=ext_type)
        dl=request.args.get('download','f')
        if dl == 't':
            resp.headers.set('Content-Disposition', 'attachment; filename="{}"'.format(fn))
        return resp

    #Return our Flask application object
    return app

###-Main-###
if __name__ == "__main__":
    #We aren't being imported, so try and run as a standalone app
    import sys

    CONFIG=''
    mount_point_href=""
    #-- Do some initial setup --#
    if len(sys.argv) > 1:
        CONFIG=sys.argv[1]
    if CONFIG:
        REAL_CONFIG=CONFIG
    else:
        REAL_CONFIG=DEFAULT_CONFIG
    conf = ConfigParser()

    if conf.read((REAL_CONFIG)) == []:
        print('Could not load config from DEFAULT_CONFIG({}) or User Supplied CONFIG({})'.format(DEFAULT_CONFIG,CONFIG))
        sys.exit(1)
    
    #Initialize signal handling
    print("Initializing signal handlers")
    gevent.signal_handler(signal.SIGINT,sig_shutdown)
    gevent.signal_handler(signal.SIGQUIT,sig_shutdown)

    #Create a logger
    #Initialize logging
    print("Initializing Logging")
    try:
        log_level = conf.getint('main','log_level')
    except ValueError:
        try:
            log_level = logging_levels[conf.get('main','log_level').lower()]
        except:
            raise
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger=logging.getLogger('Main')
    glogger = logging.getLogger("WSGIServer")
    glogger.write = types.MethodType(logger_write_wrapper,glogger)
    conf_dict={
        'conf': conf,
    }
    wsgi_app=init(conf_dict)
    wsgi_opts['listener'] = (conf.get('main','listen'), conf.getint('main', 'port'))
    wsgi_opts['application'] = wsgi_app
    wsgi_opts['log'] = glogger
    wsgi = gevent.pywsgi.WSGIServer(**wsgi_opts)
    #Start the WSGI server
    wsgi.start()

    logger.info("Service Draw has started")
    while running:
        gevent.wait(timeout=1)

    #Close down gevent servers
    logger.info("Shutting down..")
    wsgi.close()
    wsgi.stop(timeout=1)
