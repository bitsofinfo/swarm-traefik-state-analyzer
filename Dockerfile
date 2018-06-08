FROM python:3.6.5-alpine

# install the analyzer under /usr/local/bin
RUN apk update ; \
    apk upgrade ; \
    apk add git ; \
    echo $PATH ; \
    git clone https://github.com/bitsofinfo/swarm-traefik-state-analyzer.git ; \
    cp /swarm-traefik-state-analyzer/*.py /usr/local/bin/ ; \
    rm -rf /swarm-traefik-state-analyzer ; \
    apk del git ; \
    ls -al /usr/local/bin ; \
    chmod +x /usr/local/bin/*.py

# required modules
RUN pip install docker jinja2 pyyaml python-dateutil prometheus_client watchdog docker