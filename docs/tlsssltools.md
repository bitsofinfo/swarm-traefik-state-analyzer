## <a id="tlsssltools"></a>TLS/SSL diagnosis scripts

[Back to main README](../README.md)

Another cause of issues can typically be TLS/SSL related, expired certificates, unsupported ciphers, invalid names etc. A great tool out there is [https://github.com/drwetter/testssl.sh](https://github.com/drwetter/testssl.sh) and the scripts below can be used to consume the data from the `servicechecksdb` to provide `testssl.sh` command inputs to automate TLS/SSL checking your apps via their various entrypoints (unique fqdns).

1. [testsslinputgenerator.py](#testsslinputgenerator): Reads a `servicechecksdb.json` output file to produce a `testssl_input.txt` file that can be used to feed `testssl.sh` invocations.


## <a id="testsslinputgenerator"></a>testsslinputgenerator.py

```bash
./testsslinputgenerator.py --input-filename [filename] \
  --output-filename [filename] \
  --testssl-nonfile-args [single quoted args] \
  --testssl-outputdir [relative or full path to a dir] \
  --fqdn-filter [single quoted regex] \
  --uri-bucket-filter [single quoted regex] \
  --collapse-on-fqdn-filter [single quoted regex]
```

Options:
* `--input-filename`: name of the input file (i.e. this must be the output file of `servicecheckerdb.py`)
* `--output-filename`: name of the file to output the `testssl.sh` commands in. This file can be used to feed `testssl.sh`
* `--testssl-outputmode`: for each command generated, the filenames by which the testssl.sh `-*file` output file arguments will be generated. Default `files`. If `dirs` a unique dir structure will be created based on `swarmname/servicename/fqdn/[timestamp].[ext]`, if `files` each output file will be in the same `--testssl-outputdir` directory but named such as `swarmname__servicename__fqdn__[timestamp].[ext]`
* `--testssl-nonfile-args`: any valid `testssl.sh` argument other than any of the `testssl.sh` output `--*file` arguments such as `--jsonfile, --csvfile` etc. Why? because this script will auto generate those for you. The defaults for this are `-S -P -p --fast`
* `--testssl-outputdir`: for each `testssh.sh` command generated into the `--output-filename` this will be the the root output dir for all generated `testssl.sh` `--*file` arguments, default value: `testssl_output`
* `--log-file`: path to log file, otherwise STDOUT
* `--log-level`: python log level (DEBUG, WARN ... etc)
* `--fqdn-filter`: Regex filter to limit which FQDNs from the `--input-filename`'s `service_record.unique_entrypoint_uris.[bucket].[fqdns]` are actually included in the generated `--output-filename`
* `--uri-bucket-filter`: Regex filter to limit which `unique_entrypoint_uris.[bucketname]` to actually include in the output
* `--collapse-on-fqdn-filter`: Capturing Regex filter to match on fqdns that share a common element and limit the generated output to only one of those matches, the first one found. For wildcard names, this might be something like `'.*(.wildcard.domain)|.*(.wildcard.domain2)'`

Produces output for `testssl.sh` to consume:
```
-S -P -p --fast --logfile testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.log \
  --jsonfile-pretty testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.json \
  --csvfile testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.csv \
  --htmlfile testssl_output/myswarm1/my-app-prod-11-beta2_app/my-app-prod.test.com/result.html \
  https://my-app-prod.test.com
-S -P -p --fast --logfile testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.log \
  --jsonfile-pretty testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.json \
  --csvfile testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.csv \
  --htmlfile testssl_output/myswarm1/my-app-prod-11-beta2_app/bitsofinfo.test.com/result.html \
  https://bitsofinfo.test.com
```

Which could then be consumed by `testssl.sh` such as:

```
./testssl.sh -f testssl_input.txt
```

Or write your own program to parse it and spawn your own execs of `testssl.sh`

[Back to main README](../README.md)