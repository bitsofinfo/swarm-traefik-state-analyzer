#!/usr/bin/env python

__author__ = "bitsofinfo"

import json
import pprint
import re
import argparse
import getopt, sys
import ssl
import datetime
import swarmstatedb
import servicechecksdb
import servicechecker
import servicecheckerreport
import os


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-j', '--job-name', dest='job_name', help="descriptive name for this execution", required=True)
    parser.add_argument('-d', '--swarm-info-repo-root', dest='swarm_info_repo_root', required=True)
    parser.add_argument('-s', '--service-state-repo-root', dest='service_state_repo_root', required=True)
    parser.add_argument('-n', '--swarm-name', dest='swarm_name', required=True)
    parser.add_argument('-f', '--service-filter', dest='service_filter', required=False, help="i.e. '{\"name\":\"my-app\"}' Valid filters: id, name , label and mode")
    parser.add_argument('-o', '--output-dir', dest='output_dir', default="output")
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose output for servicecheckerreport")
    parser.add_argument('-l', '--layers', nargs='+')
    parser.add_argument('-g', '--tags', nargs='+', default=["health"])
    parser.add_argument('-t', '--threads', dest='threads', default=30, help="max threads for processing checks, default 30, higher = faster completion, adjust as necessary to avoid DOSing...")
    parser.add_argument('-r', '--max-retries', dest='max_retries', default=3, help="maximum retries per check, overrides service-state service check configs")
    parser.add_argument('-x', '--minstdout', action="store_true", help="minimize stdout output")

    args = parser.parse_args()

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    job_name = timestamp+"-"+args.swarm_name+"-"+args.job_name
    output_dir = args.output_dir+"/"+job_name+"/"
    if not os.path.exists(os.path.dirname(output_dir)):
        os.makedirs(os.path.dirname(output_dir))

    path_prefix = output_dir+job_name + "_"

    # generate service state db
    print("\nInvoking swarmstatedb.generate().....")
    swarmstatedb_file = path_prefix+"01_swarmstatedb.json"
    swarmstatedb.generate(args.swarm_name,args.service_filter,args.swarm_info_repo_root,swarmstatedb_file,args.minstdout)

    # generate layer checks db
    print("\nInvoking servicechecksdb.generate().....")
    servicechecksdb_file = path_prefix+"02_servicechecksdb.json"
    servicechecksdb.generate(swarmstatedb_file,args.swarm_info_repo_root,args.service_state_repo_root,servicechecksdb_file,args.layers,args.tags,args.minstdout)

    # execute actual checks
    print("\nInvoking servicechecker.execute().....")
    servicecheckerdb_file = path_prefix+"03_servicecheckerdb.json"
    servicechecker.max_retries = args.max_retries
    servicechecker.execute(servicechecksdb_file,servicecheckerdb_file,"json",args.max_retries,job_name,args.layers,args.threads,args.tags,args.minstdout)

    # make the report
    print("\nInvoking servicecheckerreport.execute().....")
    servicecheckereport_file = path_prefix+"04_servicecheckerreport.md"
    servicecheckerreport.generate(servicecheckerdb_file,servicecheckereport_file,args.verbose,args.minstdout)
