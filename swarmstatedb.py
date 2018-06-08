#!/usr/bin/env python

__author__ = "bitsofinfo"

import docker
import json
import pprint
import re
import argparse
import getopt, sys
import yaml
import glob
import logging
import time

def getServiceData(client,swarm_name,service_id):
    service_data = {"swarm_name":swarm_name,
                    "id":service_id,
                    "name":"",
                    "image":"",
                    "int_or_ext":"",
                    "replicas":1,
                    "port_mappings":[],
                    "traefik_host_labels": []}

    try:
        service = client.services.get(service_id)
    except:
        return []

    service_attrs = service.attrs
    service_endpoint = service_attrs['Endpoint']
    service_spec = service_attrs['Spec']

    service_data["name"] = service_spec['Name']
    service_mode = service_spec['Mode']
    if "Replicated" in service_mode:
        service_data["replicas"] = service_spec['Mode']['Replicated']['Replicas']

    # labels (we want to grab Host: frontend rules)
    raw_labels = service_spec['Labels']
    traefik_host_labels = []
    for label in raw_labels:
        if re.match("traefik.[a-zA-Z0-9-.]*frontend.rule", label):
            traefik_host_labels_tmp = raw_labels[label].split(":")[1].split(",")
            traefik_host_labels.extend(list(filter(lambda x: x != "", traefik_host_labels_tmp)))
        elif re.match("com.docker.stack.image", label):
            service_data["image"] = raw_labels[label]
        elif re.match("traefik.tags", label):
            if 'external' in raw_labels[label]:
                service_data["int_or_ext"] = 'external'
            elif 'internal' in raw_labels[label]:
                service_data["int_or_ext"] = 'internal'

    service_data["traefik_host_labels"] = traefik_host_labels

    # Services w/ no published ports we don't care about
    port_mappings = []
    if 'Ports' in service_endpoint:
        service_ports = service_endpoint['Ports']

        for p in service_ports:
            if 'PublishedPort' in p:
                port_mappings.append(str(p['PublishedPort']) + ":" + str(p['TargetPort']))

    service_data["port_mappings"] = port_mappings

    return service_data

# The main function that does the work...
# - swarm_name: logical swarm name to interrogate i.e. 'prodswarm1'
# - service_filter: filter for the services to get, None for all
#       i.e dictionary of {"name":"my-app"} Valid filters: id, name , label and mode
# - swarm_info_repo_root: path pointing to a directory structure
#       that contains swarm footprint yaml files. i.e. 'prodswarm1.yml'
# - output_filename: filename to write db to
#
def generate(swarm_name,service_filter,swarm_info_repo_root,output_filename):
    # instantiate the client
    logging.info("Reading swarm info files from: %s", swarm_info_repo_root)
    logging.info("Targeting swarm: %s",swarm_name)

    docker_host = None
    for yml_file in glob.iglob(swarm_info_repo_root+"/**/"+swarm_name+".yml", recursive=True):
        with open(yml_file, 'r') as f:
            logging.info("Consuming config from: %s",yml_file)
            docker_host = yaml.load(f)['SWARM_MGR_URI']

    if docker_host is None:
        logging.error("ERROR: no SWARM_MGR_URI in located for: %s", swarm_name)

    logging.info("Connecting to DOCKER_HOST: " + docker_host)
    client = docker.DockerClient(base_url=docker_host)

    # all the json records will be written here
    all_service_data = []

    # the results of the service API query
    service_list_result = []

    # apply filter if specified
    if service_filter is not None:
        service_list_result = client.services.list(filters=json.loads(service_filter))
    else:
        service_list_result = client.services.list()

    # process all found results
    for service in service_list_result:
        service_data = getServiceData(client,swarm_name,service.attrs['ID'])
        all_service_data.append(service_data)


    # to json
    if output_filename is not None:
        with open(output_filename, 'w') as outfile:
            json.dump(all_service_data, outfile, indent=4)
            logging.info("Output written to: " + output_filename)
    else:
        print()
        print(json.dumps(all_service_data,indent=4))

    print()


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--output-filename', dest='output_filename', required=False, default="swarmstatedb.json")
    parser.add_argument('-d', '--swarm-info-repo-root', dest='swarm_info_repo_root', required=True)
    parser.add_argument('-s', '--swarm-name', dest='swarm_name', required=True)
    parser.add_argument('-f', '--service-filter', dest='service_filter', required=False, help="i.e. '{\"name\":\"my-app\"}' Valid filters: id, name , label and mode")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")
    parser.add_argument('-l', '--log-file', dest='log_file', default=None, help="Path to log file, default None, STDOUT")

    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    generate(args.swarm_name,args.service_filter,args.swarm_info_repo_root,args.output_filename)
