#!/usr/bin/env python

__author__ = "bitsofinfo"

import json
import pprint
import re
import argparse
import getopt, sys
import glob
import yaml
import re

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

# map of  swarm_name -> [props from swarm.yml file]
swarm_name_2_swarm_info = {}

# full set of docker swarm service data loaded up from DB file
docker_service_data_db = []

# Map of  service formal name -> service state
formal_name_2_service_state = {}

# Map of  aliases to the formal name
aliases_2_formal_name = {}


# De-deuplicates a list of objects, where the value for given key is the same
def dedup(list_of_objects):
    to_return = []
    seen = set()
    for obj in list_of_objects:
        asjson = json.dumps(obj, sort_keys=True)
        if asjson not in seen:
            to_return.append(obj)
            seen.add(asjson)
    return to_return;

# Gets subset of items from "all_items" which
# are not equal to other_than_item
def getItemsOtherThan(other_than_item,all_items):
    other_than = []
    for p in all_items:
        if p != other_than_item:
            other_than.append(p)
    return other_than

def listContainsTokenIn(token_list,at_least_one_must_exist_in):
    found = False
    for token in token_list:
        if token in at_least_one_must_exist_in:
            found = True
            break
    return found

# Returns list of service_state.service_checks objects for any applicable
# service_state declared service_port for the specified infrastructure `layer`
# and `docker_service_name_or_traefik_fqdn`
def getServiceChecksForServiceAnyPort(layer,docker_service_name_or_traefik_fqdn,service_state,tags,docker_service_data):
    service_checks = []
    for service_port in service_state["service_ports"]:
        service_checks.extend(getServiceChecksForServicePort(layer,service_port,docker_service_name_or_traefik_fqdn,service_state,tags,docker_service_data))
    return dedup(service_checks)

