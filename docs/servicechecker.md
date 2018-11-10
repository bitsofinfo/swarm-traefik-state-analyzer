## <a id="servicechecker"></a>servicechecker.py

[Back to main README](../README.md)

This script consumes the output from `servicechecksdb.py` uses it to actually execute all the defined service check requests (in parallel) defined in the `servicechecksdb.py` JSON output file. The results are written into a JSON file containing the detailed results and metrics of all service checks completed. Note depending on the number of checks the prior scripts pre-computed, this could result in a very large result file.

This file can be used to parse and feed into an alerting system or use however you see fit for your analysis needs.

As a start a simple `servicecheckerreport.py` script is in this project which will give a summary report from the `servicechecksdb.py` output JSON file produced by this script.

```bash
./servicechecker.py --help

usage: servicechecker.py [-h] [-i INPUT_FILENAME] [-o OUTPUT_FILENAME]
                         [-f OUTPUT_FORMAT] [-r MAX_RETRIES] [-n JOB_NAME]
                         [-j JOB_ID] [-l LAYERS [LAYERS ...]]
                         [-g TAGS [TAGS ...]] [-t THREADS] [-S SLEEP_SECONDS]
                         [-x LOG_LEVEL] [-b LOG_FILE] [-z] [-e FQDN_FILTER]

optional arguments:
  -h, --help            show this help message and exit
  -i INPUT_FILENAME, --input-filename INPUT_FILENAME
                        Filename of layer check check database, default:
                        'servicechecksdb.json'
  -o OUTPUT_FILENAME, --output-filename OUTPUT_FILENAME
                        Output filename, default: 'servicecheckerdb.json'
  -f OUTPUT_FORMAT, --output-format OUTPUT_FORMAT
                        json or yaml, default 'json'
  -r MAX_RETRIES, --max-retries MAX_RETRIES
                        maximum retries per check, overrides service-state
                        service check configs, default 3
  -n JOB_NAME, --job-name JOB_NAME
                        descriptive name for this execution job, default 'no
                        --job-name specified'
  -j JOB_ID, --job-id JOB_ID
                        unique id for this execution job, default: None
  -l LAYERS [LAYERS ...], --layers LAYERS [LAYERS ...]
                        Space separated list of health check layer numbers to
                        process, i.e. '0 1 2 3 4' etc, default None, ie all
  -g TAGS [TAGS ...], --tags TAGS [TAGS ...]
                        Space separated list health check tags to process,
                        default None (i.e. all)
  -t THREADS, --threads THREADS
                        max threads for processing checks, default 30, higher
                        = faster completion, adjust as necessary to avoid
                        DOSing...
  -S SLEEP_SECONDS, --sleep-seconds SLEEP_SECONDS
                        The max amount of time to sleep between all attempts
                        for each service check; if > 0, the actual sleep will
                        be a random time from 0 to this value. Default 0
  -x LOG_LEVEL, --log-level LOG_LEVEL
                        log level, default DEBUG
  -b LOG_FILE, --log-file LOG_FILE
                        Path to log file, default None, STDOUT
  -z, --stdout-result   print results to STDOUT in addition to --output-
                        filename on disk
  -e FQDN_FILTER, --fqdn-filter FQDN_FILTER
                        Regex filter to limit which FQDNs actually get checked
                        across any --layers being checked. Default None
```

In the `--output-filename`, produces (very verbose) output related to every health check executed, including attempts information as well as a convienent `curl` command you can use to try it again yourself: (truncated for brevity)
```
  {
      "name": "20180520_003903-myswarm1-test",
      "metrics": {
          "health_rating": 97.88732394366197,
          "total_fail": 6,
          "total_ok": 278,
          "total_skipped": 0,
          "total_skipped_no_replicas": 0,
          "avg_resp_time_ms": 1591.0816619718307,
          "total_req_time_ms": 451867.1919999999,
          "retry_percentage": 24.647887323943664,
          "total_attempts": 354,
          "layer0": {
              "health_rating": 100.0,
              "total_ok": 28,
              "total_fail": 0,
              "retry_percentage": 14.285714285714285,
              "total_attempts": 32,
              "total_skipped": 0,
              "failures": {}
          },
          "layer1": {
              "health_rating": 99.10714285714286,
              "total_ok": 222,
          ...
          {
              "layer": 3,
              "url": "https://my-app1.test.com/health",
              "target_container_port": null,
              "host_header": null,
              "headers": [
                  "x-test1: 15"
              ],
              "method": "GET",
              "timeout": 5,
              "retries": 18,
              "description": "my-app1-pre-prod-12-beta2_app via normal fqdn access",
              "tags": [
                  "deployment",
                  "health"
              ],
              "result": {
                  "success": false,
                  "attempts": 3,
                  "ms": 5008.051,
                  "dns": "192.168.9.223",
                  "error": "(<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))",
                  "attempts_failed": [
                      {
                          "ms": 5009.217,
                          "dns": "192.168.9.223",
                          "error": "(<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))"
                      },
                      {
                          "ms": 5009.276,
                          "dns": "192.168.9.223",
                          "error": "(<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))"
                      },
                      {
                          "ms": 5008.051,
                          "dns": "192.168.9.223",
                          "error": "(<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))"
                      }
                  ]
              },
              "distinct_failure_codes": [],
              "distinct_failure_errors": [
                  "(<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))"
              ],
              "curl": "curl -v --retry 3 -k -m 5 -X GET --header 'x-test1: 15' https://my-app1.test.com/health"
          }
  ...
```

[Back to main README](../README.md)
