#!/usr/bin/env python

__author__ = "bitsofinfo"

import json
import pprint
import re
import argparse
import getopt, sys
import ssl
import datetime
import logging
import swarmstatedb
import servicechecksdb
import servicechecker
import servicecheckerreport
import os
import time


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
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")
    parser.add_argument('-e', '--log-file', dest='log_file', default=None, help="Path to log file, default None, STDOUT")
    parser.add_argument('-p', '--stdout-servicecheckerreport-result', action='store_true', help="print servicecheckerreport.md output to STDOUT in addition to file")
    parser.add_argument('-z', '--stdout-servicechecker-result', action='store_true', help="print servicechecker raw results to STDOUT in addition to disk")


    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime


    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    job_name = args.swarm_name+"-"+args.job_name
    job_id = timestamp+"-"+job_name
    output_dir = args.output_dir+"/"+job_id+"/"
    if not os.path.exists(os.path.dirname(output_dir)):
        os.makedirs(os.path.dirname(output_dir))

    path_prefix = output_dir+job_id + "_"

    # generate service state db
    logging.info("Invoking swarmstatedb.generate().....")
    swarmstatedb_file = path_prefix+"01_swarmstatedb.json"
    swarmstatedb.generate(args.swarm_name,args.service_filter,args.swarm_info_repo_root,swarmstatedb_file)

    # generate layer checks db
    logging.info("Invoking servicechecksdb.generate().....")
    servicechecksdb_file = path_prefix+"02_servicechecksdb.json"
    servicechecksdb.generate(swarmstatedb_file,args.swarm_info_repo_root,args.service_state_repo_root,servicechecksdb_file,args.layers,args.tags)

    # execute actual checks
    logging.info("Invoking servicechecker.execute().....")
    servicecheckerdb_file = path_prefix+"03_servicecheckerdb.json"
    servicechecker.max_retries = args.max_retries
    servicechecker.execute(servicechecksdb_file,servicecheckerdb_file,"json",args.max_retries,job_id,job_name,args.layers,args.threads,args.tags,args.stdout_servicechecker_result)

    # make the report
    logging.info("Invoking servicecheckerreport.execute().....")
    servicecheckereport_file = path_prefix+"04_servicecheckerreport.md"
    servicecheckerreport.generate(servicecheckerdb_file,servicecheckereport_file,args.verbose,args.stdout_servicecheckerreport_result)
