#!/usr/bin/env python

__author__ = "bitsofinfo"

import random
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
from logging.handlers import TimedRotatingFileHandler


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
    parser.add_argument('-e', '--log-stdout', action='store_true', help="Log to STDOUT, if not present will create logfile under --output-dir")
    parser.add_argument('-p', '--stdout-servicecheckerreport-result', action='store_true', help="print servicecheckerreport.md output to STDOUT in addition to file")
    parser.add_argument('-z', '--stdout-servicechecker-result', action='store_true', help="print servicechecker raw results to STDOUT in addition to disk")
    parser.add_argument('-m', '--daemon', action='store_true', help="Run as a long lived process, re-analyzing per interval settings, if omitted, will run 1x and exit")
    parser.add_argument('-q', '--daemon-interval-seconds', default=300, help="When in daemon mode, how long to sleep between runs, default 300")
    parser.add_argument('-c', '--daemon-interval-randomize', action='store_true', help="When in daemon mode, if enabled, will randomize the sleep between --daemon-interval-seconds and (--daemon-interval-seconds X 2)")
    parser.add_argument('-y', '--pre-analyze-script-path', default=None, help="Optional, path to executable/script that will be invoked prior to starting any analysis. No arguments, STDOUT captured and logged. If --daemon this will be invoked at the start of each iteration.")


    args = parser.parse_args()

    job_name = args.swarm_name+"-"+args.job_name
    job_dir = args.output_dir+"/"+job_name+"/"

    if not os.path.exists(os.path.dirname(job_dir)):
        os.makedirs(os.path.dirname(job_dir))

    # log file defaults to this script under output dir
    # unless log_stdout is true
    log_handlers = []
    if not args.log_stdout:
        log_handlers.append(TimedRotatingFileHandler(job_dir+"/analyze-swarm-traefik-state.log",when="m",interval=15,backupCount=48))

    # basic logging config
    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=log_handlers)
    logging.Formatter.converter = time.gmtime


    # ... now start it up
    runs = 0
    while args.daemon or runs < 1:

        try:
            timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            job_id = timestamp+"-"+job_name
            output_dir = job_dir+"/"+job_id+"/"
            if not os.path.exists(os.path.dirname(output_dir)):
                os.makedirs(os.path.dirname(output_dir))

            path_prefix = output_dir+job_id + "_"

            logging.info("Starting analysis, output dir: " + output_dir)

            # invoke pre-analysis script
            if args.pre_analyze_script_path is not None:
                if not os.path.isfile(args.pre_analyze_script_path):
                    logging.info("pre_analyze_script_path does NOT exist!: " + args.pre_analyze_script_path)
                else:
                    try:
                        logging.info("invoking... pre_analyze_script_path: " + args.pre_analyze_script_path)
                        cmd_result=os.popen(args.pre_analyze_script_path).read()
                        logging.info("pre_analyze_script_path invoked OK, output: \n" + cmd_result)
                    except Exception as e:
                        logging.exception("pre_analyze_script_path invocation error")

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


        # catch any error
        except Exception as e:
            logging.exception("Unexpected error in main loop of analyze-swarm-traefik-state.log")

        finally:
            runs += 1

            # sleep
            if args.daemon:
                sleep_seconds = int(args.daemon_interval_seconds)
                if args.daemon_interval_randomize:
                    sleep_seconds = random.randint(sleep_seconds,(sleep_seconds*2))

                logging.debug("Sleeping daemon_interval_seconds: " + str(sleep_seconds))
                time.sleep(int(sleep_seconds))