# Will return a list of service_state.service_checks objects for the specified
# service port, infrastructure layer and docker_service_name_or_traefik_fqdn
#
def getServiceChecksForServicePort(layer,service_port,docker_service_name_or_traefik_fqdn,service_state,tags,docker_service_data):
    to_return = []

    if 'service_ports' not in service_state:
        msg = "MISCONFIG: "+docker_service_name_or_traefik_fqdn+" service-state.yml has no 'service_ports' declared"
        docker_service_data['warnings'].add(msg)
        print(msg)
        return []

    # get the service_port info for the desired service_port
    if not service_port in service_state["service_ports"]:
        msg = "MISCONFIG: "+docker_service_name_or_traefik_fqdn+" service-state.yml declared port: " + str(service_port) + " IS NOT PUBLISHED according to swarm!"
        docker_service_data['warnings'].add(msg)
        print(msg)
        return []

    service_state_port_info = service_state["service_ports"][service_port]

    # lets get all possible service_checks potentially supported for the given port and layer and tags
    service_checks_for_port = getServiceChecksForPort(layer,service_port,service_state['service_checks'],tags)

    # zero, log and return...
    if len(service_checks_for_port) == 0:
        print("No service_checks for: " + docker_service_name_or_traefik_fqdn + " layer:"+str(layer)+ " port:" + str(service_port) + " tags:" + str(tags))
        return []

    # layer 4 is more unique
    # we handle differently as
    # the docker_service_name_or_traefik_fqdn passed
    # here is the docker_service_name and never a fqdn
    # sourced from a traefik label so we can be sure
    # the name we are working with supports both classifiers
    # and contexts per the service naming convention
    if layer == 4:
        for hc in service_checks_for_port:
            can_use_service_checks = False

            if 'classifiers' in hc:
                if not listContainsTokenIn(hc['classifiers'],docker_service_name_or_traefik_fqdn):
                    continue;

            if 'contexts' in hc:
                if not listContainsTokenIn(hc['contexts'],docker_service_name_or_traefik_fqdn):
                    continue;

            to_return.append(hc)


    # For layers 0-3 we need to do more exhaustive checking
    # to determine if the service check is actually relevant
    # for the given docker_service_name_or_traefik_fqdn
    # as the docker_service_name_or_traefik_fqdn itself
    # may or may NOT contain port/classifier information within it
    # (i.e. vanity traefik labels) and we use that to cross check the
    # applicability of that target against the information in the service-check
    # meta-data object
    else:
        # If the service_port is directly and literally specified within the fqdn/docker-service-name
        # we can proceed to further validate if the service-check spec qualifies
        # for this docker_service_name_or_traefik_fqdn
        if (str(service_port) in docker_service_name_or_traefik_fqdn):

            can_use_service_checks = False
            # no classiiers? just apply em
            if 'classifiers' not in service_state_port_info:
                can_use_service_checks = True

            else:
                for classifier in service_state_port_info['classifiers']:
                    if classifier in docker_service_name_or_traefik_fqdn:
                        can_use_service_checks = True

            if can_use_service_checks:
                for hc in service_checks_for_port:

                    # each service check itself can also have a classifier
                    # that further narrows down if the HC is valid
                    if 'classifiers' in hc:
                        if not listContainsTokenIn(hc['classifiers'],docker_service_name_or_traefik_fqdn):
                            can_use_service_checks = False

                    if can_use_service_checks:
                        to_return.append(hc)

        # otherwise we need to fall back to classifiers
        # as they are related to ports and their availability
        else:

            # no classifiers? just apply em
            if 'classifiers' not in service_state_port_info:
                for hc in service_checks_for_port:
                    to_return.append(hc)

            # we have classifiers
            else:

                all_classifiers = []
                all_classifiers.extend(service_state_port_info['classifiers'])
                for hc in service_checks_for_port:
                    if 'classifiers' in hc:
                        all_classifiers.extend(hc['classifiers'])

                # lets go through all classifiers for the service_port we are analyzing
                for classifier in all_classifiers:

                    # if the service_stage port object is flagged as DEFAULT
                    # OR... the fqdn/docker-service-name has the classifier literally in it...
                    # we can proceed...
                    if classifier in docker_service_name_or_traefik_fqdn:

                        #... but before we can proceed we need to ensure that NO OTHER potential
                        # service_stage declared ports are listed in the fqdn/docker-service-name
                        # (note this is due to a bug in current system that generates
                        # traefik labels for ports that are not applicable for the classifier of
                        # the service launched
                        #
                        # TODO: remove this one traefik/fqdn name generation on service creation
                        # takes into account classifiers and ports properly
                        can_use_service_checks = True
                        other_than = list(filter(lambda x: x != service_port, service_state["service_ports"].keys()))
                        for p in other_than:
                            if (str(p) in docker_service_name_or_traefik_fqdn):
                                can_use_service_checks = False
                                break

                        # ok... bag em if we can use them
                        if can_use_service_checks:

                            for hc in service_checks_for_port:
                                # each service check itself can also have a classifier
                                # that further narrows down if the HC is valid
                                if 'classifiers' in hc:
                                    if not listContainsTokenIn(hc['classifiers'],docker_service_name_or_traefik_fqdn):
                                        can_use_service_checks = False

                                if can_use_service_checks:
                                    to_return.append(hc)

    # de-dup and return
    return dedup(to_return)

# Gets all applicable service check objects for the given port
def getServiceChecksForPort(layer,port,service_state_service_checks,tags):
    hcs_toreturn = []

    for hc in service_state_service_checks:
        if port in hc['ports'] and layer in hc['layers']:
            # filter by tags?
            hc_qualifies = True
            if tags and len(tags) > 0: # we have tags we must comply with
                if 'tags' in hc and hc['tags'] is not None:
                    if not listContainsTokenIn(tags,hc['tags']):
                        hc_qualifies = False
                else: # hc record has no tags...
                    hc_qualifies = False

            if hc_qualifies:
                hcs_toreturn.append(hc)

    return hcs_toreturn;

