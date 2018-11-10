## <a id="analyze-swarm-traefik-state"></a>analyze-swarm-traefik-state.py

[Back to main README](../README.md)

This script orchestrates all the following steps with one command:

1. Invokes: [swarmstatedb.py](swarmstatedb.md) to collect raw docker swarm service state database
1. Invokes: [servicechecksdb.py](servicechecksdb.md)to create database of service checks for the swarm state
1. Invokes: [servicechecker.py](servicechecker.md) which executes the service checks, captures results
1. Invokes: [servicecheckerreport.py](servicecheckerreport_doc.md) reads and prepares a simple report  

All of the data generated from `analyze-swarm-traefik-state.py` is stored by default under the `output/` dir within the working directory

```bash
./analyze-swarm-traefik-state.py --help

analyze-swarm-traefik-state.py [-h] -j JOB_NAME -d SWARM_INFO_REPO_ROOT
                                      -s SERVICE_STATE_REPO_ROOT -n SWARM_NAME
                                      [-f SERVICE_FILTER] [-o OUTPUT_DIR] [-v]
                                      [-l LAYERS [LAYERS ...]]
                                      [-g TAGS [TAGS ...]] [-a FQDN_FILTER]
                                      [-t THREADS] [-S SLEEP_SECONDS]
                                      [-r MAX_RETRIES] [-x LOG_LEVEL] [-e]
                                      [-p] [-z] [-m]
                                      [-q DAEMON_INTERVAL_SECONDS] [-c]
                                      [-y PRE_ANALYZE_SCRIPT_PATH]
                                      [-u RETAIN_OUTPUT_HOURS]
                                      [-w SERVICE_NAME_EXCLUDE_REGEX]

optional arguments:
  -h, --help            show this help message and exit
  -j JOB_NAME, --job-name JOB_NAME
                        descriptive name for this execution
  -d SWARM_INFO_REPO_ROOT, --swarm-info-repo-root SWARM_INFO_REPO_ROOT
                        dir that anywhere in its subdirectories contains
                        `[swarm-name].yml` yaml config files
  -s SERVICE_STATE_REPO_ROOT, --service-state-repo-root SERVICE_STATE_REPO_ROOT
                        dir that anywhere in its subdirectories contains
                        `service-state.yml` yaml config files
  -n SWARM_NAME, --swarm-name SWARM_NAME
                        The logical name of the swarm name you want to grab
                        service state from, i.e. the [swarm-name].yml file to
                        consume
  -f SERVICE_FILTER, --service-filter SERVICE_FILTER
                        i.e. '{"name":"my-app"}' Valid filters: id, name ,
                        label and mode, default None i.e all
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Directory where all output generated will be placed
                        under, default 'output'
  -v, --verbose         verbose output for servicecheckerreport, default False
  -l LAYERS [LAYERS ...], --layers LAYERS [LAYERS ...]
                        Space separated list of layer checks to generate i.e
                        '0 1 2 3 4', default all
  -g TAGS [TAGS ...], --tags TAGS [TAGS ...]
                        Space separated list of health check tags to include
                        i.e 'health tag1 tag2 etc', default 'health'
  -a FQDN_FILTER, --fqdn-filter FQDN_FILTER
                        Regex filter to limit which FQDNs are included in
                        service checks for all --layers being checked, default
                        None
  -t THREADS, --threads THREADS
                        max threads for processing checks, default 30, higher
                        = faster completion, adjust as necessary to avoid
                        DOSing...
  -S SLEEP_SECONDS, --sleep-seconds SLEEP_SECONDS
                        The max amount of time to sleep between all attempts
                        for each service check; if > 0, the actual sleep will
                        be a random time from 0 to this value, default 0
  -r MAX_RETRIES, --max-retries MAX_RETRIES
                        maximum retries per check, overrides service-state
                        service check configs, default 3
  -x LOG_LEVEL, --log-level LOG_LEVEL
                        log level, default DEBUG
  -e, --log-stdout      Log to STDOUT, if not present will create logfile
                        under --output-dir
  -p, --stdout-servicecheckerreport-result
                        print servicecheckerreport.md output to STDOUT in
                        addition to file, default False
  -z, --stdout-servicechecker-result
                        print servicechecker raw results to STDOUT in addition
                        to disk, default False
  -m, --daemon          Run as a long lived process, re-analyzing per interval
                        settings, if omitted, will run 1x and exit
  -q DAEMON_INTERVAL_SECONDS, --daemon-interval-seconds DAEMON_INTERVAL_SECONDS
                        When in daemon mode, how long to sleep between runs,
                        default 300
  -c, --daemon-interval-randomize
                        When in daemon mode, if enabled, will randomize the
                        sleep between --daemon-interval-seconds and (--daemon-
                        interval-seconds X 2), default False
  -y PRE_ANALYZE_SCRIPT_PATH, --pre-analyze-script-path PRE_ANALYZE_SCRIPT_PATH
                        Optional, path to executable/script that will be
                        invoked prior to starting any analysis. No arguments,
                        STDOUT captured and logged. If --daemon this will be
                        invoked at the start of each iteration.
  -u RETAIN_OUTPUT_HOURS, --retain-output-hours RETAIN_OUTPUT_HOURS
                        Optional, default 1, the number of hours of data to
                        retain, purges output dirs older than this time
                        threshold
  -w SERVICE_NAME_EXCLUDE_REGEX, --service-name-exclude-regex SERVICE_NAME_EXCLUDE_REGEX
                        Optional, to further refine the set of services by
                        docker service name that are returned via the
                        --service-filter, will exclude any services matching
                        this regex, default None
```

[Back to main README](../README.md)
