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
import base64
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
    collapse_on_fqdn_filter,testssl_outputmode):


    try:
        # instantiate the client
        logging.debug("Reading layer check db from: " + input_filename)

        # open layer check database
        layer_check_db = []
        with open(input_filename) as f:
            layer_check_db = json.load(f)

        testssl_sh_commands = ""

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

        # process it all
        for service_record in layer_check_db:

            # no replicas? skip
            if service_record['replicas'] == 0:
                logging.debug("Skipping, no replicas for: " + service_record['name'])
                continue

            # we have replicas and lets do some checks
            for via_bucket in service_record['unique_entrypoint_uris']:

                # skip buckets we don't want
                if uri_bucket_re_filter:
                    if not uri_bucket_re_filter.match(via_bucket):
                        logging.debug("Skipping " + service_record['name'] + " unique_entrypoint_uris." + via_bucket)
                        continue

                # bucket is ok proceed
                for target_url in service_record['unique_entrypoint_uris'][via_bucket]:

                    if 'https' in target_url:

                        # matches our fqdn filter if present?
                        if fqdn_re_filter:
                            if not fqdn_re_filter.match(target_url):
                                logging.debug("Skipping fqdn_filter no match: " + service_record['name'] + " -> " + target_url)
                                continue

                        # matches our fqdn filter if present?
                        if collapse_on_fqdn_re_filter:
                            collapse_fqdn_match = collapse_on_fqdn_re_filter.search(target_url)
                            if collapse_fqdn_match:
                                collapsed_fqdn_found = collapse_fqdn_match.group(1)
                                if collapsed_fqdn_found in collapsed_fqdns_found:
                                    logging.debug("Skipping " + service_record['name'] + " url " + target_url + " as collapse_on_fqdn_filter already has a match for: " + collapsed_fqdn_found)
                                    continue
                                elif collapsed_fqdn_found:
                                    logging.debug("collapse_on_fqdn_filter matched " + service_record['name'] + " url " + target_url + " will use this as our collapsed match for fqdn: " + collapsed_fqdn_found)
                                    collapsed_fqdns_found.append(collapsed_fqdn_found)

                        # create a unique name for each filename, containing relevant swarm info
                        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
                        if testssl_outputmode == 'files':
                            file_arg_target_dir = testssl_outputdir
                            filename = service_record["swarm_name"] + "__" +service_record["name"] + "__" + target_url.replace("https://","").replace(":","_") + "__" + timestamp
                        else:
                            file_arg_target_dir = testssl_outputdir + "/" + service_record["swarm_name"] + "/" +service_record["name"] + "/" + target_url.replace("https://","").replace(":","_")
                            filename = timestamp

                        # filenames for all types
                        logfilename = file_arg_target_dir+"/testssl__"+filename+".log"
                        csvfilename = file_arg_target_dir+"/testssl__"+filename+".csv"
                        htmlfilename = file_arg_target_dir+"/testssl__"+filename+".html"
                        jsonfilename = file_arg_target_dir+"/testssl__"+filename+".json"

                        # append the actuall flags + file log args for the target_url
                        testssl_sh_commands += testssl_nonfile_args + " --logfile %s --jsonfile-pretty %s --csvfile %s --htmlfile %s %s\n" % (logfilename,jsonfilename,csvfilename,htmlfilename,target_url)

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
        logging.exception("Error in testssl_input_generator.execute()")


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-filename', dest='input_filename', default="servicechecksdb.json", help="Filename of layer check check database")
    parser.add_argument('-o', '--output-filename', dest='output_filename', default="testssl_input.txt")
    parser.add_argument('-a', '--testssl-nonfile-args', dest='testssl_nonfile_args', help='any valid testssl.sh argument other than any of the "--*file" destination arguments, default "-S -P -p --fast"', default="-S -P -p --fast")
    parser.add_argument('-d', '--testssl-outputdir', dest='testssl_outputdir', help='for each command generated, the root output dir for all --*file arguments, default "testssl_output"', default="testssl_output")
    parser.add_argument('-m', '--testssl-outputmode', dest='testssl_outputmode', help='for each command generated, the filenames by which the testssl.sh `-*file` output file arguments will be generated. Default `files`. If `dirs` a unique dir structure will be created based on swarmname/servicename/fqdn/[timestamp].[ext], if `files` each output file will be in the same `--testssl-outputdir` directory but named such as swarmname__servicename__fqdn__[timestamp].[ext]', default="files")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")
    parser.add_argument('-b', '--log-file', dest='log_file', default=None, help="Path to log file, default None, STDOUT")
    parser.add_argument('-z', '--stdout-result', action='store_true', help="print results to STDOUT in addition to output-filename on disk")
    parser.add_argument('-e', '--fqdn-filter', dest='fqdn_filter', default=None, help="Regex filter to limit which FQDNs actually include in the output")
    parser.add_argument('-B', '--uri-bucket-filter', dest='uri_bucket_filter', default=None, help="Regex filter to limit which 'unique_entrypoint_uris.[bucketname]' to actually included in output")
    parser.add_argument('-c', '--collapse-on-fqdn-filter', dest='collapse_on_fqdn_filter', default=None, help="Capturing Regex filter to match on fqdns that share a common element and limit the test to only one of those matches, the first one found. For wildcard certs, this might be something like '.*(.wildcard.domain)'")

    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    execute(args.input_filename,args.output_filename,args.stdout_result,
        args.fqdn_filter,args.testssl_nonfile_args,args.testssl_outputdir,
        args.uri_bucket_filter,args.collapse_on_fqdn_filter,args.testssl_outputmode)
