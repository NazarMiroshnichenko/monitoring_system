from flask import Blueprint
from datetime import datetime
from app.core import es_client


perf_data_app = Blueprint('perf_data', __name__)


def get_perfdata(host_name, service_name, timespan):
    """Return services perfdata.

    Args:
        host_name(str): The first parameter.
        service_name(str): The second parameter.
        timespan(int): The third parameter.

    Returns:
        list: The return value.
    """

    query = {
        "size": 100,
        "query": {
            "bool": {
                "must": [
                    {
                        "term": {
                            "hostname.keyword": host_name
                        }
                    }
                ]
            }
        },
        "sort": [
            {
                "timestamp": {
                    "order": "asc"
                }
            }
        ]
    }

    if service_name != "ALLSERVICE":
        service_match = {"term": {"service_name.keyword": service_name}}
        query["query"]["bool"]["must"].append(service_match)

    from_date = datetime.now().timestamp() - float(timespan) * 3600
    to_date = datetime.now().timestamp()

    range_match = {"range":
        {
            "timestamp":
                {
                    "gte": from_date,
                    "lte": to_date
                }
        }
    }
    query["query"]["bool"]["must"].append(range_match)

    response = es_client.search(index='perf_metric', scroll='10s', body=query, stored_fields=['_source'])
    sid = response['_scroll_id']
    fetched = len(response['hits']['hits'])
    nums = response.get('hits', {}).get('hits', [])

    while fetched > 0:
        response = es_client.scroll(scroll_id=sid, scroll='10s')
        fetched = len(response['hits']['hits'])
        nums.extend(response.get('hits', {}).get('hits', []))

    # Trying to limit the results returned for now just working on 1 month.

    response = []
    last_time_stamp = {}

    # If the selected time is greater then 7 days
    if to_date - from_date > 90000:
        # 0.000683508 x + 0.69634 = r | where x = number of minutes in the time period
        # r = number of minutes that should be between samples
        #                                                SamplePriodToMinutes            Back to seconds
        seconds_to_wait_for_next_result = (0.000683508 * ((to_date - from_date) / 60) + 0.69634) * 60
        for result in nums:
            if result["_source"]["service_name"] in last_time_stamp:
                if result["_source"]["timestamp"] > (
                    last_time_stamp[result["_source"]["service_name"]] + seconds_to_wait_for_next_result):
                    last_time_stamp[result["_source"]["service_name"]] = result["_source"]["timestamp"]
                    response.append(result)
            else:
                last_time_stamp[result["_source"]["service_name"]] = result["_source"]["timestamp"]
                response.append(result)
    else:
        response = nums

    return response

