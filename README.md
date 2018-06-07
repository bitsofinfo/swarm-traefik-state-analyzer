# swarm-traefik-state-analyzer

This project is intended to aid in the analysis of Docker Swarm services that are proxied by [Traefik](https://traefik.io/) in an "swarm footprint" architecture whereby services are segmented on the swarm/traefik by classification of being *internal* or *external* services. All inbound http(s) traffic for either segment passes through higher level proxies (layer4) or direct lb bound fqdns (layer3) on to its corresponding hard/software load balancer (layer2), to one of several Traefik instances (layer1), and then on to individual Swarm (layer0) service containers.

Triaging *"where the hell does the problem reside"* in such a setup can be a daunting task as there are many possible points of misconfiguration, hardware and software failures that can be the culprit.

- Are the service containers themselves ok?
- Are all my swarm nodes up?
- Is my service accessible and responding on the swarm pub port?
- Is Traefik functioning?
- Are all my Traefik labels working?
- Is Traefik on the right network to talk to the service?
- Is the DNS for these labels correct?
- Is the load-balancer pointing to the right Traefik backend?
- Is something busted in front of my load-balancer?
- Is the name/fqdn even pointing to the correct balancer or whatever is in front of that?

Ugh... well those kinds of questions is what this tool is intended to *assist* in helping to narrow down where to look next. These scripts collect relevant info from the swarm, generate all possible avenues of ingress across all layers for service checks to services on a swarm, and execute those checks giving detailed results.

By validating access directly through all possible layers of a Swarm/Traefik footprint you can help figure out what layers are having issues to properly stop the bleeding.

* [Architecture overview](#architecture)
  * [Swarm Info files](#swarminfo)
  * [Service State files](#servicestate)
* [Modules/Scripts overview](#modules)
  * [swarmstatedb.py](#swarmstatedb)
  * [servicechecksdb.py](#servicechecksdb)
  * [servicechecker.py](#servicechecker)
  * [servicecheckerreport.py](#servicecheckerreport)
  * [analyze-swarm-traefik-state.py](#analyze-swarm-traefik-state)
  * [servicecheckerdb2prometheus.py](#servicecheckerdb2prometheus)
* [Grafana dashboards](#grafana)

## <a id="architecture"></a>Architecture overview

This suite of modules is built around the following simple architecture

### Physical

* You have a Docker Swarm cluster made up of N hosts
*  The Swarm has two classifications of docker overlay networks on it
  - `external`: for services that receive requests from outside sources
  - `internal`: for services that receive requests from internal sources
*  Each network has a single designated [Traefik](https://traefik.io/) service that is published on a fixed swarm port. This Traefik service proxies all inbound HTTP/S traffic to other application services on that shared `internal` or `external` network.
*  Each fixed `internal/external` Traefik published port on the swarm (lets say `external` is 45900 and `internal` is 45800) receives its traffic from a corresponding designated internal/external load-balancer device (hardware or software) that resides on the network.
*  DNS for your deployed services points an appropriate device that will eventually proxy traffic to the appropriate internal or external load-balancer
*  Upstream from the load-balancers may be potentially other devices, firewalls, wafs, app proxies etc
*  Each of these DNS names are specified within a `traefik.[servicename].frontend.rule=Host:[name1],[nameN]..`label on each service

### Logical

*  Your applications are deployed as docker services on a target swarm.
*  An application runs within the scope of logical "context" (i.e. pre-prod, or prod, or qa etc)
*  A "context" generally implies a set of corresponding configuration that is different in some way to any other "context"
*  An application can have an optional "classifier" to give it additional categorization
*  A binary Docker image (i.e. my-app:10.0-beta-1) paired with a "context" and optional "classifier" yields an unique deployed docker service.
    * a deployed docker service has a naming convention `[appname]-[context]-[version][-classifier]` (i.e. `my-app-pre-prod-10-0-beta-1`)
*  The combination of a Docker image version, in scope of a "context" falls into one of three categories:
    * `current`: The current version of the application receiving live traffic bound to FQDNs representative of live traffic (i.e. www.my-app.test.com)
    * `previous`: The previous version of the application which receives traffic bound to unique FQDNs (i.e. my-app-pv.test.com)
    * `next`: The upcoming version of the application which receives traffic bound to special testing FQDNs (i.e. my-app-nv.test.com)
*  "Where" HTTP/S traffic goes for given standard FQDNs can easily be controlled by hot-swapping Traefik frontend rules via Docker service labels

## <a id="modules"></a>Modules/Scripts

This project provides multiple modules who's input/output can be used between each other or each can just be used independently on their own.

1. [swarmstatedb.py](#swarmstatedb): to collect raw docker swarm service state into a JSON db
1. [servicechecksdb.py](#servicechecksdb): decorates all the layer service checks for services discovered by `swarmstatedb`
1. [servicechecker.py](#servicechecker): executes the service checks generated by `servicechecksdb`, records results
1. [servicecheckerreport.py](#servicecheckerreport): reads `servicechecker` output and prepares a simple report  
1. [analyze-swarm-traefik-state.py](#analyze-swarm-traefik-state): orchestrates the above steps in one simple command
1. [servicecheckerdb2prometheus.py](#servicecheckerdb2prometheus): monitors a directory for `servicechecker` output and exposes as Prometheus`/metrics`


## <a id="swarmstatedb"></a>swarmstatedb.py

This script will interrogate a target swarm for services matching `--service-filter` and dump a summarized subset of the relevant information in a JSON file which can then be consumed by `servicechecksdb.py`...or whatever else you want to do with it. The information it extracts contains published port information, traefik labels, image info, number of replicas amongst other things.

```bash
./swarmstatedb.py --output-filename [filename] \
  --swarm-info-repo-root /pathto/[dir containing swarm-name.yml files] \
  --swarm-name [swarm-name] \
  --service-filter '{"name":"some-service-name prefix"}' \
```

Options:
* `--swarm-info-repo-root`: dir that anywhere in its subdirectories contains `[swarm-name].yml` files that contain the information as described in the `[swarm-name].yml` files section
* `--service-filter`: filters (dict) – Filters to process on the nodes list. Valid filters: id, name , label and mode.
* `--swarm-name`: the logical swarm name you are interrogating
* `--output-filename`: path where the JSON output will be written
* `--minstdout`: minimize the amount of STDOUT output

Produces output:
```json
[
    {
        "swarm_name": "myswarm1",
        "id": "xxxx",
        "name": "my-app-prod-11-beta2_app",
        "image": "my-app:11-beta2",
        "int_or_ext": "external",
        "replicas": 4,
        "port_mappings": [
            "30001:443"
        ],
        "traefik_host_labels": [
            "my-app-prod.test.com",
            "bitsofinfo.test.com",
            "my-app-prod-11-beta2.test.com"
        ]
    },
    ...
```

## <a id="servicechecksdb"></a>servicechecksdb.py

This script consumes the output from `swarmstatedb.py` and supplements it with information from `[swarm-name].yml`, and one or more relevant `service-state.yml` files to compute an exhaustive list of all possible ingress paths to invoke the appropriate service checks for each service exposed on the swarm via each layer of access (0:swarm direct, 1:traefik direct, 2:load-balancers, and 3:normal fqdns).

Depending on the number of ports your application exposes, number of swarm nodes and corresponding Traefik frontend `Host` header based labels you have applied to a service... this can result many pre-computed ingress check combinations.

You can use the generated JSON file that contains all the necessary information (urls, headers, methods, payloads etc) to drive any monitoring system you'd like.... or just feed into the provided `servicechecker.py` to execute all the service checks and write a detailed report out... again in JSON.

```bash
./servicechecksdb.py --input-filename [swarmstatedb output file] \
  --swarm-info-repo-root /pathto/[dir containing swarm-name.yml files] \
  --service-state-repo-root /pathto/[dir containing service-state.yml files]
  --output-filename [filename] \
  [--layers 0 1 2 3 4] \
  [--tags health foo bar]
```

Options:
* `--swarm-info-repo-root`: dir that anywhere in its subdirectories contains `[swarm-name].yml` files that contain the information as described in the `[swarm-name].yml` files section
* `--service-state-repo-root`: dir that anywhere in its subdirectories contains `service-state.yml` files that contain the information as described in the `service-state.yml` files section
* `--layers`: layers to generate actual checks for in the output database (default all)
* `--tags`: only for service checks w/ given tags (default any)
* `--input-filename`: path where the JSON output of `swarmstatedb.py` is
* `--output-filename`: path where the JSON output will be written
* `--minstdout`: minimize the amount of STDOUT output

Decorates additional info to `swarmstatedb` output from `service-state.yml` files:
```json
  ...
  "warnings": [],
  "context": {
      "name": "prod",
      "version": "10",
      "tags": [
          "current"
      ]
  },
  "formal_name": "my-app",
  "app_type": "go",
  "aliases": [
      "my-alias2",
      "my-alias1"
  ],
  "service_checks": {
      "layer0": [
          {
              "layer": 0,
              "url": "https://myswarm1-node1.test.com:30001/health",
              "target_container_port": 443,
              "host_header": null,
              "headers": [
                  "test2: yes"
              ],
              "method": "GET",
              "timeout": 5,
              "retries": 5,
              "tags" : [
                  "foo",
                  "health"
              ],
              "description": "my-app-prod-11-beta2_app swarm service port direct"
          },
          ...
        ],
      "layer1": [
          {
              "layer": 1,
              "url": "https://myswarm1-node1.test.com:45900/health",
              "target_container_port": 443,
              "host_header": "my-app-prod.test.com",
              "headers": [
                  "test2: yes"
              ],
              "method": "GET",
              "timeout": 5,
              "retries": 5,
              "tags" : [
                  "foo",
                  "health"
              ],
              "description": "my-app-prod-11-beta2_app via traefik direct"
          },
          ...
        ],
      "layer2": [
          {
              "layer": 2,
              "url": "https://myswarm1-extlb.test.com/health",
              "target_container_port": 443,
              "host_header": "my-app-prod.test.com",
              "headers": [
                  "test2: yes"
              ],
              "method": "GET",
              "timeout": 5,
              "retries": 5,
              "tags" : [
                  "foo",
                  "health"
              ],
              "description": "my-app-prod-11-beta2_app via load balancer direct"
          },
          ...
        ],
      "layer3": [
          {
              "layer": 3,
              "url": "https://my-app-prod.test.com/health",
              "target_container_port": 443,
              "host_header": null,
              "headers": [
                  "test2: yes"
              ],
              "method": "GET",
              "timeout": 5,
              "retries": 5,
              "tags" : [
                  "foo",
                  "health"
              ],
              "description": "my-app-prod-11-beta2_app via normal fqdn"
          },
      "layer4": [
          {
              "layer": 4,
              "url": "https://my-app-prod-mode-a.test.com/api/2.7/submit-report",
              "target_container_port": null,
              "host_header": null,
              "headers": [
                  "Content-Type: text/json"
              ],
              "basic_auth": "user@test.com:123",
              "body": "{ \"request_data\":\"XXXXXX\", \"text_version\":\"14a-c blah, blah, blah\" }",
              "is_healthy": {
                  "response_codes": [
                      200
                  ],
                  "body_evaluator": {
                      "type": "contains",
                      "value": "check-code=100A"
                  }
              },
              "method": "POST",
              "timeout": 10,
              "retries": 5,
              "tags" : [
                  "foo",
                  "health"
              ],
              "description": "my-app-prod-11-beta2_app via layer 4 custom: https://my-app-prod-mode-a.test.com"
          },
          ...
        ]

  ...
```

## <a id="servicechecker"></a>servicechecker.py

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
* `--threads`: default 30, number of threads for checks, adjust if DOSing yourself
* `--input-filename`: path where the JSON output of `servicechecksdb.py` is
* `--output-filename`: path where the JSON results will be written
* `--minstdout`: minimize the amount of STDOUT output

Produces (a ton of) output related to every health check executed, including attempts information as well as a convienent `curl` command you can use to try it again yourself: (truncated for brevity)
```json
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


## <a id="servicecheckerreport"></a>servicecheckerreport.py

This script consumes the service check result output from `servicecheckerdb.py` and produces a simple markdown report dumped to the consul and output to a file.

This report is pretty simplistic but gives a decent summary of the state of access to services on the target swarm.

```
./servicecheckerreport.py --input-filename [servicecheckerdb result file] \
  --verbose [flag, will dump CURL commands for all failed checks]
  --output-filename [report filename] \
```

Options:
* `--minstdout`: minimize the amount of STDOUT output

Produces output:

```
SOURCE: servicecheckerdb.json

  (N) = total replicas
(f/t) = f:failures, t:total checks
 XXms = average round trip across checks
    h = health: percentage of checks that succeeded
    a = attempts: total attempts per service check
    r = retries: percentage of attempts > 1 per check

----------------------------------------------------------
my-app
  Overall: h:98.6%  (10/692) a:775  r:12.0%  1168.8ms
----------------------------------------------------------
 - layer0: swarm direct:   h:100.0% (0/84)   a:98   r:16.7%  
 - layer1: traefik direct: h:99.6%  (2/532)  a:582  r:9.4%   
 - layer2: load balancers: h:100.0% (0/38)   a:41   r:7.9%   
 - layer3: normal fqdns :  h:78.9%  (8/38)   a:54   r:42.1%  
 - layer4: app proxies :   h:0%     (0/0)    a:0    r:0%     
----------------------------------------------------------

----------------------------------------------------------
my-app-pre-prod-10_app
    100.0% (4) [previous] 862.2ms
----------------------------------------------------------
 - l0: h:100.0% (0/28)   a:28   r:0.0%   1782.8ms
 - l1: h:100.0% (0/168)  a:168  r:0.0%   761.8ms
 - l2: h:100.0% (0/12)   a:12   r:0.0%   530.0ms
 - l3: h:100.0% (0/12)   a:12   r:0.0%   451.1ms
 - l4: h:0%     (0/0)    a:0    r:0%     0ms

----------------------------------------------------------
my-app-prod-12-beta5_app
    97.4% (1) [current] 1125.3ms
----------------------------------------------------------
 - l0: h:100.0% (0/28)   a:36   r:28.6%  3446.6ms
 - l1: h:99.6%  (1/280)  a:305  r:8.9%   847.5ms
      (1): (<class 'socket.timeout'>, timeout('The read operation timed out',))
          curl -v --retry 3 -k -m 5 -X GET --header 'Host: my-app-pre-prod-12-beta3.test.com' --header 'test2: yes' https://myswarm1-node2.test.com:10001/health
 - l2: h:100.0% (0/20)   a:23   r:15.0%  1799.6ms
 - l3: h:60.0%  (8/20)   a:36   r:80.0%  1090.2ms
      (6): (<class 'urllib.error.URLError'>, URLError(gaierror(8, 'nodename nor servname provided, or not known'),))
          curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://my-app-pre-prod-12-beta3.test.com/health
          curl -v --retry 3 -k -m 10 -X GET https://my-app-pre-prod-12-beta3.test.com/health
          curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://my-app-pre-prod-beta.test.com/health
          curl -v --retry 3 -k -m 10 -X GET https://my-app-pre-prod-beta.test.com/health
          curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://my-app-pre-prod-joedev.test.com/health
          curl -v --retry 3 -k -m 10 -X GET https://my-app-pre-prod-joedev.test.com/health
      (2): (<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))
          curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://bitsofinfo.test.com/health
          curl -v --retry 3 -k -m 10 -X GET https://my-app-pre-prod-12-beta3.test.com/health
 - l4: h:0%     (0/0)    a:0    r:0%     0ms

----------------------------------------------------------
my-app-prod-12-beta3_app
    99.2% (1) [next] 1834.8ms
----------------------------------------------------------
 - l0: h:100.0% (0/28)   a:34   r:21.4%  3537.9ms
 - l1: h:98.8%  (1/84)   a:109  r:29.8%  1403.6ms
      (1): (<class 'socket.timeout'>, timeout('The read operation timed out',))
          curl -v --retry 3 -k -m 5 -X GET --header 'Host: my-app-pre-prod-12-beta3.test.com' --header 'test2: yes' https://myswarm1-node2.test.com:10001/health
 - l2: h:100.0% (0/6)    a:6    r:0.0%   706.5ms
 - l3: h:100.0% (0/6)    a:6    r:0.0%   1052.3ms
 - l4: h:0%     (0/0)    a:0    r:0%     0ms


RAW RESULTS --> servicecheckerdb.json
THE ABOVE ON DISK --> servicecheckerreport.md
```

## <a id="analyze-swarm-traefik-state"></a>analyze-swarm-traefik-state.py

This script orchestrates all the following steps with one command:

1. Invokes: [swarmstatedb.py](#swarmstatedb) to collect raw docker swarm service state database
1. Invokes: [servicechecksdb.py](#servicechecksdb)to create database of service checks for the swarm state
1. Invokes: [servicechecker.py](#servicechecker) which executes the service checks, captures results
1. Invokes: [servicecheckerreport.py](#servicecheckerreport) reads and prepares a simple report  

All of the data generated from `analyze-swarm-traefik-state.py` is stored by default under the `output/` dir within this project.

```
./analyze-swarm-traefik-state.py --job-name [name] \
  --swarm-info-repo-root /pathto/[dir containing swarm-name.yml files] \
  --service-state-repo-root /pathto/[dir containing swarm-state.yml files] \
  --swarm-name [name] \
  --service-filter '{"name":"some-service-name prefix"}' \
  --layers 0 1 2 3 4 \
  --tags health foo bar \
  --threads 30 \
  [--verbose]
```

The meaning for the options above are the same as and described in the separate sections above for each separate module

## <a id="servicecheckerdb2prometheus"></a>servicecheckerdb2prometheus.py

This project also provides the `servicecheckerdb2prometheus.py` module which will monitor a directory for `*servicecheckerdb*.json` files generated by `servicechecker.py` and expose them as `/metrics` consumable by [Prometheus](https://prometheus.io/) for analysis in [Grafana](https://grafana.com/) through a few provided dashboards (see the `/grafana` directory for dashboards)

```
./servicecheckerdb2prometheus.py --input-dir [monitor dir] --metrics-port XXXX
```

Options:
* `--metrics-port`: HTTP port (default 8000) to expose the `/metrics` enpoint on for Prometheus consumption
* `--input-dir`: directory to recursively monitor for `*servicecheckerdb*.json` files generated by `servicechecker.py`
* `--minstdout`: minimize the amount of STDOUT output

Once run, it will automatically update all exposed metrics as new `*servicecheckerdb*.json` are created within the `--input-dir`. The metrics produced are several Prometheus `Counters` and `Gauges` appropriately labeled for very broad or granular slices.

Metrics exposed:
```
# HELP python_info Python platform information
# TYPE python_info gauge
python_info{implementation="CPython",major="3",minor="6",patchlevel="4",version="3.6.4"} 1.0
# HELP sts_analyzer_c_ok_total Cumulative total OK
# TYPE sts_analyzer_c_ok_total counter
sts_analyzer_c_ok_total{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 28.0
...
# HELP sts_analyzer_c_fail_total Cumulative total FAILED
# TYPE sts_analyzer_c_fail_total counter
sts_analyzer_c_fail_total{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 0.0
...
# HELP sts_analyzer_c_attempts_total Cumulative total attempts
# TYPE sts_analyzer_c_attempts_total counter
sts_analyzer_c_attempts_total{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 33.0
...
# HELP sts_analyzer_g_health_rating Most recent % OK checks for
# TYPE sts_analyzer_g_health_rating gauge
sts_analyzer_g_health_rating{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 100.0
...
# HELP sts_analyzer_g_retry_percentage Most recent % of checks that had to be retried
# TYPE sts_analyzer_g_retry_percentage gauge
sts_analyzer_g_retry_percentage{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 17.857142857142858
...
# TYPE sts_analyzer_g_fail_percentage gauge
sts_analyzer_g_fail_percentage{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 0.0
...
# HELP sts_analyzer_g_ok Most recent total OK checks
# TYPE sts_analyzer_g_ok gauge
sts_analyzer_g_ok{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 28.0
...
# HELP sts_analyzer_g_failures Most recent total FAILED checks
# TYPE sts_analyzer_g_failures gauge
sts_analyzer_g_failures{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 0.0
...
# HELP sts_analyzer_g_attempts Most recent total ATTEMPTS checks
# TYPE sts_analyzer_g_attempts gauge
sts_analyzer_g_attempts{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 33.0
...
# HELP sts_analyzer_g_avg_resp_time_seconds Average response time for checks in seconds
# TYPE sts_analyzer_g_avg_resp_time_seconds gauge
sts_analyzer_g_avg_resp_time_seconds{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer0",swarm="myswarm1",tags="current",version="12beta2"} 4.298571428571428
...
# HELP sts_analyzer_g_attempt_errors Most recent total errors
# TYPE sts_analyzer_g_attempt_errors gauge
sts_analyzer_g_attempt_errors{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",error="timeout",formal_name="my_app",layer="layer3",swarm="myswarm1",tags="current",version="12beta2",path="/health"} 6.0
# HELP sts_analyzer_g_replicas Most recent total replicas
# TYPE sts_analyzer_g_replicas gauge
sts_analyzer_g_replicas{classifier="none",context="pre-prod",docker_service_name="my_app_pre-prod_12beta2_app",formal_name="my_app",layer="layer3",swarm="myswarm1",tags="current",version="12beta2"} 6.0
...
```

## <a id="grafana"></a>Grafana dashboards


### Layer Inspector

This dashboard presents analytics organized by **layer**. At the top of the dashboard you can drill down into the data consumed by all metric `labels` generated by the `servicecheckerdb2prometheus.py` module.

[grafana.swarm-traefik-state-analyzer_layer_inspector.json](grafana/grafana.swarm-traefik-state-analyzer_layer_inspector.json)

|Overall Status|Service Inspector|
:-------------------------:|:-------------------------:
![](docs/grafana_overall_status.png)|![](docs/grafana_service_inspector.png)
|Global Alerts|Layer Inspector|
:-------------------------:|:-------------------------:
![](docs/grafana_global_alerts.png)|![](docs/grafana_layer_inspector.png)


## <a id="swarminfo"></a>[swarm-name].yml files

Swarm info files, are a generic YAML declaration that describes a named swarm footprint in the described architecture above.

```yaml
SWARM_MGR_URI: "http://myswarm1.test.com:[port]"

swarm_lb_endpoint_internal: "myswarm1-intlb.test.com"
swarm_lb_endpoint_external: "myswarm1-extlb.test.com"

traefik_swarm_port_internal_https: 45800
traefik_swarm_port_external_https: 45900

contexts:
  - "prod"
  - "pre-prod"

swarm_host_info:
  template: "myswarm1-node{id}.test.com"
  total_nodes: 5

```

## <a id="servicestate"></a>service-state.yml files

Service state files, are a generic YAML declaration that describes a named "service" that can be deployed within the described architecture above on one or more target swarms


```yaml
formal_name: "my-servicename"
app_type: "go"

classifiers:
  mode-a:
    desc: "operation mode A"
  mode-b:
    desc: "operation mode B"

aliases:
  - "my-alias1"
  - "my-alias2"

service_ports:
  443:
    name: "https access port"
    desc: "description"
    protocol: "https"
    classifiers
      - "mode-a"
      - "mode-b"

service_checks:
  - ports: [443]
    path: "/health"
    layers: [0,1,2,3]
    headers:
      - "test2: yes"
    method: "GET"
    timeout: 10
    retries: 3
    tags: ["foo","health"]
  - ports: [443]
    layers: [0,1,2,3]
    path: "/api/2.7/submit-report"
    method: "POST"
    headers:
      - "Content-Type: text/json"
    body: >
      {
        "request_data":"XXXXXX",
        "text_version":"14a-c blah, blah, blah",
      }
    is_healthy:
      response_codes: [200]
      body_evaluator:
        type: "jinja2"
        template: "{% if service_record['context']['version']|string in response_data['as_string'] %}1{% else %}0{% endif %}"
    timeout: 5
    retries: 5
    classifiers: ["mode-a"]
    tags: ["version"]
  - ports: [443]
    layers: [4]
    path: "/api/2.7/submit-report"
    method: "POST"
    headers:
      - "Content-Type: text/json"
    basic_auth: "user@test.com:123"
    body: >
      {
        "request_data":"XXXXXX",
        "text_version":"14a-c blah, blah, blah",
      }
    is_healthy:
      response_codes: [200]
      body_evaluator:
        type: "contains"
        value: "result = 100A"
    timeout: 5
    retries: 5
    classifiers: ["mode-a"]
    tags: ["bar","health"]
    contexts:
      prod:
        url_roots:
          - "https://my-app-prod-mode-a.test.com"
      pre-prod:
        url_roots:
          - "https://my-app-pre-prod-mode-a.test.com"

contexts:
  prod:
    versions:
      current: "10"
      previous: "9"
      next: "12-beta1"
  pre-prod:
    versions:
      current: "10"
      previous: "9"
      next: "12-beta1"
```
