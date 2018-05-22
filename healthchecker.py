#!/usr/bin/env python

__author__ = "bitsofinfo"

import json
import pprint
import re
import argparse
import getopt, sys
import yaml
import urllib.request
import urllib.error
import ssl
import datetime
import socket
import base64
from multiprocessing import Pool, Process

#convert string to hex
def toHex(s):
    lst = []
    for ch in s:
        hv = hex(ord(ch)).replace('0x', '')
        if len(hv) == 1:
            hv = '0'+hv
        lst.append(hv)

    return reduce(lambda x,y:x+y, lst)

# for max max_retries
max_retries = None

sslcontext = ssl.create_default_context()
sslcontext.check_hostname = False
sslcontext.verify_mode = ssl.CERT_NONE

def listContainsTokenIn(token_list,at_least_one_must_exist_in):
    found = False
    for token in token_list:
        if token in at_least_one_must_exist_in:
            found = True
    return found

def readHTTPResponse(response):
    response_data = None
    try:
        response_str = response.read().decode('utf-8')
        try:
            response_obj = json.loads(response_str)
            response_data = response_obj
        except:
            response_data = response_str
    except Exception as e:
        response_data = "body read failed: " + str(sys.exc_info())

    return response_data

def calcHealthRating(total_fail,total_ok):
    if (total_ok == 0):
        return 0

    return 100-((total_fail/(total_fail+total_ok))*100)

def calcRetryPercentage(total_attempts,total_fail,total_ok):
    if (total_ok == 0 and total_fail == 0):
        return 0

    total = (total_fail+total_ok);
    diff = abs(total_attempts-total)

    return ((diff/total)*100)


def execHealthCheck(hc):

    hc['result'] = { "success":False }

    # build request
    response = None
    try:
        retries = hc['retries']
        if (max_retries is not None):
            retries = int(max_retries)

        headers = {}
        curl_header = ""

        # seed to blank if not already there
        if not 'headers' in hc or hc['headers'] is None:
            hc['headers'] = []

        # handle specific host header
        host_header_val_4log = "none"
        if hc['host_header'] is not None and hc['host_header'] != '':
            headers = {'Host':hc['host_header']}
            host_header_val_4log = hc['host_header']
            curl_header = "--header 'Host: "+hc['host_header']+"' "

        # handle basic auth
        if 'basic_auth' in hc:
            baheader = "Authorization: Basic: "+ base64.urlsafe_b64encode(hc['basic_auth'].strip().encode("UTF-8")).decode('ascii')
            hc['headers'].append(baheader)

        # handle other headers
        for header in hc['headers']:
            parts = header.split(":");
            key = parts[0].strip()
            val = ''.join(parts[1:]).strip()
            headers[key] = val
            curl_header += "--header '"+key+": "+val+"' "

        # body?
        body_bytes = None
        body_text = None
        curl_data = ""
        if 'body' in hc:
            body_text = hc['body']
            body_bytes = body_text.encode("UTF-8")
            curl_body = body_text.replace("'","\\'")
            curl_data = "-d '"+curl_body+"' "


        print("Checking: " + hc['method'] + " > "+ hc['url'] + " hh:" + host_header_val_4log)

        request = urllib.request.Request(hc['url'],headers=headers,method=hc['method'],data=body_bytes)

        curl_cmd = "curl -v --retry "+str(retries)+" -k -m " + str(hc['timeout']) + " -X "+hc['method']+" " + curl_header + curl_data +  hc['url']
        hc['curl'] = curl_cmd

    except Exception as e:
        hc['result'] = { "success":False,
                         "ms":0,
                         "attempts":0,
                         "error": str(sys.exc_info()[:2])}


    # ok now do the attempts based on configured retries
    attempts = 0
    while (attempts < retries):

        try:
            attempts += 1
            hc['result'] = { "success":False }

            if attempts > 1:
                print("   retryring: " + hc['url'])

            # do the request
            start = datetime.datetime.now()
            response = urllib.request.urlopen(request,timeout=hc['timeout'],context=sslcontext)
            ms = round((datetime.datetime.now() - start).total_seconds() * 1000,0)

            # attempt to parse the response
            response_data = readHTTPResponse(response)

            # what is "success"?!
            success_status_codes = [200]
            success_body_regex = None
            if 'is_healthy' in hc:
                success_status_codes = hc['is_healthy']['response_codes']
                if 'body_regex' in hc['is_healthy']:
                    success_body_regex = hc['is_healthy']['body_regex']


            # lets actually check if the response is legit...
            response_is_healthy = False
            if response.getcode() in success_status_codes:
                if success_body_regex is not None:
                    if success_body_regex in response_data:
                        response_is_healthy = True
                else:
                    response_is_healthy = True

            # formulate our result object
            if (response_is_healthy):
                hc['result'] = { "success":True,
                                 "code":response.getcode(),
                                 "ms":ms,
                                 "attempts":attempts,
                                 "response": response_data,
                                 "headers": response.getheaders(),}
                break
            else:
                hc['result'] = { "success":False,
                                 "code":response.getcode(),
                                 "ms":ms,
                                 "attempts":attempts,
                                 "response": response_data,
                                 "headers": response.getheaders()}

        except Exception as e:
            ms = (datetime.datetime.now() - start).total_seconds() * 1000
            hc['result'] = { "success":False,
                             "ms":ms,
                             "attempts":attempts,
                             "error": str(sys.exc_info()[:2])}
            if type(e) is urllib.error.HTTPError:
                hc['result']['code'] = e.code
                hc['result']['response'] = readHTTPResponse(e)
                hc['result']['headers'] = e.getheaders()


    return hc


