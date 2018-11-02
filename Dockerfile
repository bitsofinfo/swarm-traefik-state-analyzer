FROM python:3.6.5-alpine

EXPOSE 8000

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
    chmod +x /usr/local/bin/*.py ; \
    rm -rf /var/cache/apk/*

# required modules
RUN pip install --upgrade pip docker jinja2 pyyaml python-dateutil prometheus_client watchdog
