#!/usr/bin/env python

from prometheus_client import start_http_server, Summary
import random
import argparse
import time
from prometheus_client import Counter
from prometheus_client import Gauge
from prometheus_client import Summary
from prometheus_client import Histogram
import sys
import time
import json
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# makes name "metric" name compliant
def m(s):
    return s.replace("-","_")


class HealthCheckerDbHandler(FileSystemEventHandler):

    counters_db = {}
    gauges_db = {}
    summaries_db = {}
    histograms_db = {}

    def observe_histogram(self, value, metric_name, desc,formal_name,layer,swarm,context,classifier,version,tags,docker_service_name):
        if metric_name not in self.histograms_db:
            self.histograms_db[metric_name] = Histogram(metric_name, desc,['formal_name','layer','swarm','context','classifier','version','tags','docker_service_name'])
        self.histograms_db[metric_name].labels(formal_name,layer,swarm,context,classifier,version,tags,docker_service_name).observe(value)

    def observe_summary(self, value, metric_name, desc,formal_name,layer,swarm,context,classifier,version,tags,docker_service_name):
        if metric_name not in self.summaries_db:
            self.summaries_db[metric_name] = Summary(metric_name, desc,['formal_name','layer','swarm','context','classifier','version','tags','docker_service_name'])
        self.summaries_db[metric_name].labels(formal_name,layer,swarm,context,classifier,version,tags,docker_service_name).observe(value)

    def set_gauge(self, value, metric_name, desc,formal_name,layer,swarm,context,classifier,version,tags,docker_service_name):
        if metric_name not in self.gauges_db:
            self.gauges_db[metric_name] = Gauge(metric_name, desc,['formal_name','layer','swarm','context','classifier','version','tags','docker_service_name'])
        self.gauges_db[metric_name].labels(formal_name,layer,swarm,context,classifier,version,tags,docker_service_name).set(value)

    def inc_counter(self, inc_by, metric_name, desc, formal_name,layer,swarm,context,classifier,version,tags,docker_service_name):
        if metric_name not in self.counters_db:
            self.counters_db[metric_name] = Counter(metric_name, desc, ['formal_name','layer','swarm','context','classifier','version','tags','docker_service_name'])
        self.counters_db[metric_name].labels(formal_name,layer,swarm,context,classifier,version,tags,docker_service_name).inc(inc_by)

    def record_metrics(self, formal_name, metrics, layer, swarm,context,classifier,version,tags,docker_service_name):
        self.inc_counter(metrics['total_ok'],("sts_analyzer_analyzer_c_ok_total"),("Cumulative total OK"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.inc_counter(metrics['total_fail'],("sts_analyzer_analyzer_c_fail_total"),("Cumulative total FAILED"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.inc_counter(metrics['total_attempts'],("sts_analyzer_analyzer_c_attempts_total"),("Cumulative total attempts"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)

        self.set_gauge(metrics['health_rating'],"sts_analyzer_analyzer_g_health_rating","Most recent % OK checks for",formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.set_gauge(metrics['retry_percentage'],"sts_analyzer_analyzer_g_retry_percentage","Most recent % of checks that had to be retried",formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.set_gauge(metrics['fail_percentage'],"sts_analyzer_analyzer_g_fail_percentage","Most recent % of checks that have failed",formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.set_gauge(metrics['total_ok'],("sts_analyzer_analyzer_g_ok"),("Most recent total OK checks"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.set_gauge(metrics['total_fail'],("sts_analyzer_analyzer_g_failures"),("Most recent total FAILED checks"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.set_gauge(metrics['total_attempts'],("sts_analyzer_analyzer_g_attempts"),("Most recent total ATTEMPTS checks"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        self.set_gauge((metrics['avg_resp_time_ms'] / 1000.0),("sts_analyzer_analyzer_g_avg_resp_time_seconds"),("Average response time for checks in seconds"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)

    def record_all_metrics(self, formal_name, context, classifier, swarm, version,tags,docker_service_name,metrics):
        for l in range(0,5):
            layer = "layer"+str(l)
            self.record_metrics(formal_name,metrics[layer],layer,swarm,context,classifier,version,tags,docker_service_name)

    def on_created(self, event):
        super(HealthCheckerDbHandler, self).on_created(event)

        if event.is_directory:
            return

        if 'servicecheckerdb' in event.src_path:

            logging.info("Responding to creation of %s: %s", "file", event.src_path)

            # give write time to close....
            time.sleep(10)

            health_result_db = {}
            with open(event.src_path) as f:
                health_result_db = json.load(f)

            logging.info("Processing servicecheckerdb: '%s'", health_result_db['name'])

            # process service records for each one
            swarm_names_recorded = []
            for service_result in health_result_db['service_results']:

                service_record = service_result['service_record']

                if service_record['replicas'] == 0:
                    continue

                metrics = service_result['metrics']
                formal_name = service_record['formal_name']
                context = service_record['context']['name']
                version = service_record['context']['version']
                tags = service_record['context']['tags']
                classifier = service_record['classifier']
                swarm_name = service_record['swarm_name']
                docker_service_name = service_record['name']

                if classifier is None:
                    classifier = "none"

                tags_str = "none"
                if tags is not None and len(tags) > 0:
                    tags_str = ",".join(tags)

                # Service level metrics
                self.record_all_metrics(m(formal_name),m(context),classifier,swarm_name,version,tags_str,m(docker_service_name),metrics)



###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-dir', dest='input_dir', default="./output", help="Directory path to recursively monitor for new '*servicecheckerdb*' json output files")
    parser.add_argument('-p', '--metrics-port', dest='metrics_port', default=8000, help="HTTP port to expose /metrics at")
    parser.add_argument('-x', '--minstdout', action="store_true",help="minimize stdout output")

    args = parser.parse_args()

    # Start up the server to expose the metrics.
    start_http_server(args.metrics_port)

    print("Exposing metrics at: http://localhost:" + args.metrics_port + "/metrics")
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    event_handler = HealthCheckerDbHandler()
    observer = Observer()
    observer.schedule(event_handler, args.input_dir, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