# Does the bulk of the work
def execute(input_filename,output_filename,output_format,maximum_retries,job_name,layers_to_process_str,threads,tags):

    layers_to_process = [0,1,2,3,4]
    if layers_to_process_str is not None:
        layers_to_process = list(map(int, layers_to_process_str))

    if tags is None:
        tags = []

    # seed max retries override
    max_retries = int(maximum_retries)

    # mthreaded...
    if (isinstance(threads,str)):
        threads = int(threads)
    exec_pool = Pool(threads)

    # instantiate the client
    print()
    print("Reading layer check db from: " + input_filename)

    # where we will store our results
    global_results_db = {'name':job_name,
                         'tags':tags,
                         'metrics': {'health_rating':0,
                                   'total_fail':0,
                                   'total_ok':0,
                                   'total_skipped_no_replicas':0,
                                   'avg_resp_time_ms': 0,
                                   'total_req_time_ms': 0,
                                   'retry_percentage':0,
                                   'total_attempts': 0,
                                   'total_skipped': 0,
                                   'layer0':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}},
                                   'layer1':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}},
                                   'layer2':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}},
                                   'layer3':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}},
                                   'layer4':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}},
                                 },
                          'service_results': []
                          }

    global_metrics = global_results_db['metrics']

    # open layer check database
    layer_check_db = []
    with open(input_filename) as f:
        layer_check_db = json.load(f)

    # process it all
    for service_record in layer_check_db:

        # our result object
        service_results_db = {'name': service_record['name'],
                                'success': True,
                                'msg': None,
                                'metrics': { 'health_rating':0,
                                             'total_ok':0,
                                             'total_fail':0,
                                             'avg_resp_time_ms' :0,
                                             'total_req_time_ms': 0,
                                             'retry_percentage':0,
                                             'total_attempts': 0,
                                             'total_skipped': 0,
                                             'layer0': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0},
                                             'layer1': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0},
                                             'layer2': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0},
                                             'layer3': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0},
                                             'layer4': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0} },
                                'service_record' : service_record}

        global_results_db['service_results'].append(service_results_db)

        service_metrics = service_results_db['metrics']

        # no replicas? skip
        if service_record['replicas'] == 0:
            global_metrics['total_skipped_no_replicas'] += 1
            service_results_db['success'] = True
            service_results_db['msg'] = "nothing to do: replicas = 0"
            continue



        # we have replicas and lets do some checks
        for layer in service_record['health_checks']:

            skip_layer = True
            for l in layers_to_process:
                if str(l) in layer:
                    skip_layer = False
                    break

            if skip_layer:
                continue

            # tag relevant?
            skipped_health_checks = []
            executable_health_checks = []

            hc_executable = True
            for hc in service_record['health_checks'][layer]:
                if tags and len(tags) > 0:
                    if 'tags' in hc and hc['tags'] is not None:
                        if not listContainsTokenIn(tags,hc['tags']):
                            hc_executable = False
                    else:
                        hc_executable = False

                if hc_executable:
                    executable_health_checks.append(hc)
                else:
                    hc['result'] = { "success":True,
                                      "ms":0,
                                      "attempts":0,
                                      "skipped":True,
                                      "msg":"does not match tags"}
                    skipped_health_checks.append(hc)

            # ok here we dump all the health check records
            # to be executed concurrently in the pool
            # which returns a copy...
            result_tagged_hc_records_for_layer = exec_pool.map(execHealthCheck,executable_health_checks)

            # and we now replace it w/ the result which is now decorated with results
            service_record['health_checks'][layer] = result_tagged_hc_records_for_layer

            # +... the ones we skipped...
            service_record['health_checks'][layer].extend(skipped_health_checks)

            # process each result record updating counters
            for health_check_record in service_record['health_checks'][layer]:

                # get the individual result
                check_result = health_check_record['result']

                # total attempts
                total_attempts = check_result['attempts']
                total_ms = check_result['ms']

                # update the total attempst in global metrics
                global_metrics['total_attempts'] += total_attempts
                global_metrics[layer]['total_attempts'] += total_attempts

                if 'skipped' in check_result and check_result['skipped']:
                    # update the total skipped in global/service metrics
                    global_metrics['total_skipped'] += 1
                    global_metrics[layer]['total_skipped'] += 1
                    service_metrics['total_skipped'] += 1
                    continue

                # service metrics across all layers
                service_metrics['total_attempts'] += total_attempts
                service_metrics['total_req_time_ms'] += total_ms

                # service metrics for this layer
                service_metrics[layer]['total_attempts'] += total_attempts
                service_metrics[layer]['total_req_time_ms'] += total_ms

                # handle failure...
                if not check_result['success']:

                    service_results_db["success"] = False

                    # service metrics bump
                    service_metrics["total_fail"] += 1
                    service_metrics[layer]['total_fail'] += 1

                    # global failures bump
                    global_metrics['total_fail'] += 1
                    global_metrics[layer]['total_fail'] += 1

                    # manage map in global_metrics of failures per layer
                    # that are keyed by docker-service-name[reason]{count,curls}
                    if service_record['name'] in global_metrics[layer]['failures']:
                        service_failure_summary = global_metrics[layer]['failures'][service_record['name']]
                    else:
                        service_failure_summary = {}
                        global_metrics[layer]['failures'][service_record['name']] = service_failure_summary;

                    # Create record for service_failure_summary
                    # for failures based on code/error key w/ count
                    error_result_key = None
                    if 'code' in check_result:
                        error_result_key = str(check_result['code'])

                    if 'error' in check_result:
                        prefix = ""
                        if error_result_key is not None:
                            prefix = error_result_key + " - "

                        error_result_key = prefix+check_result['error']

                    if error_result_key not in service_failure_summary:
                        service_failure_summary[error_result_key] = {'total':0, 'curls':[]}
                    service_failure_summary[error_result_key]['total'] += 1

                    # add curls if to the reason keyed under each service
                    if 'curl' in health_check_record:
                        if health_check_record['curl'] not in service_failure_summary[error_result_key]['curls']:
                            service_failure_summary[error_result_key]['curls'].append(health_check_record['curl'])

                # check result is OK!
                else:
                    service_results_db['metrics'][layer]['total_ok'] += 1
                    service_results_db['metrics']['total_ok'] += 1
                    global_metrics[layer]['total_ok'] += 1
                    global_metrics['total_ok'] += 1

            # end loop of layer specific checks
            if len(result_tagged_hc_records_for_layer) > 0:
                layer_total_fail = service_metrics[layer]['total_fail'];
                layer_total_ok = service_metrics[layer]['total_ok'];
                layer_total_attempts = service_metrics[layer]['total_attempts'];

                global_layer_total_ok = global_metrics[layer]['total_ok']
                global_layer_total_fail = global_metrics[layer]['total_fail']

                service_metrics[layer]['avg_resp_time_ms'] = round(service_metrics[layer]['total_req_time_ms'] / len(result_tagged_hc_records_for_layer),0)
                service_metrics[layer]['health_rating'] = calcHealthRating(layer_total_fail,layer_total_ok)
                service_metrics[layer]['retry_percentage'] = calcRetryPercentage(layer_total_attempts,layer_total_fail,layer_total_ok)
                global_metrics[layer]['health_rating'] = calcHealthRating(global_layer_total_fail,global_layer_total_ok)
                global_metrics[layer]['retry_percentage'] = calcRetryPercentage(global_metrics[layer]['total_attempts'],global_layer_total_fail,global_layer_total_ok)

        # end loop over all layers
        service_total_processed = (service_metrics['total_fail']+service_metrics['total_ok'])
        if service_total_processed > 0:
            service_metrics['avg_resp_time_ms'] = service_metrics['total_req_time_ms'] / service_total_processed
        service_metrics['health_rating'] = calcHealthRating(service_metrics['total_fail'],service_metrics['total_ok'])
        service_metrics['retry_percentage'] = calcRetryPercentage(service_metrics['total_attempts'],service_metrics['total_fail'],service_metrics['total_ok'])


        # overall global metrics
        global_total_ok = global_metrics['total_ok']
        global_total_fail = global_metrics['total_fail']
        global_total = (global_total_ok + global_total_fail)

        for service_result in global_results_db['service_results']:
            global_metrics['total_req_time_ms'] += service_metrics['total_req_time_ms']

        if global_total > 0 and global_metrics['total_req_time_ms'] > 0:
            global_metrics['avg_resp_time_ms'] = global_metrics['total_req_time_ms'] / (global_total_ok + global_total_fail)

        global_metrics['health_rating'] = calcHealthRating(global_total_fail,global_total_ok)
        global_metrics['retry_percentage'] = calcRetryPercentage(global_metrics['total_attempts'],global_total_fail,global_total_ok)


    # to json
    if output_filename is not None:
        with open(output_filename, 'w') as outfile:
            if output_format == 'json':
                json.dump(global_results_db, outfile, indent=4)
            else:
                yaml.dump(global_results_db, outfile, default_flow_style=False)

            print("Output written to: " + output_filename)
    else:
        print()
        if output_format == 'json':
            print(json.dumps(global_results_db,indent=4))
        else:
            yaml.dump(global_results_db, outfile, default_flow_style=False)

    print()


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="healthchecksdb.json", help="Filename of layer check check database")
    parser.add_argument('-o', '--output-filename', dest='output_filename', default="healthcheckerdb.json")
    parser.add_argument('-f', '--output-format', dest='output_format', default="json", help="json or yaml")
    parser.add_argument('-r', '--max-retries', dest='max_retries', default=3, help="maximum retries per check, overrides service-state health check configs")
    parser.add_argument('-n', '--job-name', dest='job_name', default="no --job-name specified", help="descriptive name for this execution job")
    parser.add_argument('-l', '--layers', nargs='+')
    parser.add_argument('-g', '--tags', nargs='+')
    parser.add_argument('-t', '--threads', dest='threads', default=30, help="max threads for processing checks, default 30, higher = faster completion, adjust as necessary to avoid DOSing...")

    args = parser.parse_args()

    max_retries = int(args.max_retries)

    execute(args.input_filename,args.output_filename,args.output_format,max_retries,args.job_name,args.layers,args.threads,args.tags)
