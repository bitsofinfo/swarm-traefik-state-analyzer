# swarm-traefik-state-analyzer

This project is intended to aid in the analysis of Docker Swarm services that are proxied by [Traefik](https://traefik.io/) in a fairly typical footprint whereby services are segmented on the swarm/traefik by classification of being *internal* or *external* services. All inbound http(s) traffic for either segment passes through higher level proxies (layer4) or direct lb bound fqdns (layer3) on to its corresponding hard/software load balancer (layer2), to one of several Traefik instances (layer1), and then on to individual Swarm (layer0) service containers.

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

Ugh... well those kinds of questions is what this tool is intended to *assist* in helping to narrow down where to look next. These scripts collect relevant info from the swarm, generate all possible avenues of ingress across all layers for health checks to services on a swarm, and execute those healthchecks giving detailed results.

By validating access directly through all possible layers of a Swarm/Traefik footprint you can help figure out what layers are having issues to properly stop the bleeding.

## analyze-swarm-traefik-state.py

This script orchestrates all the following steps with one command:

1. Invokes: `swarmstatedb.py` to collect raw docker swarm service state database
1. Invokes: `healthchecksdb.py` to create database of health checks for the swarm state
1. Invokes: `healthchecker.py` which executes the health checks, captures results
1. Invokes: `healthcheckerreport.py` reads and prepares a simple report  

All of the data generated from `analyze-swarm-traefik-state.py` is stored by default under the `output/` dir within this project.

```
./analyze-swarm-traefik-state.py --job-name [name] \
  --swarm-info-repo-root /pathto/[dir containing swarm-name.yml files] \
  --service-state-repo-root /pathto/[dir containing swarm-state.yml files] \
  --swarm-name [name] \
  --service-filter '{"name":"some-service-name prefix"}' \
  --layers 0 1 2 3 4 \
  --tags foo bar \
  --threads 30 \
  [--verbose]
```

The meaning for the options above are the same as and described in the separate sections below for each separate module

## swarmstatedb.py

This script will interrogate a target swarm for services matching `--service-filter` and dump a summarized subset of the relevant information in a JSON file which can then be consumed by `healthchecksdb.py`...or whatever else you want to do with it. The information it extracts contains published port information, traefik labels, image info, number of replicas amongst other things.

```
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

Produces output:
```
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

## healthchecksdb.py

This script consumes the output from `swarmstatedb.py` and supplements it with information from `[swarm-name].yml`, and one or more relevant `service-state.yml` files to compute an exhaustive list of all possible ingress paths to invoke the appropriate health checks for each service exposed on the swarm via each layer of access (0:swarm direct, 1:traefik direct, 2:load-balancers, and 3:normal fqdns).

Depending on the number of ports your application exposes, number of swarm nodes and corresponding Traefik frontend `Host` header based labels you have applied to a service... this can result in easily over 1000+ pre-computed ingress check combinations.

You can use the generated JSON file that contains all the necessary information (urls, headers, methods, payloads etc) to drive any monitoring system you'd like.... or just feed into the provided `healthchecker.py` to execute all the health checks and write a detailed report out... again in JSON.

```
./healthchecksdb.py --input-filename [swarmstatedb output file] \
  --swarm-info-repo-root /pathto/[dir containing swarm-name.yml files] \
  --service-state-repo-root /pathto/[dir containing service-state.yml files]
  --output-filename [filename] \
  [--layers 0 1 2 3 4] \
  [--tags foo bar]
```

Options:
* `--swarm-info-repo-root`: dir that anywhere in its subdirectories contains `[swarm-name].yml` files that contain the information as described in the `[swarm-name].yml` files section
* `--service-state-repo-root`: dir that anywhere in its subdirectories contains `service-state.yml` files that contain the information as described in the `service-state.yml` files section
* `--layers`: layers to generate actual checks for in the output database (default all)
* `--tags`: only for health checks w/ given tags (default any)
* `--input-filename`: path where the JSON output of `swarmstatedb.py` is
* `--output-filename`: path where the JSON output will be written

Decorates additional info to `swarmstatedb` output:
```
  ...
  "context": "prod",
  "context_version": "current",
  "health_checks": {
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
                  "foo"
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
                  "foo"
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
                  "foo"
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
                  "foo"
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
                  "body_regex": "result = 100A"
              },
              "method": "POST",
              "timeout": 10,
              "retries": 5,
              "tags" : [
                  "foo"
              ],
              "description": "my-app-prod-11-beta2_app via layer 4 custom: https://my-app-prod-mode-a.test.com"
          },
          ...
        ]

  ...
```

## healthchecker.py

This script consumes the output from `healthchecksdb.py` uses it to actually execute all the defined health check requests (in parallel) defined in the `healthchecksdb.py` JSON output file. The results are written into a JSON file containing the detailed results and metrics of all health checks completed. Note depending on the number of checks the prior scripts pre-computed, this could result in a very large result file.

This file can be used to parse and feed into an alerting system or use however you see fit for your analysis needs.

As a start a simple `healthcheckerreport.py` script is in this project which will give a summary report from the `healthchecksdb.py` output JSON file.

```
./healthchecker.py --input-filename [healthchecksdb output file] \
  --job-name [optional name for this execution job] \
  --output-format [json or yaml: default json]
  --max-retries [maximum retries per health check]
  --output-filename [report filename] \
  [--layers 0 1 2 3 4] \
  [--tags foo bar] \
  [--threads N]
```

Options:
* `--max-retries`: max retries per health check, overrides the value in the input file
* `--output-format`: json or yaml. Must be JSON if this will be fed into: `healthcheckerreport.py`
* `--job-name`: optional arbitrary job name
* `--layers`: layers to actually invoke checks for (default all)
* `--tags`: only execute health checks w/ given tags (default any)
* `--threads`: default 30, number of threads for checks, adjust if DOSing yourself
* `--input-filename`: path where the JSON output of `healthchecksdb.py` is
* `--output-filename`: path where the JSON results will be written

Produces (a ton of) output: (truncated for brevity)
```
  {
      "name": "20180520_003903-myswarm1-test",
      "metrics": {
          "health_rating": 97.88732394366197,
          "total_fail": 6,
          "total_ok": 278,
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
              "failures": {}
          },
          "layer1": {
              "health_rating": 99.10714285714286,
              "total_ok": 222,
          ...
  ...
```


## healthcheckerreport.py

This script consumes the health check result output from `healthcheckerdb.py` and produces a simple markdown report dumped to the consul and output to a file.

This report is pretty simplistic but gives a decent summary of the state of access to services on the target swarm.

```
./healthcheckerreport.py --input-filename [healthcheckerdb result file] \
  --verbose [flag, will dump CURL commands for all failed checks]
  --output-filename [report filename] \
```

Produces output:
```
SOURCE: healthcheckerdb.json

(f/t) = f:failures, t:total checks
 XXms = average round trip across checks
    h = health: percentage of checks that succeeded
    a = attempts: total attempts per health check
    r = retries: percentage of attempts > 1 per check

----------------------------------------------------------
20180515a-my-app-prod-11-beta2_app
  Overall: h:98.6%  (4/284)  a:312  r:9.9%   1405.6ms
----------------------------------------------------------
 - layer0: via swarm direct:   h:100.0% (0/28)   a:28   r:0.0%   
 - layer1: via traefik direct: h:100.0% (0/224)  a:244  r:8.9%   
 - layer2: via load balancers: h:100.0% (0/16)   a:16   r:0.0%   
 - layer3: via normal fqdns :  h:75.0%  (4/16)   a:24   r:50.0%  
----------------------------------------------------------

----------------------------------------------------------
my-app-prod-11-beta2_app
    100.0% (1) (previous) 1084.7ms
----------------------------------------------------------
 - l0: h:100.0% (0/14)   a:14   r:0.0%   3497.0ms
 - l1: h:100.0% (0/84)   a:98   r:16.7%  674.0ms
 - l2: h:100.0% (0/6)    a:6    r:0.0%   1416.0ms
 - l3: h:100.0% (0/6)    a:6    r:0.0%   871.0ms

 ----------------------------------------------------------
my-app-pre-prod-12-beta3_app
     97.7% (1) (current) 804.2ms
 ----------------------------------------------------------
  - l0: h:100.0% (0/14)   a:14   r:0.0%   3695.0ms
  - l1: h:100.0% (0/140)  a:146  r:4.3%   462.0ms
  - l2: h:100.0% (0/10)   a:10   r:0.0%   1664.0ms
  - l3: h:60.0%  (4/10)   a:18   r:80.0%  693.0ms
       (3): (<class 'urllib.error.URLError'>, URLError(gaierror(8, 'nodename nor servname provided, or not known'),))
           curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://my-app-pre-prod-12-beta3.test.com/health
           curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://my-app-pre-prod-beta.test.com/health
           curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://my-app-pre-prod-joedev.test.com/health
       (1): (<class 'urllib.error.URLError'>, URLError(timeout('timed out',),))
           curl -v --retry 3 -k -m 5 -X GET --header 'test2: yes' https://bitsofinfo.test.com/health


 RAW RESULTS --> healthcheckerdb.json
 THE ABOVE ON DISK --> healthcheckerreport.md
```

## [swarm-name].yml files

```
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

## service-state.yml files

```
formal_name: "my-servicename"

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

health_checks:
  - ports: [443]
    path: "/health"
    layers: [0,1,2,3]
    headers:
      - "test2: yes"
    method: "GET"
    timeout: 10
    retries: 3
    tags: ["foo"]
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
      body_regex: "result = 100A"
    timeout: 5
    retries: 5
    classifiers: ["mode-a"]
    tags: ["bar"]
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
