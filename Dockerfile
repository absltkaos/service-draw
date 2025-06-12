FROM python:3


RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        python3-flask \
        python3-gevent \
        python3-dateutil \
        python3-pydot \
        graphviz && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/local/service-draw/servicedraw && \
    mkdir -p /etc/service-draw/services.d && \
    mkdir -p /var/servicedraw/templates

COPY ./service-draw.py /usr/local/service-draw/
COPY ./servicedraw /usr/local/service-draw/servicedraw/
COPY ./templates /var/servicedraw/templates
COPY ./service-draw.conf.ex /etc/service-draw/service-draw.conf

WORKDIR /usr/local/service-draw

CMD ["/usr/local/service-draw/service-draw.py", "/etc/service-draw/service-draw.conf"]
