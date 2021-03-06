#!/usr/bin/env python

__author__ = "bitsofinfo"

import random
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
import logging
import socket
import base64
import time
from multiprocessing import Pool, Process
from jinja2 import Template
from urllib.parse import urlparse

# De-deuplicates a list of objects, where the value is the same
def dedup(list_of_objects):
    to_return = []
    seen = set()
    for obj in list_of_objects:
        asjson = json.dumps(obj, sort_keys=True)
        if asjson not in seen:
            to_return.append(obj)
            seen.add(asjson)
    return to_return;

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
    response_data = {'as_string':None,'as_object':None}
    try:
        response_str = response.read().decode('utf-8')
        response_data['as_string'] = response_str
        try:
            response_obj = json.loads(response_str)
            response_data['as_object'] = response_obj
        except:
            response_data['as_string'] = response_str
    except Exception as e:
        response_data['as_string'] = "body read failed: " + str(sys.exc_info())
        logging.exception("readHTTPResponse() Exception parsing body")

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

def calcFailPercentage(total_fail,total_ok):
    if (total_ok == 0 and total_fail == 0):
        return 0

    total = (total_fail+total_ok)
    return ((total_fail/total)*100)

def processResponse(service_check_def,
                    service_record,
                    ms,
                    response,
                    attempts_failed,
                    distinct_failure_codes,
                    distinct_failure_errors,
                    attempt_count,
                    dns_lookup_result):

    # hc/service_check (health check for short)
    hc = service_check_def

    # attempt to parse the response
    response_data = readHTTPResponse(response)

    # what is "success"?!
    success_status_codes = [200]
    success_body_evaluator = None
    if 'is_healthy' in hc:
        success_status_codes = hc['is_healthy']['response_codes']
        if 'body_evaluator' in hc['is_healthy']:
            success_body_evaluator = hc['is_healthy']['body_evaluator']


    # lets actually check if the response is legit...
    response_is_healthy = False
    response_unhealthy_reason = None
    if response.getcode() in success_status_codes:

        # handle evaluator..
        if success_body_evaluator is not None:

            if success_body_evaluator['type'] == "contains":
                if success_body_evaluator["value"] in response_data['as_string']:
                    response_is_healthy = True
                else:
                    response_unhealthy_reason = "body_evaluator[contains] failed, did not find: '"+success_body_evaluator["value"]+"' in resp. body"

            elif success_body_evaluator['type'] == "jinja2":
                t = Template(success_body_evaluator["template"])
                x = t.render(response_data=response_data,response_code=response.getcode(),service_record=service_record)
                if '1' in x:
                    response_is_healthy = True
                else:
                    response_unhealthy_reason = "body_evaluator[jinja2] failed, template returned 0 (expected 1)"

        else:
            response_is_healthy = True

    # status code invalid
    else:
        response_unhealthy_reason = "response status code:" + str(response.getcode()) + ", is not in 'success_status_codes'"

    # formulate our result object
    if (response_is_healthy):
        hc['result'] = { "success":True,
                         "code":response.getcode(),
                         "ms":ms,
                         "attempts":attempt_count,
                         "response": response_data,
                         "headers": response.getheaders(),
                         "dns":dns_lookup_result,
                         "attempts_failed":attempts_failed}
        return

    # failed...
    else:
        # create base result object
        hc['result'] = { "success":False,
                         "attempts": attempt_count}

        # attributes specific to the attempt
        attempt_entry = { "ms":ms,
                          "response": response_data,
                          "headers": response.getheaders(),
                          "dns":dns_lookup_result,
                          "error":response_unhealthy_reason,
                          "code":response.getcode()}

        # record in attempts_failed
        attempts_failed.append(attempt_entry)
        distinct_failure_codes.append(response.getcode())
        distinct_failure_codes = dedup(distinct_failure_codes)
        distinct_failure_errors.append(response_unhealthy_reason)
        distinct_failure_errors = dedup(distinct_failure_errors)

        # merge the attempt_entry props into result object
        # as we always store the most recent one at the top level
        hc['result'].update(attempt_entry)

        # add the current list of attempt errors to result object
        hc['result']['attempts_failed'] = attempts_failed
        hc['result']['distinct_failure_codes'] = distinct_failure_codes
        hc['result']['distinct_failure_errors'] = distinct_failure_errors



