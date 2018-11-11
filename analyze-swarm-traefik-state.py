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
import testsslcmdsgenerator
import os
import time
import shutil
from logging.handlers import TimedRotatingFileHandler


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-j', '--job-name', dest='job_name', help="descriptive name for this execution", required=True)
    parser.add_argument('-d', '--swarm-info-repo-root', dest='swarm_info_repo_root', required=True, help="dir that anywhere in its subdirectories contains `[swarm-name].yml` yaml config files")
    parser.add_argument('-s', '--service-state-repo-root', dest='service_state_repo_root', required=True, help="dir that anywhere in its subdirectories contains `service-state.yml` yaml config files")
    parser.add_argument('-n', '--swarm-name', dest='swarm_name', required=True, help="The logical name of the swarm name you want to grab service state from, i.e. the [swarm-name].yml file to consume")
    parser.add_argument('-f', '--service-filter', dest='service_filter', required=False, help="i.e. '{\"name\":\"my-app\"}' Valid filters: id, name , label and mode, default None i.e all ")
    parser.add_argument('-o', '--output-dir', dest='output_dir', default="output", help="Directory where all output generated will be placed under, default 'output'")
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose output for servicecheckerreport, default False")
    parser.add_argument('-l', '--layers', nargs='+', help="Space separated list of layer checks to generate i.e '0 1 2 3 4', default all")
    parser.add_argument('-g', '--tags', nargs='+', default=["health"], help="Space separated list of health check tags to include i.e 'health tag1 tag2 etc', default 'health'")
    parser.add_argument('-a', '--fqdn-filter', dest='fqdn_filter', default=None, help="Regex filter to limit which FQDNs are included in service checks for all --layers being checked, default None")
    parser.add_argument('-t', '--threads', dest='threads', default=30, help="max threads for processing checks, default 30, higher = faster completion, adjust as necessary to avoid DOSing...")
    parser.add_argument('-S', '--sleep-seconds', dest='sleep_seconds', default=0, help="The max amount of time to sleep between all attempts for each service check; if > 0, the actual sleep will be a random time from 0 to this value, default 0")
    parser.add_argument('-r', '--max-retries', dest='max_retries', default=3, help="maximum retries per check, overrides service-state service check configs, default 3")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")
    parser.add_argument('-e', '--log-stdout', action='store_true', help="Log to STDOUT, if not present will create logfile under --output-dir")
    parser.add_argument('-p', '--stdout-servicecheckerreport-result', action='store_true', help="print servicecheckerreport.md output to STDOUT in addition to file, default False")
    parser.add_argument('-z', '--stdout-servicechecker-result', action='store_true', help="print servicechecker raw results to STDOUT in addition to disk, default False")
    parser.add_argument('-m', '--daemon', action='store_true', help="Run as a long lived process, re-analyzing per interval settings, if omitted, will run 1x and exit")
    parser.add_argument('-q', '--daemon-interval-seconds', default=300, help="When in daemon mode, how long to sleep between runs, default 300")
    parser.add_argument('-c', '--daemon-interval-randomize', action='store_true', help="When in daemon mode, if enabled, will randomize the sleep between --daemon-interval-seconds and (--daemon-interval-seconds X 2), default False")
    parser.add_argument('-y', '--pre-analyze-script-path', default=None, help="Optional, path to executable/script that will be invoked prior to starting any analysis. No arguments, STDOUT captured and logged. If --daemon this will be invoked at the start of each iteration.")
    parser.add_argument('-u', '--retain-output-hours', default=1, help="Optional, default 1, the number of hours of data to retain, purges output dirs older than this time threshold")
    parser.add_argument('-w', '--service-name-exclude-regex', dest='service_name_exclude_regex', help="Optional, to further refine the set of services by docker service name that are returned via the --service-filter, will exclude any services matching this regex, default None")

    # testsslcmdsgenerator related args
    parser.add_argument('-T', '--gen-testssl-cmds', action='store_true', help='Also produce a testssl.sh.cmds file, optional, default no')
    parser.add_argument('-X', '--gen-testssl-cmds-nomore-than-once-every-ms', type=int, dest='gen_testssl_cmds_nomore_than_once_every_ms', help="Default 86400000 (24h). If --gen-testssl-cmds is specified, don't generate more than ONE testssl.sh.cmds file every N milliseconds. This is here to throttle an upstream consumer of these files (such as https://github.com/bitsofinfo/testssl.sh-processor) as there is often no need to run testssl.sh more than 1x a day for example.", default=86400000)
    parser.add_argument('-A', '--testssl-nonfile-args', dest='testssl_nonfile_args', help="any valid testssl.sh arguments OTHER THAN any of the '--*file' destination arguments. IMPORTANT! Please quote the arguments and provide a single leading SPACE character ' ' following your leading quote prior to any arguments (works around ArgumentParser bug). default ' -S -P -p -U --fast'", default="-S -P -p -U --fast")
    parser.add_argument('-B', '--uri-bucket-filter', dest='uri_bucket_filter', default=None, help="For testssl.sh genreated cmds file: Regex filter to limit which 'unique_entrypoint_uris.[bucketname]' from the --input-filename (servicechecksdb) to actually included in output (buckets are 'via_direct' & 'via_fqdn'). Default: None")
    parser.add_argument('-L', '--limit-via-direct', dest='limit_via_direct', action='store_const', const=True, help="For testssl.sh genreated cmds file: For the 'unique_entrypoint_uris'... 'via_direct' bucket, if this flag is present: limit the total number of uris included to only ONE uri. Given these represent swarm nodes, only one is typically needed to test the cert presented directly by that service")
    parser.add_argument('-C', '--collapse-on-fqdn-filter', dest='collapse_on_fqdn_filter', default=None, help="For testssl.sh genreated cmds file: Capturing Regex filter to match on fqdns from 'unique_entrypoint_uris' that share a common element and limit the test to only one of those matches, the first one found. For wildcard certs, this might be something like '.*(.wildcard.domain)'. Default None")
    parser.add_argument('-M', '--testssl-outputmode', dest='testssl_outputmode', help='For testssl.sh genreated cmds file: for each command generated, the filenames by which the testssl.sh `-*file` output file arguments will be generated. Default `files`. If `dirs1` a unique dir structure will be created based on swarmname/servicename/fqdn/testssloutput__[timestamp].[ext], If `dirs2` a unique dir structure will be created based on fqdn/[timestamp]/swarmname/servicename/testssloutput__fqdn.[ext], if `files` each output file will be in the same `--testssl-outputdir` directory but named such as testssloutput__[swarmname]__[servicename]__[fqdn]__[timestamp].[ext]', default="files")
    parser.add_argument('-D', '--testssl-dir', dest='testssl_dir', help='For testssl.sh genreated cmds file: dir containing the `testssl.sh` script to prepend to the command, default None"', default=None)
    parser.add_argument('-F', '--testssl-output-file-types', dest='testssl_output_file_types', help='For testssl.sh genreated cmds file: The `--*file` argument types that will be included for each command (comma delimited no spaces), default all: "html,json,csv,log"', default="html,json,csv,log")


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

    # for gen_testssl_cmds_nomore_than_once_every_ms handling
    last_testssl_cmds_generated = 0

    # ... now start it up
    runs = 0
    while args.daemon or runs < 1:

        try:

            # cleanup old data
            if args.retain_output_hours is not None:
                now = time.time()
                purge_older_than = now - (float(args.retain_output_hours) * 60 * 60)
                for root, dirs, files in os.walk(job_dir, topdown=False):
                    for _dir in dirs:
                        toeval = job_dir+"/"+_dir
                        dir_timestamp = os.path.getmtime(toeval)
                        if dir_timestamp < purge_older_than:
                            logging.debug("Removing old directory: " +toeval)
                            shutil.rmtree(toeval)


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
            swarmstatedb.generate(args.swarm_name,args.service_filter,args.swarm_info_repo_root,swarmstatedb_file,args.service_name_exclude_regex)

            # generate layer checks db
            logging.info("Invoking servicechecksdb.generate().....")
            servicechecksdb_file = path_prefix+"02_servicechecksdb.json"
            servicechecksdb.generate(swarmstatedb_file,args.swarm_info_repo_root,args.service_state_repo_root,servicechecksdb_file,args.layers,args.tags,args.fqdn_filter)

            # execute actual checks
            logging.info("Invoking servicechecker.execute().....")
            servicecheckerdb_file = path_prefix+"03_servicecheckerdb.json"
            servicechecker.max_retries = args.max_retries
            servicechecker.execute(servicechecksdb_file,servicecheckerdb_file,"json",args.max_retries,job_id,job_name,args.layers,args.threads,args.tags,args.stdout_servicechecker_result,args.fqdn_filter,args.sleep_seconds)

            # make the report
            logging.info("Invoking servicecheckerreport.execute().....")
            servicecheckereport_file = path_prefix+"04_servicecheckerreport.md"
            servicecheckerreport.generate(servicecheckerdb_file,servicecheckereport_file,args.verbose,args.stdout_servicecheckerreport_result)

            # optionally generate testssl.sh commands file
            now_in_ms = int(round(time.time() * 1000))
            ms_since_last_testssl_cmds_generated = (now_in_ms - last_testssl_cmds_generated)
            if args.gen_testssl_cmds and ms_since_last_testssl_cmds_generated >= args.gen_testssl_cmds_nomore_than_once_every_ms:
                logging.info("Invoking testsslcmdsgenerator.execute().....")
                testssl_cmds_file = path_prefix+"05_testssl.sh.cmds"
                testsslcmdsgenerator.execute(servicechecksdb_file,testssl_cmds_file,False,
                                             None,args.testssl_nonfile_args,None,
                                             args.uri_bucket_filter,args.collapse_on_fqdn_filter,args.testssl_outputmode,
                                             args.testssl_dir,'plain',args.limit_via_direct,args.testssl_output_file_types)
                last_testssl_cmds_generated = int(round(time.time() * 1000))

            elif ms_since_last_testssl_cmds_generated < args.gen_testssl_cmds_nomore_than_once_every_ms:
                logging.info("Skipping testsslcmdsgenerator.execute() as ms_since_last_testssl_cmds_generated[%d] < gen_testssl_cmds_nomore_than_once_every_ms[%d]" % (ms_since_last_testssl_cmds_generated,args.gen_testssl_cmds_nomore_than_once_every_ms))


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
