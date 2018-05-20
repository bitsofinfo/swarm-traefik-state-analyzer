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
import healthchecksdb
import healthchecker
import healthcheckerreport
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
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-r', '--max-retries', dest='max_retries', default=3, help="maximum retries per check, overrides service-state health check configs")

    args = parser.parse_args()

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    job_name = timestamp+"-"+args.swarm_name+"-"+args.job_name
    output_dir = args.output_dir+"/"+job_name
    if not os.path.exists(os.path.dirname(output_dir+"/")):
        os.makedirs(os.path.dirname(output_dir))

    path_prefix = output_dir+"/"+job_name + "_"

    # generate service state db
    print("\nInvoking swarmstatedb.generate().....")
    swarmstatedb_file = path_prefix+"01_swarmstatedb.json"
    swarmstatedb.generate(args.swarm_name,args.service_filter,args.swarm_info_repo_root,swarmstatedb_file)

    # generate layer checks db
    print("\nInvoking healthchecksdb.generate().....")
    healthchecksdb_file = path_prefix+"02_healthchecksdb.json"
    healthchecksdb.generate(swarmstatedb_file,args.swarm_info_repo_root,args.service_state_repo_root,healthchecksdb_file)

    # execute actual checks
    print("\nInvoking healthchecker.execute().....")
    healthcheckerdb_file = path_prefix+"03_healthcheckerdb.json"
    healthchecker.max_retries = args.max_retries
    healthchecker.execute(healthchecksdb_file,healthcheckerdb_file,"json",args.max_retries,job_name)

    # make the report
    print("\nInvoking healthcheckerreport.execute().....")
    healthcheckereport_file = path_prefix+"04_healthcheckerreport.md"
    healthcheckerreport.generate(healthcheckerdb_file,healthcheckereport_file,args.verbose)
