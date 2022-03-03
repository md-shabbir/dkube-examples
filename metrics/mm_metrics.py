import urllib3
from prometheus_api_client.metric_range_df import MetricRangeDataFrame
from prometheus_api_client import PrometheusConnect
from prometheus_api_client.utils import parse_datetime
from datetime import timedelta
import argparse
import os,sys
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parser = argparse.ArgumentParser(description='Compute min/max/mean/std on monitoring metrics.')
parser.add_argument('-i', "--id", required=True, help='deployment id')
parser.add_argument('-n', type=int, required=True, help="Use metric data from last N days")
parser.add_argument('-t', dest='type', required=True, choices=['health', 'drift', 'performance'],help="metric type")
parser.add_argument('-r', type=int, default=1, help="compute metric statistics on R day interval ")
parser.add_argument('-s', type=int, default=1, help="metrics sampling period as configured in DKube")
parser.add_argument('-o','--output', type=argparse.FileType('w'), default='-', help="CSV output file")

args = parser.parse_args()

token = os.environ.get("DKUBE_USER_ACCESS_TOKEN")
dkube_url = os.environ.get("DKUBE_URL")

if not token or not dkube_url:
    print("DKUBE_USER_ACCESS_TOKEN and DKUBE_URL env variable needs to be set.")
    sys.exit(-1)
    
headers = {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/json",
}
prom = PrometheusConnect(url =f"{dkube_url}/dkube/v2/prometheus/", headers=headers, disable_ssl=True)

end_time = parse_datetime("now")
start_time = end_time - timedelta(days=args.n)
duration = args.s * 2
deployment_id=args.id

queries = {
    "health" : {
        "requests_rate" : f"sum(rate(deployment_predictions_total{{id='{deployment_id}', response_code_class='2xx'}}[{duration}m]))",
        "4xx_requests_rate" : f"sum(rate(deployment_predictions_total{{id='{deployment_id}', response_code_class='4xx'}}[{duration}m]))",
        "5xx_requests_rate" : f"sum(rate(deployment_predictions_total{{id='{deployment_id}', response_code_class='5xx'}}[{duration}m]))",
        "latency" : f"sum(rate(deployment_latency_sum{{id='{deployment_id}'}}[{duration}m])) / sum(rate(deployment_latency_count{{id='{deployment_id}'}}[{duration}m]))",
        "cpu_utilization" : f"sum(rate(deployment_cpu_usage_total{{id='{deployment_id}'}}[{duration}m]))",
        "memory_utilization": f"sum(deployment_memory_usage{{id='{deployment_id}'}})"
    }
}

output = []

while start_time < end_time:
    
    dfs = []
    for metric,query in queries[args.type].items():
        data = prom.custom_query_range(
            query,
            start_time=start_time,
            end_time=start_time + timedelta(days=1),
            step=f"{args.s}m",
        )

        df=MetricRangeDataFrame(data, columns=["timestamp","value"], dtype="Float64")
        df=df.describe(percentiles=[]).rename(columns = {'value': metric })
        dfs.append(df)

    start_time += timedelta(days=1)
    df = pd.concat(dfs, axis=1)
    df["date"] = start_time.date()
    output.append(df)
    
df = pd.concat(output)
df=df.set_index(['date'], append=True).reorder_levels(order = [1,0]).sort_index()

if args.output == sys.stdout:
    pd.options.display.width=None
    pd.set_option('display.float_format', lambda x: '%.3f' % x)
    print(df)
else:
    df.to_csv(args.output)