def execServiceCheck(service_record_and_health_check):

    max_retries = service_record_and_health_check['max_retries']

    hc = service_record_and_health_check['health_check']
    service_record = service_record_and_health_check['service_record']
    sleep_seconds = int(service_record_and_health_check['sleep_seconds'])

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


        logging.debug("Checking: " + hc['method'] + " > "+ hc['url'] + " hh:" + host_header_val_4log)

        request = urllib.request.Request(hc['url'],headers=headers,method=hc['method'],data=body_bytes)

        curl_cmd = "curl -v --retry "+str(retries)+" -k -m " + str(hc['timeout']) + " -X "+hc['method']+" " + curl_header + curl_data +  hc['url']
        hc['curl'] = curl_cmd

    except Exception as e:
        logging.exception("execServiceCheck() exception:")
        hc['result'] = { "success":False,
                         "ms":0,
                         "attempts":0,
                         "error": str(sys.exc_info()[:2])}
        return service_record_and_health_check

    # ok now do the attempts based on configured retries
    attempt_count = 0
    attempts_failed = []
    distinct_failure_codes = []
    distinct_failure_errors = []
    dns_lookup_result = None
    while (attempt_count < retries):

        try:
            attempt_count += 1
            hc['result'] = { "success":False }

            if attempt_count > 1:
                logging.debug("retrying: " + hc['url'])

            # log what it resolves to...
            dns_lookup_result = None
            try:
                parsed = urlparse(hc['url'])
                lookup = parsed.netloc.split(":")[0]
                dns_lookup_result = socket.gethostbyname(lookup)
            except Exception as e:
                dns_lookup_result = str(sys.exc_info()[:2])

            # do the request
            try:
                start = datetime.datetime.now()
                response = urllib.request.urlopen(request,timeout=hc['timeout'],context=sslcontext)

            except urllib.error.HTTPError as httperror:
                response = httperror

            ms = round((datetime.datetime.now() - start).total_seconds() * 1000,0)

            # process the response
            processResponse(hc,service_record,ms,response,
                            attempts_failed,
                            distinct_failure_codes,
                            distinct_failure_errors,
                            attempt_count,
                            dns_lookup_result)

            # if it was successful, exit loop
            if hc['result']['success']:
                break


        except Exception as e:
            ms = (datetime.datetime.now() - start).total_seconds() * 1000

            hc['result'] = { "success":False,
                             "attempts":attempt_count }

            # attributes specific to the attempt
            attempt_entry = { "ms":ms,
                              "dns":dns_lookup_result,
                              "error":str(sys.exc_info()[:2])}

            distinct_failure_errors.append(attempt_entry['error'])
            distinct_failure_errors = dedup(distinct_failure_errors)

            # record in attempts_failed
            attempts_failed.append(attempt_entry)

            # merge the attempt_entry props into result object
            # as we always store the most recent one at the top level
            hc['result'].update(attempt_entry)

            # add the current list of attempt errors to result object
            hc['result']['attempts_failed'] = attempts_failed
            hc['result']['distinct_failure_codes'] = distinct_failure_codes
            hc['result']['distinct_failure_errors'] = distinct_failure_errors

        # finally, sleep after every attempt IF configured to do so...
        finally:
            if sleep_seconds > 0:
                tmp_sleep = random.randint(0,sleep_seconds)
                time.sleep(int(tmp_sleep))

    return service_record_and_health_check


