from flask import Blueprint, request, jsonify
from flask.views import MethodView
from app.models import ServiceGroup
from app.auth.helper import token_required
from datetime import date, datetime
from app.core import es_client


perf_data_app = Blueprint('perf_data', __name__)


class ManagePerfDataView(MethodView):
    def post(self, jwt, hostname, timespan):

      if request.is_json and request.get_json(silent=True) is not None:
        post_data = request.get_json()
        servicename = post_data.get('service_name')

        query = {
                  "size": 100,
                  "query": {
                    "bool": {
                      "must": [
                        {
                          "term": {
                            "hostname.keyword": hostname
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

        if servicename != "ALLSERVICE":
          service_match = {"term": {"service_name.keyword": servicename}}
          query["query"]["bool"]["must"].append(service_match)

        from_date = ""
        to_date = ""
        if timespan == "manual":
          from_date = request.args.get('from_date', post_data.get('start_time') / 1000)
          to_date = request.args.get('to_date', post_data.get('end_time') / 1000)
        else:
          #Default only pull last 24 hours of data.
          from_date = request.args.get('from_date', datetime.now().timestamp() - float(timespan) * 3600)
          to_date = request.args.get('to_date', datetime.now().timestamp())

        if from_date:
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

        response = []
        nums = []
        response = es_client.search(index='perf_metric', scroll='10s',
                                      body=query, stored_fields=['_source'])
        sid = response['_scroll_id']
        fetched = len(response['hits']['hits'])
        nums = response.get('hits', {}).get('hits', [])

        while(fetched > 0):
          response = es_client.scroll(scroll_id=sid, scroll='10s')
          fetched = len(response['hits']['hits'])
          nums.extend(response.get('hits', {}).get('hits', []))


        #Trying to limit the results returned for now just working on 1 month.


        response = []
        last_time_stamp = {}

        #If the selected time is greater then 7 days
        if to_date-from_date > 90000:
            # 0.000683508 x + 0.69634 = r | where x = number of minutes in the time period
            # r = number of minutes that should be between samples
            #                                                SamplePriodToMinutes            Back to seconds
            seconds_to_wait_for_next_result = (0.000683508*((to_date-from_date)/60)+0.69634)*60
            for result in nums:
                if result["_source"]["service_name"] in last_time_stamp:
                    if result["_source"]["timestamp"] > (last_time_stamp[result["_source"]["service_name"]] + seconds_to_wait_for_next_result):
                        last_time_stamp[result["_source"]["service_name"]] = result["_source"]["timestamp"]
                        response.append(result)
                else:
                    last_time_stamp[result["_source"]["service_name"]] = result["_source"]["timestamp"]
                    response.append(result)
        else:
            response = nums


        return jsonify(data=response, from_date=from_date, to_date=to_date)
      return jsonify(error=True)


manage_perf_data_view = token_required(ManagePerfDataView.as_view('manage_perf_data_view'))


# perf_data_app.add_url_rule(
#     '/perf_data/',
#     defaults={'service_id': None},
#     view_func=manage_perf_data_view,
#     methods=['GET']
# )

perf_data_app.add_url_rule(
    '/perf_data/<string:hostname>/<string:timespan>/',
    view_func=manage_perf_data_view,
    methods=['POST']
)
