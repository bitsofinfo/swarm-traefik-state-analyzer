#!/usr/bin/env python

__author__ = "bitsofinfo"

import json
import pprint
import re
import argparse
import getopt, sys
import yaml
import io

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

###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="check-health-curl-db.json", help="Filename of health check result database")
    parser.add_argument('-o', '--output-filename', dest='output_filename', default="report.md")
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    # output for report
    report_str = io.StringIO()

    # output for curls
    curls_str = io.StringIO()

    # instantiate the client
    report_str.write("\n")
    report_str.write("Reading health check results db: " + args.input_filename +"\n")
    report_str.write("\n")

    # Load the docker swarm service json database
    with open(args.input_filename) as f:
        health_result_db = json.load(f)

    db_metrics = health_result_db['metrics']

    report_str.write("----------------------------------------------------------\n")
    report_str.write("Overall: " + fo(None,db_metrics) + "\n")
    report_str.write("----------------------------------------------------------\n")
    report_str.write(" - layer0: via swarm direct:   " + fo("0",db_metrics) +"\n")
    report_str.write(" - layer1: via traefik direct: " + fo("1",db_metrics) +"\n")
    report_str.write(" - layer2: via load balancers: " + fo("2",db_metrics) +"\n")
    report_str.write(" - layer3: via normal fqdns :  " + fo("3",db_metrics) +"\n")
    report_str.write("----------------------------------------------------------\n")
    report_str.write("\n")

    for service_result in health_result_db['service_results']:

        service = service_result['service_record']

        if service['replicas'] == 0:
            continue

        service_metrics = service_result['metrics']

        curr_prev_next = "?"
        if 'current' in service['context_version']:
            curr_prev_next = "current"
        elif 'previous' in service['context_version']:
            curr_prev_next = "previous"
        elif 'next' in service['context_version']:
            curr_prev_next = "next"

        report_str.write("----------------------------------------------------------\n")
        report_str.write(service['name']+"\n")
        report_str.write("    " +str(r(service_metrics['health_rating']))+"% ("+str(service['replicas'])+") ("+curr_prev_next+") "+ str(r(service_metrics['avg_resp_time_ms']))+"ms\n")
        report_str.write("----------------------------------------------------------\n")

        for l in range(0,4):
            layer = "layer"+str(l)
            report_str.write(" - l"+str(l)+": " + fo(str(l),service_metrics)+"\n")

            if service['name'] in db_metrics[layer]['failures']:
                failinfo = db_metrics[layer]['failures'][service['name']]
                for reason in failinfo:
                    details = failinfo[reason]
                    report_str.write("      ("+str(details['total'])+"): " + reason +"\n")
                    if args.verbose:
                        for curl in details['curls']:
                            report_str.write("          " + curl +"\n")


        report_str.write("\n")

    report_str.write("\n")

    report_str.write("Exhaustive results details are located in --> " + args.input_filename +"\n")

    if args.output_filename is not None:
        report_str.write("A copy of this report has been written to --> " + args.output_filename +"\n")

    report_string = report_str.getvalue();
    report_str.close()

    print(report_string)

    if args.output_filename is not None:
        with open(args.output_filename, 'w') as outfile:
            outfile.write("```\n"+report_string+"\n```")