# Does the bulk of the work
def execute(input_filename,output_filename,output_format,maximum_retries,job_id,job_name,layers_to_process_str,threads,tags,stdout_result,fqdn_filter,sleep_seconds):

    # thread pool to exec tasks
    exec_pool = None

    try:
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

        # init pool
        exec_pool = Pool(threads)

        # instantiate the client
        logging.debug("Reading layer check db from: " + input_filename)

        # where we will store our results
        global_results_db = {'id':job_id,
                             'name':job_name,
                             'tags':tags,
                             'metrics': {'health_rating':0,
                                       'total_fail':0,
                                       'total_ok':0,
                                       'total_skipped_no_replicas':0,
                                       'avg_resp_time_ms': 0,
                                       'total_req_time_ms': 0,
                                       'retry_percentage':0,
                                       'fail_percentage':0,
                                       'total_attempts': 0,
                                       'total_skipped': 0,
                                       'failed_attempt_stats' : {},
                                       'layer0':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}, 'failed_attempt_stats' : {}},
                                       'layer1':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}, 'failed_attempt_stats' : {}},
                                       'layer2':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}, 'failed_attempt_stats' : {}},
                                       'layer3':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}, 'failed_attempt_stats' : {}},
                                       'layer4':{'health_rating':0, 'total_ok':0, 'total_fail':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_skipped': 0, 'failures':{}, 'failed_attempt_stats' : {}},
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
                                                 'fail_percentage':0,
                                                 'total_attempts': 0,
                                                 'total_skipped': 0,
                                                 'failed_attempt_stats' : {},
                                                 'layer0': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0, 'failed_attempt_stats' : {}},
                                                 'layer1': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0, 'failed_attempt_stats' : {}},
                                                 'layer2': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0, 'failed_attempt_stats' : {}},
                                                 'layer3': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0, 'failed_attempt_stats' : {}},
                                                 'layer4': {'health_rating':0, 'avg_resp_time_ms': 0, 'total_fail':0, 'total_ok':0, 'retry_percentage':0, 'fail_percentage':0, 'total_attempts': 0, 'total_req_time_ms':0, 'failed_attempt_stats' : {}} },
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
            for layer in service_record['service_checks']:

                skip_layer = True
                for l in layers_to_process:
                    if str(l) in layer:
                        skip_layer = False
                        break

                # if skipping
                if skip_layer:
                    continue

                # tag relevant?
                skipped_service_checks = []
                executable_service_checks = [] # note this is array of dicts

                fqdn_re_filter = None
                if fqdn_filter:
                    fqdn_re_filter = re.compile(fqdn_filter,re.M|re.I)

                for hc in service_record['service_checks'][layer]:

                    hc_executable = True
                    no_match_reason = None

                    # check against tags?
                    if tags and len(tags) > 0:
                        if 'tags' in hc and hc['tags'] is not None:
                            if not listContainsTokenIn(tags,hc['tags']):
                                hc_executable = False
                                no_match_reason = "tags"
                        else:
                            hc_executable = False
                            no_match_reason = "tags"

                    # check against fqdn filter?
                    if fqdn_re_filter:
                        if not fqdn_re_filter.match(hc['url']):
                            hc_executable = False
                            no_match_reason = "fqdn_re_filter"

                    if hc_executable:
                        executable_service_checks.append({'service_record':service_record,'health_check':hc,'max_retries':max_retries,'sleep_seconds':sleep_seconds})
                    else:
                        hc['result'] = { "success":True,
                                          "ms":0,
                                          "attempts":0,
                                          "skipped":True,
                                          "msg":"does not match " + str(no_match_reason)}
                        skipped_service_checks.append(hc)

                # ok here we dump all the service check records
                # to be executed concurrently in the pool
                # which returns a copy...
                executable_service_checks = exec_pool.map(execServiceCheck,executable_service_checks)

                # and we now replace it w/ the result which is now decorated with results
                service_record['service_checks'][layer] = []
                for item in executable_service_checks:
                    service_record['service_checks'][layer].append(item['health_check'])

                # +... the ones we skipped...
                service_record['service_checks'][layer].extend(skipped_service_checks)

                # process each result record updating counters
                for service_check_record in service_record['service_checks'][layer]:

                    # get the individual result
                    check_result = service_check_record['result']

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

                    # bump stats for all attempt information
                    # this is relevant regardless of success/fail
                    if 'attempts_failed' in check_result:
                        for attempt_error in check_result['attempts_failed']:
                            failure_reason = ""
                            if 'code' in attempt_error:
                                failure_reason = str(attempt_error['code'])
                            if 'error' in attempt_error:
                                failure_reason += " - " + attempt_error['error']

                            if len(failure_reason) > 0:
                                metrics_2_update = [service_metrics,service_metrics[layer],global_metrics,global_metrics[layer]]
                                for metric_2_update in metrics_2_update:
                                    failed_attempt_stats = metric_2_update['failed_attempt_stats']
                                    healthcheck_url = service_check_record['url']

                                    if healthcheck_url not in failed_attempt_stats:
                                        failed_attempt_stats[healthcheck_url] = {}

                                    url_stats = failed_attempt_stats[healthcheck_url]
                                    if failure_reason not in url_stats:
                                        url_stats[failure_reason] = 0
                                    url_stats[failure_reason] += 1

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
                        if 'curl' in service_check_record:
                            if service_check_record['curl'] not in service_failure_summary[error_result_key]['curls']:
                                service_failure_summary[error_result_key]['curls'].append(service_check_record['curl'])

                    # check result is OK!
                    else:
                        service_results_db['metrics'][layer]['total_ok'] += 1
                        service_results_db['metrics']['total_ok'] += 1
                        global_metrics[layer]['total_ok'] += 1
                        global_metrics['total_ok'] += 1

                # end loop of layer specific checks
                if len(executable_service_checks) > 0:
                    layer_total_fail = service_metrics[layer]['total_fail'];
                    layer_total_ok = service_metrics[layer]['total_ok'];
                    layer_total_attempts = service_metrics[layer]['total_attempts'];

                    global_layer_total_ok = global_metrics[layer]['total_ok']
                    global_layer_total_fail = global_metrics[layer]['total_fail']

                    service_metrics[layer]['avg_resp_time_ms'] = service_metrics[layer]['total_req_time_ms'] / len(executable_service_checks)
                    service_metrics[layer]['health_rating'] = calcHealthRating(layer_total_fail,layer_total_ok)
                    service_metrics[layer]['retry_percentage'] = calcRetryPercentage(layer_total_attempts,layer_total_fail,layer_total_ok)
                    service_metrics[layer]['fail_percentage'] = calcFailPercentage(layer_total_fail,layer_total_ok)
                    global_metrics[layer]['health_rating'] = calcHealthRating(global_layer_total_fail,global_layer_total_ok)
                    global_metrics[layer]['retry_percentage'] = calcRetryPercentage(global_metrics[layer]['total_attempts'],global_layer_total_fail,global_layer_total_ok)
                    global_metrics[layer]['fail_percentage'] = calcFailPercentage(global_layer_total_fail,global_layer_total_ok)

            # end loop over all layers
            service_total_processed = (service_metrics['total_fail']+service_metrics['total_ok'])
            if service_total_processed > 0:
                service_metrics['avg_resp_time_ms'] = service_metrics['total_req_time_ms'] / service_total_processed
            service_metrics['health_rating'] = calcHealthRating(service_metrics['total_fail'],service_metrics['total_ok'])
            service_metrics['retry_percentage'] = calcRetryPercentage(service_metrics['total_attempts'],service_metrics['total_fail'],service_metrics['total_ok'])
            service_metrics['fail_percentage'] = calcFailPercentage(service_metrics['total_fail'],service_metrics['total_ok'])


            # overall global metrics
            global_total_ok = global_metrics['total_ok']
            global_total_fail = global_metrics['total_fail']
            global_total = (global_total_ok + global_total_fail)
            global_metrics['total_req_time_ms'] += service_metrics['total_req_time_ms']

            if global_total > 0 and global_metrics['total_req_time_ms'] > 0:
                global_metrics['avg_resp_time_ms'] = global_metrics['total_req_time_ms'] / global_total

            global_metrics['health_rating'] = calcHealthRating(global_total_fail,global_total_ok)
            global_metrics['retry_percentage'] = calcRetryPercentage(global_metrics['total_attempts'],global_total_fail,global_total_ok)
            global_metrics['fail_percentage'] = calcFailPercentage(global_total_fail,global_total_ok)


        # to json
        if output_filename is not None:
            with open(output_filename, 'w') as outfile:
                if output_format == 'json':
                    json.dump(global_results_db, outfile, indent=4)
                else:
                    yaml.dump(global_results_db, outfile, default_flow_style=False)

                logging.debug("Output written to: " + output_filename)


        # also to stdout?
        if stdout_result:
            print()
            if output_format == 'json':
                print(json.dumps(global_results_db,indent=4))
            else:
                yaml.dump(global_results_db, outfile, default_flow_style=False)

        print()


    # end main wrapping try
    except Exception as e:
        logging.exception("Error in servicechecker.execute()")

    finally:
        try:
            if exec_pool is not None:
                exec_pool.close()
                exec_pool.terminate()
                exec_pool = None
                logging.debug("Pool closed and terminated")
        except:
            logging.exception("Error terminating, closing pool")

