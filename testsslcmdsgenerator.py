#!/usr/bin/env python

__author__ = "bitsofinfo"

import random
import json
import pprint
import re
import argparse
import getopt, sys
import datetime
import logging
import time

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



# Does the bulk of the work
def execute(input_filename,output_filename,stdout_result,fqdn_filter,
    testssl_nonfile_args,testssl_outputdir,uri_bucket_filter,
    collapse_on_fqdn_filter,testssl_outputmode,testssl_dir,output_mode,limit_via_direct,
    testssl_output_file_types):


    try:
        # instantiate the client
        logging.debug("Reading layer check db from: " + input_filename)

        # open layer check database
        layer_check_db = []
        with open(input_filename) as f:
            layer_check_db = json.load(f)

        testssl_sh_commands = ""
        if output_mode == 'sh':
            testssl_sh_commands += "#!/bin/sh\n\n"

        # fqdn filter
        fqdn_re_filter = None
        if fqdn_filter:
            fqdn_re_filter = re.compile(fqdn_filter,re.M|re.I)

        # uri bucket filter
        uri_bucket_re_filter = None
        if uri_bucket_filter:
            uri_bucket_re_filter = re.compile(uri_bucket_filter,re.M|re.I)

        # collapse on fqdn filter
        collapse_on_fqdn_re_filter = None
        collapsed_fqdns_found = []
        if collapse_on_fqdn_filter:
            collapse_on_fqdn_re_filter = re.compile(collapse_on_fqdn_filter,re.M|re.I)

        if testssl_outputdir is None:
            testssl_outputdir = ""

        if testssl_outputdir is not None and len(testssl_outputdir) > 0 and not testssl_outputdir.endswith('/'):
            testssl_outputdir = testssl_outputdir + "/"

        # process it all
        for service_record in layer_check_db:

            # no replicas? skip
            if service_record['replicas'] == 0:
                logging.debug("Skipping, no replicas for: " + service_record['name'])
                continue

            # no key? skip it
            if 'unique_entrypoint_uris' not in service_record:
                logging.debug("Skipping, no unique_entrypoint_uris for: " + service_record['name'])
                continue


            for via_bucket in service_record['unique_entrypoint_uris']:

                # skip buckets we don't want
                if uri_bucket_re_filter:
                    if not uri_bucket_re_filter.match(via_bucket):
                        logging.debug("Skipping " + service_record['name'] + " unique_entrypoint_uris." + via_bucket)
                        continue

                # bucket is ok proceed
                via_direct_uri_count = 0

                for target_url in service_record['unique_entrypoint_uris'][via_bucket]:

                    if limit_via_direct and via_direct_uri_count >= 1:
                        continue

                    if 'https' in target_url:

                        # matches our fqdn filter if present?
                        if fqdn_re_filter:
                            if not fqdn_re_filter.match(target_url):
                                logging.debug("Skipping fqdn_filter no match: " + service_record['name'] + " -> " + target_url)
                                continue

                        # matches our fqdn filter if present?
                        skippable = False
                        if collapse_on_fqdn_re_filter:
                            collapse_fqdn_match = collapse_on_fqdn_re_filter.search(target_url)
                            if collapse_fqdn_match:
                                for i in range(1,20):
                                    try:
                                        collapsed_fqdn_found = collapse_fqdn_match.group(i)
                                    except IndexError:
                                        continue

                                    if collapsed_fqdn_found in collapsed_fqdns_found:
                                        logging.debug("Skipping " + service_record['name'] + " url " + target_url + " as collapse_on_fqdn_filter already has a match for: " + collapsed_fqdn_found)
                                        skippable = True
                                        break
                                    elif collapsed_fqdn_found:
                                        logging.debug("collapse_on_fqdn_filter matched " + service_record['name'] + " url " + target_url + " will use this as our collapsed match for fqdn: " + collapsed_fqdn_found)
                                        collapsed_fqdns_found.append(collapsed_fqdn_found)

                        if skippable:
                            continue

                        # create a unique name for each filename, containing relevant swarm info
                        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
                        fqdn_port = target_url.replace("https://","").replace(":","_")
                        fqdn_only = target_url.replace("https://","")
                        fqdn_only = re.sub(":\d+","",fqdn_only)

                        if testssl_outputmode == 'files':
                            file_arg_target_dir = testssl_outputdir
                            filename = service_record["swarm_name"] + "__" +service_record["name"] + "__" + target_url.replace("https://","").replace(":","_") + "__" + timestamp
                        elif testssl_outputmode == 'dirs1':
                            file_arg_target_dir = testssl_outputdir + service_record["swarm_name"] + "/" +service_record["name"] + "/" + fqdn_port
                            filename = timestamp
                        elif testssl_outputmode == 'dirs2':
                            file_arg_target_dir = testssl_outputdir + fqdn_only + "/" + timestamp + "/" + service_record["swarm_name"] + "/" +service_record["name"]
                            filename = fqdn_port

                        if output_mode == 'sh' and file_arg_target_dir != '':
                            testssl_sh_commands += "mkdir -p " + file_arg_target_dir + "\n"

                        # filenames for all types
                        logfilename = file_arg_target_dir+"/testssloutput__"+filename+".log"
                        csvfilename = file_arg_target_dir+"/testssloutput__"+filename+".csv"
                        htmlfilename = file_arg_target_dir+"/testssloutput__"+filename+".html"
                        jsonfilename = file_arg_target_dir+"/testssloutput__"+filename+".json"

                        # append the actuall flags + file log args for the target_url
                        if testssl_dir is None:
                            testssl_dir = ""

                        testssl_sh_commands += testssl_dir + "testssl.sh " + testssl_nonfile_args

                        if 'log' in testssl_output_file_types:
                            testssl_sh_commands += " --logfile %s " % (logfilename)
                        if 'json' in testssl_output_file_types:
                            testssl_sh_commands += " --jsonfile-pretty %s " % (jsonfilename)
                        if 'csv' in testssl_output_file_types:
                            testssl_sh_commands += " --csvfile %s " % (csvfilename)
                        if 'html' in testssl_output_file_types:
                            testssl_sh_commands += " --htmlfile %s " % (htmlfilename)

                        testssl_sh_commands += "%s\n" % (target_url)

                        # bump up the via direct bucket count
                        if via_bucket == 'via_direct':
                            via_direct_uri_count += 1

        # write it out...
        if output_filename is not None:
            with open(output_filename, 'w') as outfile:
                outfile.write(testssl_sh_commands)
                logging.debug("Output written to: " + output_filename)


        # also to stdout?
        if stdout_result:
            print()
            print(testssl_sh_commands)

        print()


    # end main wrapping try
    except Exception as e:
        logging.exception("Error in testssl_cmds_generator.execute()")


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="servicechecksdb.json", help="input filename of layer check check database, default: 'servicechecksdb.json'")
    parser.add_argument('-o', '--output-filename', dest='output_filename', help="Output filename, default 'testssl_cmds'", default="testssl_cmds")
    parser.add_argument('-M', '--output-mode', dest='output_mode', help="output a `plain` text file of one command per line or a executable `sh` script, default `plain`", default="plain")
    parser.add_argument('-D', '--testssl-dir', dest='testssl_dir', help='dir containing the `testssl.sh` script to prepend to the command, default None"', default=None)
    parser.add_argument('-F', '--testssl-output-file-types', dest='testssl_output_file_types', help='The `--*file` argument types that will be included for each command (comma delimited no spaces), default all: "html,json,csv,log"', default="html,json,csv,log")
    parser.add_argument('-a', '--testssl-nonfile-args', dest='testssl_nonfile_args', help='any valid testssl.sh argument other than any of the "--*file" destination arguments, default "-S -P -p -U --fast"', default="-S -P -p -U --fast")
    parser.add_argument('-d', '--testssl-outputdir', dest='testssl_outputdir', help='for each command generated, the root output dir for all --*file arguments, default None', default=None)
    parser.add_argument('-m', '--testssl-outputmode', dest='testssl_outputmode', help='for each command generated, the filenames by which the testssl.sh `-*file` output file arguments will be generated. Default `files`. If `dirs1` a unique dir structure will be created based on swarmname/servicename/fqdn/testssloutput__[timestamp].[ext], If `dirs2` a unique dir structure will be created based on fqdn/[timestamp]/swarmname/servicename/testssloutput__fqdn.[ext], if `files` each output file will be in the same `--testssl-outputdir` directory but named such as testssloutput__[swarmname]__[servicename]__[fqdn]__[timestamp].[ext]', default="files")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default 'DEBUG'")
    parser.add_argument('-b', '--log-file', dest='log_file', default=None, help="Path to log file, default None which will output to STDOUT")
    parser.add_argument('-z', '--stdout-result', action='store_true', help="print results to STDOUT in addition to output-filename on disk, default off")
    parser.add_argument('-e', '--fqdn-filter', dest='fqdn_filter', default=None, help="Regex filter to limit which FQDNs actually include in the output from 'unique_entrypoint_uris' within (servicechecksdb). Default None")
    parser.add_argument('-B', '--uri-bucket-filter', dest='uri_bucket_filter', default=None, help="Regex filter to limit which 'unique_entrypoint_uris.[bucketname]' from the --input-filename (servicechecksdb) to actually included in output (buckets are 'via_direct' & 'via_fqdn'). Default: None")
    parser.add_argument('-L', '--limit-via-direct', dest='limit_via_direct', action='store_const', const=True, help="For the 'unique_entrypoint_uris'... 'via_direct' bucket, if this flag is present: limit the total number of uris included to only ONE uri. Given these represent swarm nodes, only one is typically needed to test the cert presented directly by that service")
    parser.add_argument('-c', '--collapse-on-fqdn-filter', dest='collapse_on_fqdn_filter', default=None, help="Capturing Regex filter to match on fqdns from 'unique_entrypoint_uris' that share a common element and limit the test to only one of those matches, the first one found. For wildcard certs, this might be something like '.*(.wildcard.domain)'. Default None")

    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    execute(args.input_filename,args.output_filename,args.stdout_result,
        args.fqdn_filter,args.testssl_nonfile_args,args.testssl_outputdir,
        args.uri_bucket_filter,args.collapse_on_fqdn_filter,args.testssl_outputmode,
        args.testssl_dir,args.output_mode,args.limit_via_direct,args.testssl_output_file_types)
