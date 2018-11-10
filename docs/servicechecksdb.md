## <a id="servicechecksdb"></a>servicechecksdb.py

[Back to main README](../README.md)

This script consumes the output from `swarmstatedb.py` and supplements it with information from `[swarm-name].yml`, and one or more relevant `service-state.yml` files to compute an exhaustive list of all possible ingress paths to invoke the appropriate service checks for each service exposed on the swarm via each layer of access (0:swarm direct, 1:traefik direct, 2:load-balancers, and 3:normal fqdns).

Depending on the number of ports your application exposes, number of swarm nodes and corresponding Traefik frontend `Host` header based labels you have applied to a service... this can result many pre-computed ingress check combinations.

You can use the generated JSON file that contains all the necessary information (urls, headers, methods, payloads etc) to drive any monitoring system you'd like.... or just feed into the provided `servicechecker.py` to execute all the service checks and write a detailed report out... again in JSON.

Note you an also use this file as input to [testsslinputgenerator.py](tlsssltools.md)

```bash
./servicechecksdb.py --help

usage: servicechecksdb.py [-h] [-i INPUT_FILENAME] -s SERVICE_STATE_REPO_ROOT
                          -d SWARM_INFO_REPO_ROOT [-o OUTPUT_FILENAME]
                          [-l LAYERS [LAYERS ...]] [-g TAGS [TAGS ...]]
                          [-x LOG_LEVEL] [-f LOG_FILE] [-e FQDN_FILTER]

optional arguments:
  -h, --help            show this help message and exit
  -i INPUT_FILENAME, --input-filename INPUT_FILENAME
                        Filename of swarm state to consume, default
                        'swarmstatedb.json'
  -s SERVICE_STATE_REPO_ROOT, --service-state-repo-root SERVICE_STATE_REPO_ROOT
                        dir that anywhere in its subdirectories contains
                        `[swarm-name].yml` yaml config files
  -d SWARM_INFO_REPO_ROOT, --swarm-info-repo-root SWARM_INFO_REPO_ROOT
                        dir that anywhere in its subdirectories contains
                        `service-state.yml` yaml config files
  -o OUTPUT_FILENAME, --output-filename OUTPUT_FILENAME
                        Ouput filename for all the generated service checks
                        db, default 'servicechecksdb.json'
  -l LAYERS [LAYERS ...], --layers LAYERS [LAYERS ...]
                        Space separated list of layer checks to generate i.e
                        '0 1 2 3 4', default all
  -g TAGS [TAGS ...], --tags TAGS [TAGS ...]
                        Space separated list of health check tags to include
                        i.e 'health tag1 tag2 etc', default 'health'
  -x LOG_LEVEL, --log-level LOG_LEVEL
                        log level, default DEBUG
  -f LOG_FILE, --log-file LOG_FILE
                        Path to log file, default None, STDOUT
  -e FQDN_FILTER, --fqdn-filter FQDN_FILTER
                        Regex filter to limit which FQDNs checks actually get
                        computed within --layers being checked, default None
```

Decorates additional info to `swarmstatedb` output from `service-state.yml` files:
```
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
  "unique_entrypoint_uris": {
      "via_direct": [
          "https://myswarm1-node1.test.com:30001"
      ],
      "via_fqdn": [
          "https://myswarm1-extlb.test.com"
      ]
  },
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

[Back to main README](../README.md)