###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="servicechecksdb.json", help="Filename of layer check check database, default: 'servicechecksdb.json'")
    parser.add_argument('-o', '--output-filename', dest='output_filename', default="servicecheckerdb.json", help="Output filename, default: 'servicecheckerdb.json'")
    parser.add_argument('-f', '--output-format', dest='output_format', default="json", help="json or yaml, default 'json'")
    parser.add_argument('-r', '--max-retries', dest='max_retries', default=3, help="maximum retries per check, overrides service-state service check configs, default 3")
    parser.add_argument('-n', '--job-name', dest='job_name', default="no --job-name specified", help="descriptive name for this execution job, default 'no --job-name specified'")
    parser.add_argument('-j', '--job-id', dest='job_id', help="unique id for this execution job, default: None")
    parser.add_argument('-l', '--layers', nargs='+', help="Space separated list of health check layer numbers to process, i.e. '0 1 2 3 4' etc, default None, ie all")
    parser.add_argument('-g', '--tags', nargs='+', help="Space separated list health check tags to process, default None (i.e. all)")
    parser.add_argument('-t', '--threads', dest='threads', default=30, help="max threads for processing checks, default 30, higher = faster completion, adjust as necessary to avoid DOSing...")
    parser.add_argument('-S', '--sleep-seconds', dest='sleep_seconds', default=0, help="The max amount of time to sleep between all attempts for each service check; if > 0, the actual sleep will be a random time from 0 to this value. Default 0")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")
    parser.add_argument('-b', '--log-file', dest='log_file', default=None, help="Path to log file, default None, STDOUT")
    parser.add_argument('-z', '--stdout-result', action='store_true', help="print results to STDOUT in addition to --output-filename on disk")
    parser.add_argument('-e', '--fqdn-filter', dest='fqdn_filter', default=None, help="Regex filter to limit which FQDNs actually get checked across any --layers being checked. Default None")

    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    max_retries = int(args.max_retries)

    execute(args.input_filename,args.output_filename,args.output_format,max_retries,args.job_id,args.job_name,args.layers,args.threads,args.tags,args.stdout_result,args.fqdn_filter,args.sleep_seconds)