# Constructs a service check entry object for placement in the output-file
#
# layer = the layer
# host_header = if applicable
# url_root = http(s)://fqdn[:port]
# target_container_port = the backend port this servicecheck is ultimately targeting
# servicecheck_info = the 'servicecheck_info' object from service_state.service_checks
# description = arbitrary information string context
def toServiceCheckEntry(layer,host_header,url_root,target_container_port,servicecheck_info,description):
    hc_entry = {}
    hc_entry['layer'] = layer;
    hc_entry['url'] = url_root + servicecheck_info['path']
    hc_entry['target_container_port'] = target_container_port
    hc_entry['host_header'] = host_header
    if 'headers' in servicecheck_info:
        hc_entry['headers'] = servicecheck_info['headers']
    if 'basic_auth' in servicecheck_info:
        hc_entry['basic_auth'] = servicecheck_info['basic_auth']

    if 'body' in servicecheck_info:
        hc_entry['body'] = re.sub("\s+"," ",servicecheck_info['body'])

    if 'is_healthy' in servicecheck_info:
        hc_entry['is_healthy'] = servicecheck_info['is_healthy']
    hc_entry['method'] = servicecheck_info['method']
    hc_entry['timeout'] = servicecheck_info['timeout']
    hc_entry['retries'] = servicecheck_info['retries']
    hc_entry['description'] = description

    if 'tags' in servicecheck_info:
        hc_entry['tags'] = servicecheck_info['tags']

    return hc_entry

# Given a record from docker_service_data_db
# return the relevant  service state data structure
def getServiceState(docker_service_data_record):
    for alias in aliases_2_formal_name:
        if alias in docker_service_data_record['name']:
            return aliases_2_formal_name[alias]
    for formal_name in formal_name_2_service_state:
        if formal_name in docker_service_data_record['name']:
            return formal_name_2_service_state[formal_name]

# Given a logical  "swarm name" (i.e. myswarm2)
# return a list of Docker host FQDN's in that swarm
# levaraging the `swarm_info` component of
# a service state file
def getSwarmHostFQDNs(swarm_name):
    swarm_hosts = []

    swarm_info = swarm_name_2_swarm_info[swarm_name]
    host_info = swarm_info['swarm_host_info']

    host_ceiling = 0

    for n in range(1,(host_info['total_nodes']+1)):
        swarm_hosts.append(host_info['template'].replace("{id}",str(n)))

    return swarm_hosts

# Manages small DB of [swarm_name] -> swarm_name.yml config
# manages the state of `swarm_name_2_swarm_info` structure
# and returns entries from it
# - swarm_info_repo_root: path to directory who contains [my-swarm-name].yml files
# - swarm_name: the logical swarm name you want info for
def getSwarmInfoMap(swarm_info_repo_root,swarm_name):
    if swarm_name not in swarm_name_2_swarm_info:
        for yml_file in glob.iglob(swarm_info_repo_root+"/**/"+swarm_name+".yml", recursive=True):
            with open(yml_file, 'r') as f:
                print("Consuming config from: " + yml_file)
                swarm_name_2_swarm_info_yml = yaml.load(f)
                swarm_name_2_swarm_info[swarm_name] = swarm_name_2_swarm_info_yml

    return swarm_name_2_swarm_info[swarm_name]


