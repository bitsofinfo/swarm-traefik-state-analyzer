## <a id="analyze-swarm-traefik-state"></a>analyze-swarm-traefik-state.py

[Back to main README](../README.md)

This script orchestrates all the following steps with one command:

1. Invokes: [swarmstatedb.py](swarmstatedb.md) to collect raw docker swarm service state database
1. Invokes: [servicechecksdb.py](servicechecksdb.md)to create database of service checks for the swarm state
1. Invokes: [servicechecker.py](servicechecker.md) which executes the service checks, captures results
1. Invokes: [servicecheckerreport.py](servicecheckerreport.md) reads and prepares a simple report  

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
  --output-dir output/ \
  --stdout-servicecheckerreport-result \
  [--verbose]
```

Options:
* `--stdout-servicecheckerreport-result`: print servicecheckerreport.md output to STDOUT in addition to file
* `--stdout-servicechecker-result`: print servicechecker raw results to STDOUT in addition to disk
* `--log-stdout`: will log to STDOUT, if not present will log within `--output-dir`
* `--log-level`: python log level (DEBUG, WARN ... etc)
* `--fqdn-filter`: regex string to limit urls that get computed for checks within specified layers
* `--sleep-seconds`: The max amount of time to sleep between all attempts for each service check; if > 0, the actual sleep will be a random time from 0 to this value
* `--daemon`: Run as a long lived process, re-analyzing per interval settings
* `--daemon-interval-seconds`: When in daemon mode, how long to sleep between runs, default 300
* `--daemon-interval-randomize`: When in daemon mode, if enabled, will randomize the sleep between --daemon-interval-seconds and (--daemon-interval-seconds X 2)
* `--pre-analyze-script-path`: Optional, path to executable/script that will be invoked prior to starting any analysis. If --daemon this will be invoked at the start of each iteration.
* `--retain-output-hours`: Optional, default 1, the number of hours of data to retain, purges output dirs older than this time threshold
* `--service-name-exclude-regex`: Optional, to further refine the set of services by docker service name that are returned via the --service-filter, will exclude any services matching this regex`

The meaning for the options above are the same as and described in the separate sections above for each separate module

[Back to main README](../README.md)
