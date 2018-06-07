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
import datetime
import dateutil.parser
import logging
import socket
import pprint
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from http import HTTPStatus
from urllib.parse import urlparse
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

# makes name "metric" name compliant
def m(s):
    return s.replace("-","_")

# determine if string is int
def stringIsInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

# a prometheus client_python
# custom "Collector": https://github.com/prometheus/client_python
# This classes collect() method is called periodically
# and it dumps the current state of the job_name_2_metrics_db
# database of metrics
class STSACollector(object):

    # for controlling access to job_name_2_metrics_db
    lock = threading.RLock()

    # default life of all metrics
    # stored in job_name_2_metrics_db
    # before they are purged
    metric_ttl_seconds = 600

    # current database of our
    # metrics state organized by job_name
    # collect() always dumps the current
    # state of what is in here
    job_name_2_metrics_db = {}

    # Will analyze the service servicechekerdb file located
    # at the given path and create approproiate metrics
    # for it
    def processServicecheckerDb(self,servicecheckerdb_path):

        # open the file
        servicecheckerdb = {}

        with open(servicecheckerdb_path) as f:
            servicecheckerdb = json.load(f)

        job_name = servicecheckerdb['name']
        job_id = servicecheckerdb['id']

        logging.info("Processing servicecheckerdb: '%s'", job_id)

        latest_job_metrics = []

        # process service records for each one
        for service_result in servicecheckerdb['service_results']:
            collected_metrics = self.processServiceResult(service_result)
            latest_job_metrics.extend(collected_metrics)

        # hotswap and replace latest metrics..
        try:
            self.lock.acquire()
            self.job_name_2_metrics_db[job_name] = latest_job_metrics
        finally:
            self.lock.release()

    # if the metric's 'created_at' is is beyond the metric_ttl_seconds
    def metricIsExpired(self,metric_def):
        iso_utc_str = metric_def['created_at']
        iso_utc = dateutil.parser.parse(iso_utc_str)
        diff_seconds = (datetime.datetime.utcnow()-iso_utc).total_seconds()
        if diff_seconds > self.metric_ttl_seconds:
            return True
        return False


    # this is invoked by prometheus_client.core
    # on some sort of schedule or by request to get
    # latest metrics
    def collect(self):

        try:
            self.lock.acquire()

            gauges_db = {}

            # 1. build our in-memory set of current state
            # of all metrics via Gauges
            for job_name in self.job_name_2_metrics_db:

                metrics = self.job_name_2_metrics_db[job_name]

                for metric_def in metrics:

                    metric_name = metric_def['name']
                    metric_type = metric_def['metric_type']

                    if self.metricIsExpired(metric_def):
                        logging.debug("Skipping expired metric: %s %s", metric_name, metric_def['created_at'])
                        continue;

                    if metric_type in 'gauge':
                        if metric_name not in gauges_db:
                            gauges_db[metric_name] = GaugeMetricFamily(metric_name,metric_def['desc'],labels=list(metric_def['labels'].keys()))

                        gauges_db[metric_name].add_metric(list(metric_def['labels'].values()),metric_def['value'])
                    else:
                        logging.error("Unrecognized metric_type: %s ... skipping...", metric_type)


            # 2. Once built yield every Gauge
            for metric_name in gauges_db:
                yield gauges_db[metric_name]

        except Exception:
            logger.exception("Unexpected error in collect()")

        finally:
            self.lock.release()


    def processServiceResult(self,service_result):

        metrics_2_return = []

        # return quick if zero replicas...
        service_record = service_result['service_record']
        if service_record['replicas'] == 0:
            return metrics_2_return

        service_record = service_result['service_record']

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

        if version is None:
            version = "unknown"

        if context is None:
            context = "unknown"

        tags_str = "none"
        if tags is not None and len(tags) > 0:
            tags_str = ",".join(tags)


        # Service level metrics
        metrics_2_return.extend(self.get_all_metrics(m(formal_name),m(context),classifier,swarm_name,version,tags_str,m(docker_service_name),metrics,service_record))

        return metrics_2_return

    def get_service_layer_error_gauge_def(self,
                                          value,
                                          metric_name,
                                          desc,
                                          formal_name,
                                          layer,
                                          swarm,
                                          context,
                                          classifier,
                                          version,
                                          tags,
                                          docker_service_name,
                                          service_check_url,
                                          service_check_host,
                                          service_check_port,
                                          service_check_path,
                                          service_check_url_dns,
                                          error_key):
        return { 'name' : metric_name,
                 'desc' :  desc,
                 'label_schema' : "service_layer_error",
                 'metric_type': 'gauge',
                 'value': value,
                 'created_at': datetime.datetime.utcnow().isoformat(),
                 'labels': {'formal_name':formal_name,
                             'layer':layer,
                             'swarm':swarm,
                             'context':context,
                             'classifier':classifier,
                             'version':version,
                             'tags':tags,
                             'docker_service_name':docker_service_name,
                             'url':service_check_url,
                             'host':service_check_host,
                             'port':service_check_port,
                             'path':service_check_path,
                             'dns':service_check_url_dns,
                             'error':error_key}
                    }


    def get_service_gauge_def(self, value, metric_name, desc,formal_name,swarm,context,classifier,version,tags,docker_service_name):
        return { 'name' : metric_name,
                 'desc' :  desc,
                 'label_schema' : "service",
                 'metric_type': 'gauge',
                 'value': value,
                 'created_at': datetime.datetime.utcnow().isoformat(),
                 'labels': {'formal_name':formal_name,
                             'swarm':swarm,
                             'context':context,
                             'classifier':classifier,
                             'version':version,
                             'tags':tags,
                             'docker_service_name':docker_service_name}
                    }

    def get_service_layer_gauge_def(self, value, metric_name, desc,formal_name,layer,swarm,context,classifier,version,tags,docker_service_name):
        return { 'name' : metric_name,
                 'desc' :  desc,
                 'label_schema' : "service_layer",
                 'metric_type': 'gauge',
                 'value': value,
                 'created_at': datetime.datetime.utcnow().isoformat(),
                 'labels': {'formal_name':formal_name,
                             'layer':layer,
                             'swarm':swarm,
                             'context':context,
                             'classifier':classifier,
                             'version':version,
                             'tags':tags,
                             'docker_service_name':docker_service_name}
                    }

    def get_metrics_for_layer(self, formal_name, service_record, metrics, layer, swarm,context,classifier,version,tags,docker_service_name):
        #self.inc_counter(metrics['total_ok'],("sts_analyzer_c_ok_total"),("Cumulative total OK"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        #self.inc_counter(metrics['total_fail'],("sts_analyzer_c_fail_total"),("Cumulative total FAILED"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)
        #self.inc_counter(metrics['total_attempts'],("sts_analyzer_c_attempts_total"),("Cumulative total attempts"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name)

        gs = []

        gs.append(self.get_service_layer_gauge_def(metrics['health_rating'],"sts_analyzer_g_health_rating","Most recent % OK checks for",formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(metrics['retry_percentage'],"sts_analyzer_g_retry_percentage","Most recent % of checks that had to be retried",formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(metrics['fail_percentage'],"sts_analyzer_g_fail_percentage","Most recent % of checks that have failed",formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(metrics['total_ok'],("sts_analyzer_g_ok"),("Most recent total OK checks"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(metrics['total_fail'],("sts_analyzer_g_failures"),("Most recent total FAILED checks"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(metrics['total_fail']+metrics['total_ok'],("sts_analyzer_g_total_checks"),("Most recent total checks executed"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(metrics['total_attempts'],("sts_analyzer_g_attempts"),("Most recent total ATTEMPTS checks"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def((metrics['avg_resp_time_ms'] / 1000.0),("sts_analyzer_g_avg_resp_time_seconds"),("Average response time for checks in seconds"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def((metrics['total_req_time_ms'] / 1000.0),("sts_analyzer_g_total_resp_time_seconds"),("Total response time for checks in seconds"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))
        gs.append(self.get_service_layer_gauge_def(service_record['replicas'],("sts_analyzer_g_replicas"),("Most recent total replicas"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name))

        # lets create stats for each failed attempt paths/error stats
        failed_attempt_stats = metrics['failed_attempt_stats']
        for service_check_url in failed_attempt_stats:
            url_errors = failed_attempt_stats[service_check_url]

            # lets breakup the url into some more labels
            service_check_url_host = None
            service_check_url_dns = None
            service_check_url_path = None
            service_check_url_port = None
            try:
                parsed = urlparse(service_check_url)
                service_check_url_path = parsed.path

                if ":" in parsed.netloc:
                    service_check_url_host = parsed.netloc.split(":")[0]
                    service_check_url_port = parsed.netloc.split(":")[1]

                else:
                    service_check_url_host = parsed.netloc
                    if 'https' in parsed.scheme:
                        service_check_url_port = "443"
                    else:
                        service_check_url_port = "80"

                service_check_url_dns = socket.gethostbyname(service_check_url_host)
            except Exception as e:
                service_check_url_dns = "lookup_fail"

            # now lets create a guage for each url/error
            for attempt_error in url_errors:

                error_short_key = attempt_error
                error_count = url_errors[attempt_error]

                # lets shorten certain types of errors
                if 'timeout' in attempt_error or 'timed out' in attempt_error:
                    error_short_key = "timeout"
                elif 'body_evaluator' in attempt_error:
                    error_short_key = "bodyeval_fail"
                elif 'nodename nor servname provided, or not known' in attempt_error:
                    error_short_key = "dns_fail"
                elif 'Connection refused' in attempt_error:
                    error_short_key = "conn_refused"
                else:
                    # convert any messages w/ a status code into code only
                    for s in list(HTTPStatus):
                        if str(s.value) in attempt_error:
                            error_short_key = str(s.value)
                            break

                gs.append(self.get_service_layer_error_gauge_def(error_count,("sts_analyzer_g_attempt_errors"),("Most recent total attempt errors"),formal_name,layer,swarm,context,classifier,version,tags,docker_service_name,service_check_url,service_check_url_host,service_check_url_port,service_check_url_path,service_check_url_dns,error_short_key))

        return gs

    def get_all_metrics(self, formal_name, context, classifier, swarm, version,tags,docker_service_name, metrics, service_record):
        to_return = []

        # Metric for the service "existence" itself
        to_return.append(self.get_service_gauge_def(1, "sts_analyzer_g_services","Current total number of services with 1+ replicas",m(formal_name),swarm,m(context),classifier,version,tags,docker_service_name))

        # layer specific metrics...
        for l in range(0,5):
            layer = "layer"+str(l)

            # if nothing was actually checked for they layer
            # lets flag it as 100 for purposes of how prometheus
            # grafana metrics are averaged across all layers
            if metrics[layer]['health_rating'] == 0 and metrics[layer]['total_attempts'] == 0:
                metrics[layer]['health_rating'] = 100

            to_return.extend(self.get_metrics_for_layer(formal_name,service_record,metrics[layer],layer,swarm,context,classifier,version,tags,docker_service_name))

        return to_return



class ServiceCheckerDBMonitor(FileSystemEventHandler):

    # we need to register new service-checker db
    # file paths to process with this collector
    stsa_collector = None

    def on_created(self, event):
        super(ServiceCheckerDBMonitor, self).on_created(event)

        if event.is_directory:
            return

        if 'servicecheckerdb' in event.src_path:

            logging.info("Responding to creation of %s: %s", "file", event.src_path)

            # give write time to close....
            time.sleep(10)

            # process path...
            self.stsa_collector.processServicecheckerDb(event.src_path)


###########################
# Main program
##########################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-dir', dest='input_dir', default="./output", help="Directory path to recursively monitor for new '*servicecheckerdb*' json output files")
    parser.add_argument('-p', '--metrics-port', dest='metrics_port', default=8000, help="HTTP port to expose /metrics at")
    parser.add_argument('-t', '--metric-ttl-seconds', dest='metric_ttl_seconds', default=300, help="TTL for generated metrics that will be exposed. This value should be > than the interval that new *servicecheckerdb*.json are created")
    parser.add_argument('-l', '--log-file', dest='log_file', default=None, help="Path to log file, default None, STDOUT")
    parser.add_argument('-x', '--log-level', dest='log_level', default="DEBUG", help="log level, default DEBUG ")

    args = parser.parse_args()

    logging.basicConfig(level=logging.getLevelName(args.log_level),
                        format='%(asctime)s - %(message)s',
                        filename=args.log_file,filemode='w')
    logging.Formatter.converter = time.gmtime

    # create watchdog to look for new files
    event_handler = ServiceCheckerDBMonitor()

    # create prometheus python client collector for metrics
    # our watchdog registers files to process in this collector
    event_handler.stsa_collector = STSACollector()
    event_handler.stsa_collector.metric_ttl_seconds = int(args.metric_ttl_seconds)

    # schedule our file watchdog
    observer = Observer()
    observer.schedule(event_handler, args.input_dir, recursive=True)
    observer.start()

    REGISTRY.register(event_handler.stsa_collector)

    # Start up the server to expose the metrics.
    start_http_server(int(args.metrics_port))



    logging.info("Exposing servicecheckerdb metrics for Prometheus at: http://localhost:%s/metrics",str(args.metrics_port))


    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
