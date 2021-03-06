#!/usr/bin/env python

__author__ = "bitsofinfo"

import json
import pprint
import re
import argparse
import getopt, sys
import yaml
import io
import logging
import time

# r = round
def r(n):
    return round(n,1)

# format-output.. you know... fo
def fo(layer,db):

    l = db
    if layer is not None:
        l = db['layer'+layer]

    resp_time = ""
    if ('avg_resp_time_ms' in l):
        resp_time = str(r(l['avg_resp_time_ms']))+"ms"

    retry_percentage = "r:"+ str(r(l['retry_percentage']))+"%"

    return ("h:"+str(r(l['health_rating']))+ "%").ljust(9) + ("("+str(l['total_fail']) + "/" + str(l['total_ok']+l['total_fail']) +")").ljust(9) + ("a:" + str(l['total_attempts'])).ljust(7) + retry_percentage.ljust(8) + " " +resp_time

# does the bulk of the work
def generate(input_filename,output_filename,verbose,report_stdout):
    # output for report
    report_str = io.StringIO()

    # output for curls
    curls_str = io.StringIO()

    # instantiate the client
    report_str.write("\n")
    report_str.write("SOURCE: " + input_filename +"\n")
    report_str.write("\n")

    report_str.write("  (N) = total replicas\n")
    report_str.write("(f/t) = f:failures, t:total checks\n")
    report_str.write(" XXms = average round trip across checks\n")
    report_str.write("    h = health: percentage of checks that succeeded\n")
    report_str.write("    a = attempts: total attempts per service check\n")
    report_str.write("    r = retries: percentage of attempts > 1 per check\n")
    report_str.write("\n")

    # Load the docker swarm service json database
    with open(input_filename) as f:
        health_result_db = json.load(f)

    db_metrics = health_result_db['metrics']

    report_str.write("----------------------------------------------------------\n")
    report_str.write(health_result_db['name']+"\n")
    report_str.write("  Overall: " + fo(None,db_metrics) + "\n")
    report_str.write("----------------------------------------------------------\n")
    report_str.write(" - layer0: swarm direct:   " + fo("0",db_metrics) +"\n")
    report_str.write(" - layer1: traefik direct: " + fo("1",db_metrics) +"\n")
    report_str.write(" - layer2: load balancers: " + fo("2",db_metrics) +"\n")
    report_str.write(" - layer3: normal fqdns :  " + fo("3",db_metrics) +"\n")
    report_str.write(" - layer4: app proxies :   " + fo("4",db_metrics) +"\n")
    report_str.write("----------------------------------------------------------\n")
    report_str.write("\n")

    for service_result in health_result_db['service_results']:

        service = service_result['service_record']

        if service['replicas'] == 0:
            continue

        service_metrics = service_result['metrics']

        report_str.write("----------------------------------------------------------\n")
        report_str.write(service['name']+"\n")
        report_str.write("    " +str(r(service_metrics['health_rating']))+"% ("+str(service['replicas'])+") "+str(service['context']['tags']).replace('\'','')+" "+ str(r(service_metrics['avg_resp_time_ms']))+"ms\n")
        report_str.write("----------------------------------------------------------\n")

        for l in range(0,5):
            layer = "layer"+str(l)
            report_str.write(" - l"+str(l)+": " + fo(str(l),service_metrics)+"\n")

            if service['name'] in db_metrics[layer]['failures']:
                failinfo = db_metrics[layer]['failures'][service['name']]
                for reason in failinfo:
                    details = failinfo[reason]
                    report_str.write("      ("+str(details['total'])+"): " + reason +"\n")
                    if verbose:
                        for curl in details['curls']:
                            report_str.write("          " + curl +"\n")

        if 'warnings' in service and len(service['warnings']) > 0:
            report_str.write("\n")
            for warning in service['warnings']:
                report_str.write("   (!W): " + warning +"\n")

        report_str.write("\n")

    report_str.write("\n")

    report_str.write("RAW RESULTS --> " + input_filename +"\n")

    if output_filename is not None:
        report_str.write("THE ABOVE ON DISK --> " + output_filename +"\n")

    report_string = report_str.getvalue();
    report_str.close()

    if report_stdout:
        print(report_string)

    if output_filename is not None:
        with open(output_filename, 'w') as outfile:
            outfile.write("```\n"+report_string+"\n```")

###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="servicecheckerdb.json", help="Filename of service check result database, default 'servicecheckerdb.json'")
    parser.add_argument('-o', '--output-filename', dest='output_filename', default="servicecheckerreport.md", help="Filename of the markdown report to generate, default 'servicecheckerreport.md'")
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose details in report, default False")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")
    parser.add_argument('-l', '--log-file', dest='log_file', default=None, help="Path to log file, default None, STDOUT")
    parser.add_argument('-p', '--report-stdout', action='store_true', help="print servicecheckerreport output to STDOUT in addition to file, default False")

    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    generate(args.input_filename,args.output_filename,args.verbose,args.report_stdout)