# Does the bulk of the work
def generate(input_filename,swarm_info_repo_root,service_state_repo_root,output_filename,layers_to_process_str,tags,minimize_stdout):

    if tags is None:
        tags = []

    layers_to_process = [0,1,2,3,4]
    if layers_to_process_str is not None:
        layers_to_process = list(map(int, layers_to_process_str))

    # instantiate the client
    print()
    print("Reading docker swarm service data from: " + input_filename)
    print("Reading swarm info files from: " + swarm_info_repo_root)
    print("Reading swarm service state YAML files from: " + service_state_repo_root)

    # Load the docker swarm service json database
    with open(input_filename) as f:
        docker_service_data_db = json.load(f)

    # Load up all  service_state.yml files found under
    # we create a larger map of [formal_name] = service_state.yml for each one found
    # and a secondary map for each "alias" -> formal_name
    # to just have a subset of this info in memory
    for yml_file in glob.iglob(service_state_repo_root+"/**/service_state.yml", recursive=True):
        with open(yml_file, 'r') as f:
            service_state_yml = yaml.load(f)
            formal_name_2_service_state[service_state_yml['formal_name']] = service_state_yml
            for alias in service_state_yml['aliases']:
                aliases_2_formal_name[alias] = service_state_yml



    # For every entry in the docker_service_data_db
    # We will create a new entry for the layer check database
    for docker_service_data in docker_service_data_db:

        # docker service name
        docker_service_name = docker_service_data['name']

        # capture the  swarm name
        swarm_name = docker_service_data["swarm_name"]

        # get the  swarm info properties
        swarm_info = getSwarmInfoMap(swarm_info_repo_root,swarm_name)

        # fetch the relevant service_state record
        # for the given docker service data record
        service_state = getServiceState(docker_service_data)

        # setup warnings so mis-configurations can be logged
        docker_service_data['warnings'] = set()

        # copy over some basic info
        docker_service_data['formal_name'] = service_state['formal_name']
        docker_service_data['app_type'] = service_state['app_type']
        docker_service_data['aliases'] = service_state['aliases']

        # Analyze the classifiers and decorate
        # the docker_service_data w/ this additional information
        docker_service_data['classifier'] = None
        if 'classifiers' in service_state:
            for classifier_name in service_state['classifiers']:
                if classifier_name in docker_service_name:
                    docker_service_data['classifier'] = classifier_name
                    break

        # Analyze the contexts/versions and decorate
        # the docker_service_data w/ this additional information
        docker_service_data['context'] = {'name':None,'version':None,'tags':[]}
        for context_name in service_state['contexts']:

            # no need to continue we've already found
            # the service in the context
            #if docker_service_data["context"]["tag"] is not None:
            #    break;

            # if the context-name is even relevant for the target swarm...
            if context_name in swarm_info['contexts']:
                context = service_state['contexts'][context_name]
                if context_name in docker_service_name:
                    docker_service_data['context']['name'] = context_name
                    for version_tag in context['versions']:
                        version_number = context['versions'][version_tag]
                        if version_number != '':
                            if version_number.replace(".","-") in docker_service_name:
                                docker_service_data['context']['tags'].append(version_tag)
                                docker_service_data['context']['version'] = version_number


        # Determine the traefik port based on internal/external
        traefik_port = swarm_info['traefik_swarm_port_internal_https']
        if docker_service_data['int_or_ext'] == 'external':
            traefik_port = swarm_info['traefik_swarm_port_external_https']

        # Determine the load balancer based on internal/external
        load_balancer = swarm_info['swarm_lb_endpoint_internal']
        if docker_service_data['int_or_ext'] == 'external':
            load_balancer = swarm_info['swarm_lb_endpoint_external']


        service_state_servicechecks_info = None
        if 'service_checks' in service_state:
            service_state_servicechecks_info = service_state['service_checks']

        if service_state_servicechecks_info is not None and len(service_state_servicechecks_info) == 0:
            print("No service_checks could be found in service state for: " + docker_service_data['name'] + " skipping...")
            continue;

        # if none were found... skip and move on
        if service_state is None:
            print("No service_state could be found for: " + docker_service_data['name'] + " skipping...")
            continue;


        if docker_service_data['replicas'] == 0:
            continue


        # init service_checks
        docker_service_data['service_checks'] = {
                                                'layer0':[],
                                                'layer1':[],
                                                'layer2':[],
                                                'layer3':[],
                                                'layer4':[]
                                                }



        # layer-0: swarm direct checks
        if 0 in layers_to_process:
            for host in getSwarmHostFQDNs(swarm_name):
                for p in docker_service_data['port_mappings']:
                    # split up docker service record publish/target port
                    swarm_pub_port = int(p.split(":")[0])
                    target_container_port = int(p.split(":")[1])

                    for hc in getServiceChecksForServicePort(0,target_container_port,docker_service_name,service_state,tags,docker_service_data):
                        url = service_state['service_ports'][target_container_port]["protocol"]+"://"+host+":"+str(swarm_pub_port)
                        hc_entry = toServiceCheckEntry(0,None,url,target_container_port,hc,docker_service_name+" swarm service port direct")
                        docker_service_data['service_checks']['layer0'].append(hc_entry)



        # layer-1: traefik checks
        if 1 in layers_to_process:
            for host in getSwarmHostFQDNs(swarm_name):
                for fqdn in docker_service_data['traefik_host_labels']:
                    for hc in getServiceChecksForServiceAnyPort(1,fqdn,service_state,tags,docker_service_data):
                        hc_entry = toServiceCheckEntry(1,fqdn,"https://"+host+":"+str(traefik_port),None,hc,docker_service_name+" via traefik swarm port")
                        docker_service_data['service_checks']['layer1'].append(hc_entry)

        # layer-2: load-balancers
        if 2 in layers_to_process:
            for fqdn in docker_service_data['traefik_host_labels']:
                for hc in getServiceChecksForServiceAnyPort(2,fqdn,service_state,tags,docker_service_data):
                    hc_entry = toServiceCheckEntry(2,fqdn,"https://"+load_balancer,None,hc,docker_service_name+" via load balancer")
                    docker_service_data['service_checks']['layer2'].append(hc_entry)

        # layer-3: straight, FQDN access
        if 3 in layers_to_process:
            for fqdn in docker_service_data['traefik_host_labels']:
                for hc in getServiceChecksForServiceAnyPort(3,fqdn,service_state,tags,docker_service_data):
                    hc_entry = toServiceCheckEntry(3,None,"https://"+fqdn,None,hc,docker_service_name+" via normal fqdn access")
                    docker_service_data['service_checks']['layer3'].append(hc_entry)

        # layer-4: these are custom and vary based on context
        # typically another proxy beyond layer3 so the root url
        # is static in the service check config and tied to the context
        # vs. being calculated like the other layers above
        if 4 in layers_to_process:
            for hc in getServiceChecksForServiceAnyPort(4,docker_service_name,service_state,tags,docker_service_data):
                contexts = hc['contexts']
                for context_name in contexts:
                    if context_name in docker_service_name:
                        for url_root in contexts[context_name]['url_roots']:
                            hc_entry = toServiceCheckEntry(4,None,url_root,None,hc,docker_service_name+" via layer 4 custom: " + url_root)
                            docker_service_data['service_checks']['layer4'].append(hc_entry)


    # to json
    if output_filename is not None:
        with open(output_filename, 'w') as outfile:
            json.dump(docker_service_data_db, outfile, indent=4, cls=SetEncoder)
            print("Output written to: " + output_filename)
    else:
        print()
        print(json.dumps(docker_service_data_db,indent=4))




###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="swarmstatedb.json")
    parser.add_argument('-s', '--service-state-repo-root', dest='service_state_repo_root', required=True)
    parser.add_argument('-d', '--swarm-info-repo-root', dest='swarm_info_repo_root', required=True)
    parser.add_argument('-o', '--output-filename', dest='output_filename', default="servicechecksdb.json")
    parser.add_argument('-l', '--layers', nargs='+')
    parser.add_argument('-g', '--tags', nargs='+', default=["health"])
    parser.add_argument('-x', '--minstdout', action="store_true",help="minimize stdout output")
    args = parser.parse_args()

    generate(args.input_filename,args.swarm_info_repo_root,args.service_state_repo_root,args.output_filename,args.layers,args.tags,args.minstdout)
