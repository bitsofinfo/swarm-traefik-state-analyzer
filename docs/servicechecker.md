## <a id="servicechecker"></a>servicechecker.py

[Back to main README](../README.md)

This script consumes the output from `servicechecksdb.py` uses it to actually execute all the defined service check requests (in parallel) defined in the `servicechecksdb.py` JSON output file. The results are written into a JSON file containing the detailed results and metrics of all service checks completed. Note depending on the number of checks the prior scripts pre-computed, this could result in a very large result file.

This file can be used to parse and feed into an alerting system or use however you see fit for your analysis needs.

As a start a simple `servicecheckerreport.py` script is in this project which will give a summary report from the `servicechecksdb.py` output JSON file.

```bash
./servicechecker.py --input-filename [servicechecksdb output file] \
  --job-name [optional name for this execution job] \
  --output-format [json or yaml: default json]
  --max-retries [maximum retries per service check]
  --output-filename [report filename] \
  [--layers 0 1 2 3 4] \
  [--tags health foo bar] \
  [--threads N]
```

Options:
* `--max-retries`: max retries per service check, overrides the value in the input file
* `--output-format`: json or yaml. Must be JSON if this will be fed into: `servicecheckerreport.py`
* `--job-name`: optional arbitrary job name
* `--layers`: layers to actually invoke checks for (default all)
* `--tags`: only execute service checks w/ given tags (default any)
* `--fqdn-filter`: regex string to limit urls that get executed for checks within specified layers
* `--threads`: default 30, number of threads for checks, adjust if DOSing yourself
* `--sleep-seconds`: The max amount of time to sleep between all attempts for each service check; if > 0, the actual sleep will be a random time from 0 to this value
* `--input-filename`: path where the JSON output of `servicechecksdb.py` is
* `--output-filename`: path where the JSON results will be written
* `--log-file`: path to log file, otherwise STDOUT
* `--log-level`: python log level (DEBUG, WARN ... etc)
* `--stdout-result`: print results to STDOUT in addition to output-filename on disk

Produces (a ton of) output related to every health check executed, including attempts information as well as a convienent `curl` command you can use to try it again yourself: (truncated for brevity)
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
