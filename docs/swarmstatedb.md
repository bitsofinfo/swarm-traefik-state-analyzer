## <a id="swarmstatedb"></a>swarmstatedb.py

[Back to main README](../README.md)

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
* `--log-file`: path to log file, otherwise STDOUT
* `--log-level`: python log level (DEBUG, WARN ... etc)
* `--service-name-exclude-regex`: Optional, to further refine the set of services by docker service name that are returned via the --service-filter, will exclude any services matching this regex

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
    }
```

[Back to main README](../README.md)
