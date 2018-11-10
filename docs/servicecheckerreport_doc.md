## <a id="servicecheckerreport"></a>servicecheckerreport.py

[Back to main README](../README.md)

This script consumes the service check result output from `servicecheckerdb.py` and produces a simple markdown report dumped to the consul and output to a file.

This report is pretty simplistic but gives a decent summary of the state of access to services on the target swarm.

```bash
./servicecheckerreport.py --help

usage: servicecheckerreport.py [-h] [-i INPUT_FILENAME] [-o OUTPUT_FILENAME]
                               [-v] [-x LOG_LEVEL] [-l LOG_FILE] [-p]

optional arguments:
  -h, --help            show this help message and exit
  -i INPUT_FILENAME, --input-filename INPUT_FILENAME
                        Filename of service check result database, default
                        'servicecheckerdb.json'
  -o OUTPUT_FILENAME, --output-filename OUTPUT_FILENAME
                        Filename of the markdown report to generate, default
                        'servicecheckerreport.md'
  -v, --verbose         verbose details in report, default False
  -x LOG_LEVEL, --log-level LOG_LEVEL
                        log level, default DEBUG
  -l LOG_FILE, --log-file LOG_FILE
                        Path to log file, default None, STDOUT
  -p, --report-stdout   print servicecheckerreport output to STDOUT in
                        addition to file, default False
```

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

[Back to main README](../README.md)
