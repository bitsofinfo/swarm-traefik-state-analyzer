## <a id="tlsssltools"></a>TLS/SSL diagnosis scripts

[Back to main README](../README.md)

Another cause of issues can typically be TLS/SSL related, expired certificates, unsupported ciphers, invalid names etc. A great tool out there is [https://github.com/drwetter/testssl.sh](https://github.com/drwetter/testssl.sh) and the scripts below can be used to consume the data from the `servicechecksdb` to generate `testssl.sh` commands to automate TLS/SSL checking your apps via their various entrypoints (unique fqdns).

1. [testsslcmdsgenerator.py](#testsslcmdsgenerator): Reads a `servicechecksdb.json` output file to produce a `testssl.sh` commands file that can be used invoke all the necessary `testssl.sh` scans.

2. Note! You should checkout the [testssl.sh-processor](https://github.com/bitsofinfo/testssl.sh-processor) which can be used to automatically consume and process the commands generated by this script.


## <a id="testsslcmdsgenerator"></a>testsslcmdsgenerator.py

```bash
./testsslcmdsgenerator.py --help

usage: testsslcmdsgenerator.py [-h] [-i INPUT_FILENAME] [-o OUTPUT_FILENAME]
                               [-M OUTPUT_MODE] [-D TESTSSL_DIR]
                               [-F TESTSSL_OUTPUT_FILE_TYPES]
                               [-a TESTSSL_NONFILE_ARGS]
                               [-d TESTSSL_OUTPUTDIR] [-m TESTSSL_OUTPUTMODE]
                               [-x LOG_LEVEL] [-b LOG_FILE] [-z]
                               [-e FQDN_FILTER] [-B URI_BUCKET_FILTER] [-L]
                               [-c COLLAPSE_ON_FQDN_FILTER]

optional arguments:
  -h, --help            show this help message and exit
  -i INPUT_FILENAME, --input-filename INPUT_FILENAME
                        input filename of layer check check database, default:
                        'servicechecksdb.json'
  -o OUTPUT_FILENAME, --output-filename OUTPUT_FILENAME
                        Output filename, default 'testssl_cmds'
  -M OUTPUT_MODE, --output-mode OUTPUT_MODE
                        output a `plain` text file of one command per line or
                        a executable `sh` script, default `plain`
  -D TESTSSL_DIR, --testssl-dir TESTSSL_DIR
                        dir containing the `testssl.sh` script to prepend to
                        the command, default None"
  -F TESTSSL_OUTPUT_FILE_TYPES, --testssl-output-file-types TESTSSL_OUTPUT_FILE_TYPES
                        The `--*file` argument types that will be included for
                        each command (comma delimited no spaces), default all:
                        "html,json,csv,log"
  -a TESTSSL_NONFILE_ARGS, --testssl-nonfile-args TESTSSL_NONFILE_ARGS
                        any valid testssl.sh arguments OTHER THAN any of the
                        '--*file' destination arguments. IMPORTANT! Please
                        quote the arguments and provide a single leading SPACE
                        character following your leading quote prior to any
                        argument (gets around ArgumentParser bug). default '
                        -S -P -p -U --fast'
  -d TESTSSL_OUTPUTDIR, --testssl-outputdir TESTSSL_OUTPUTDIR
                        for each command generated, the root output dir for
                        all --*file arguments, default None
  -m TESTSSL_OUTPUTMODE, --testssl-outputmode TESTSSL_OUTPUTMODE
                        for each command generated, the filenames by which the
                        testssl.sh `-*file` output file arguments will be
                        generated. Default `files`. If `dirs1` a unique dir
                        structure will be created based on swarmname/servicena
                        me/fqdn/testssloutput__[timestamp].[ext], If `dirs2` a
                        unique dir structure will be created based on fqdn/[ti
                        mestamp]/swarmname/servicename/testssloutput__fqdn.[ex
                        t], if `files` each output file will be in the same
                        `--testssl-outputdir` directory but named such as test
                        ssloutput__[swarmname]__[servicename]__[fqdn]__[timest
                        amp].[ext]
  -x LOG_LEVEL, --log-level LOG_LEVEL
                        log level, default 'DEBUG'
  -b LOG_FILE, --log-file LOG_FILE
                        Path to log file, default None which will output to
                        STDOUT
  -z, --stdout-result   print results to STDOUT in addition to output-filename
                        on disk, default off
  -e FQDN_FILTER, --fqdn-filter FQDN_FILTER
                        Regex filter to limit which FQDNs actually include in
                        the output from 'unique_entrypoint_uris' within
                        (servicechecksdb). Default None
  -B URI_BUCKET_FILTER, --uri-bucket-filter URI_BUCKET_FILTER
                        Regex filter to limit which
                        'unique_entrypoint_uris.[bucketname]' from the
                        --input-filename (servicechecksdb) to actually
                        included in output (buckets are 'via_direct' &
                        'via_fqdn'). Default: None
  -L, --limit-via-direct
                        For the 'unique_entrypoint_uris'... 'via_direct'
                        bucket, if this flag is present: limit the total
                        number of uris included to only ONE uri. Given these
                        represent swarm nodes, only one is typically needed to
                        test the cert presented directly by that service
  -c COLLAPSE_ON_FQDN_FILTER, --collapse-on-fqdn-filter COLLAPSE_ON_FQDN_FILTER
                        Capturing Regex filter to match on fqdns from
                        'unique_entrypoint_uris' that share a common element
                        and limit the test to only one of those matches, the
                        first one found. For wildcard certs, this might be
                        something like '.*(.wildcard.domain)'. Default None
```

Produces output of commands: (`--output-mode sh`)
```
#!/bin/sh

./testssl.sh -S -P -p --fast --logfile testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.log \
  --jsonfile-pretty testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.json \
  --csvfile testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.csv \
  --htmlfile testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.html \
  https://my-app-prod.test.com
./testssl.sh -S -P -p --fast --logfile testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.log \
  --jsonfile-pretty testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.json \
  --csvfile testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.csv \
  --htmlfile testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.html \
  https://bitsofinfo.test.com
```

Or use `--output-mode plain` and write your own program to parse it and spawn your own execs of the commands within

[Back to main README](../README.md)
