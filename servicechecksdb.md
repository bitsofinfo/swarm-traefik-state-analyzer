## <a id="servicechecksdb"></a>servicechecksdb.py

[Back to main README](README.md)

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
* `--fqdn-filter`: regex string to limit urls that get computed for checks within specified layers
* `--input-filename`: path where the JSON output of `swarmstatedb.py` is
* `--output-filename`: path where the JSON output will be written
* `--log-file`: path to log file, otherwise STDOUT
* `--log-level`: python log level (DEBUG, WARN ... etc)

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

[Back to main README](README.md)
