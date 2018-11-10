## <a id="swarmstatedb"></a>swarmstatedb.py

[Back to main README](../README.md)

This script will interrogate a target swarm for services matching `--service-filter` and dump a summarized subset of the relevant information in a JSON file which can then be consumed by `servicechecksdb.py`...or whatever else you want to do with it. The information it extracts contains published port information, traefik labels, image info, number of replicas amongst other things.

```bash
./swarmstatedb.py --help

usage: swarmstatedb.py [-h] [-o OUTPUT_FILENAME] -d SWARM_INFO_REPO_ROOT -s
                       SWARM_NAME [-f SERVICE_FILTER] [-x LOG_LEVEL]
                       [-l LOG_FILE] [-n SERVICE_NAME_EXCLUDE_REGEX]

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT_FILENAME, --output-filename OUTPUT_FILENAME
                        Output filename to write the swarm service state to,
                        default 'swarmstatedb.json'
  -d SWARM_INFO_REPO_ROOT, --swarm-info-repo-root SWARM_INFO_REPO_ROOT
                        dir that anywhere in its subdirectories contains
                        `[swarm-name].yml` yaml config files
  -s SWARM_NAME, --swarm-name SWARM_NAME
                        The logical name of the swarm name you want to grab
                        service state from, i.e. the [swarm-name].yml file to
                        consume
  -f SERVICE_FILTER, --service-filter SERVICE_FILTER
                        i.e. '{"name":"my-app"}' Valid filters: id, name ,
                        label and mode, default None; i.e. all
  -x LOG_LEVEL, --log-level LOG_LEVEL
                        log level, default DEBUG
  -l LOG_FILE, --log-file LOG_FILE
                        Path to log file, default None, STDOUT
  -n SERVICE_NAME_EXCLUDE_REGEX, --service-name-exclude-regex SERVICE_NAME_EXCLUDE_REGEX
                        Optional, to further refine the set of services by
                        docker service name that are returned via the
                        --service-filter, will exclude any services matching
                        this regex, default None
```

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
