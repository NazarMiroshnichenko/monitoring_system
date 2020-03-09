from flask import Blueprint, request, jsonify, make_response
from flask.views import MethodView
from app.models import Host, Service
from app.auth.helper import token_required
from datetime import date, datetime
import requests
from requests.auth import HTTPBasicAuth
from math import floor
from app.nagios_functions.helper import get_nagios_status, get_nagios_statusdat_exist, sizeof_bps_fmt
from app import db
import os
import random
import sys
from app.core import es_client
from app.status_data.helper import *


status_data_app = Blueprint('status_data', __name__)

#I'm not sure this will actually ever get used.
#Gets data for a specific service or all services
class ManageServiceStatusDataView(MethodView):
    def get(self, jwt, service_id=None):
        data = []

        #If no service_id is passed in get all data else get for just one service.
        if (service_id is None):
            #get data for all services
            return jsonify(error=True, msg="Queries for all data take too long. Please write the UI to query one at a time as needed.")
        elif service_id:
            #get data for one service requested
            service = Service.get_by_id(service_id)

        if service is None:
            return jsonify(error=True, msg="No service found.")

        nagios_user = os.getenv(
            'NAGIOS_USERNAME',
            'nagiosadmin'
        )
        nagios_password = os.getenv(
            'NAGIOS_PASSWORD',
            'nagios'
        )

        auth = HTTPBasicAuth(nagios_user, nagios_password)
        service_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=service&formatoptions=enumerate' + \
            '&hostname=' + service.host_name + '&servicedescription=' + service.service_description
        service_response = requests.get(service_url, auth=auth)
        data = [{
            "service_description": service.service_description,
            "id": service.id,
            "status": service_response.json()["data"]["service"]["status"],
            "host_name" : service.host_name
        }]

        return jsonify(data=data)

#This will be the one that is probably always used.
#Gets data for a host and all of its attached services
#or Gets data for all hosts and all of their attached services
class ManageHostStatusDataView(MethodView):
    def get(self, jwt, host_id=None, host_name=None):
        data = []

        #If no host_id is passed in get all data else get for just one host.
        if (host_id is None) and (host_name is None):
            #get data for all hosts
            return jsonify(error=True, msg="Queries for all data take too long. Please write the UI to query one at a time as needed.")
        elif host_id:
            #get data for one host requested
            host = Host.get_by_id(host_id)
        elif host_name:
            #get data for one host requested
            host = Host.get_by_hostname(host_name)

        if host is None:
            return jsonify(error=True, msg="No host found.")

        services = Service.get_all_by_host_name(host.host_name)

        nagios_user = os.getenv(
            'NAGIOS_USERNAME',
            'nagiosadmin'
        )
        nagios_password = os.getenv(
            'NAGIOS_PASSWORD',
            'nagios'
        )
        auth = HTTPBasicAuth(nagios_user, nagios_password)
        host_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=host&formatoptions=enumerate&hostname=' + \
            str(host.host_name)

        host_response = requests.get(host_url, auth=auth)

        services_status = []

        # Add PING service
        service_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=service&formatoptions=enumerate' + \
                '&hostname=' + host.host_name + '&servicedescription=PING'
        service_response = requests.get(service_url, auth=auth)
        services_status.append({
            "service_description": "PING",
            "id": "0",
            "service_plugin_output": service_response.json()["data"]["service"]["plugin_output"],
            "status": service_response.json()["data"]["service"]["status"]
        })

        for service in services:
            service_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=service&formatoptions=enumerate' + \
                '&hostname=' + host.host_name + '&servicedescription=' + service.service_description
            service_response = requests.get(service_url, auth=auth)
            services_status.append({
                "service_description": service.service_description,
                "id": service.id,
                "service_plugin_output": service_response.json()["data"]["service"]["plugin_output"],
                "status": service_response.json()["data"]["service"]["status"]
            })

        data = [
            {
                "host_name": host.host_name,
                "id": host.id,
                "status": host_response.json()["data"]["host"]["status"],
                "services_status": services_status
            }
        ]

        return jsonify(data=data)

#Gets total count for UP/DOWN status of hosts and services
class ManageHostServiceStatusTotalView(MethodView):
    def post(self, jwt, page_id, status_id):
        data = []
        nagios_user = os.getenv(
            'NAGIOS_USERNAME',
            'nagiosadmin'
        )
        nagios_password = os.getenv(
            'NAGIOS_PASSWORD',
            'nagios'
        )
        auth = HTTPBasicAuth(nagios_user, nagios_password)

        if  page_id is None:
            try:
                # Get hosts status from nagios server
                host_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=hostcount&formatoptions=enumerate'
                host_response = requests.get(host_url, auth=auth)
                host_up_count = host_response.json()["data"]["count"]["up"]
                host_down_count = host_response.json()["data"]["count"]["down"]
                host_unreachable_count = host_response.json()["data"]["count"]["unreachable"]
                host_pending_count = host_response.json()["data"]["count"]["pending"]

                # Get services status from nagios server
                service_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=servicecount&formatoptions=enumerate'

                service_response = requests.get(service_url, auth=auth)

                serivce_ok_count = service_response.json()["data"]["count"]["ok"]
                serivce_warning_count = service_response.json()["data"]["count"]["warning"]
                serivce_critical_count = service_response.json()["data"]["count"]["critical"]
                serivce_unknown_count = service_response.json()["data"]["count"]["unknown"]
                serivce_pending_count = service_response.json()["data"]["count"]["pending"]

                data = [
                    {
                        "host_up": host_up_count,
                        "host_down": host_down_count,
                        "host_unreachable": host_unreachable_count,
                        "host_pending": host_pending_count,
                        "service_ok": serivce_ok_count,
                        "service_warning": serivce_warning_count,
                        "service_critical": serivce_critical_count,
                        "service_unknown": serivce_unknown_count,
                        "service_pending": serivce_pending_count
                    }
                ]
            except:
                data = []

            return jsonify(data=data)

        elif status_id != 0:

            statusData = get_nagios_status()
            post_data = request.get_json()
            count = post_data.get('rows_count', 10)
            found_count = 0
            first_id = post_data.get('first_id')
            last_id = post_data.get('last_id')
            user_filter = post_data.get('filter')
            f_hostname_ip = user_filter.get('hostname')
            f_description = user_filter.get('description')
            ret_first_id = -1
            ret_last_id = -1
            params = {}
            found_first = False

            while found_count < count:

                if first_id > 0:
                    if found_first == True:
                        params = {
                            'host_id': first_id,
                            'search_type': 'gt',
                            'hostname_ip': f_hostname_ip,
                            'description': f_description
                        }
                    else:
                        params = {
                            'host_id': first_id,
                            'search_type': 'egt',
                            'hostname_ip': f_hostname_ip,
                            'description': f_description
                        }
                else:
                    params = {
                        'host_id': last_id,
                        'search_type': 'gt',
                        'hostname_ip': f_hostname_ip,
                        'description': f_description
                    }

                host = Host.get_next_by_id(**params)

                if host is None:
                    break
                found_first = True
                host.host_name = host.host_name.strip()

                found = False

                if status_id == 1:
                    if statusData['hosts'][host.host_name]['current_state'] == str(0):
                        found = True
                else:
                    if statusData['hosts'][host.host_name]['current_state'] != str(0):
                        found = True

                if found == True:
                    found_count += 1

                    obj = {
                        "id": host.id,
                        "host_name": host.host_name,
                        "host_status": "",
                        "service_name": "",
                        "service_status": "",
                        "street_address": host.street_address,
                        "plugin_output": "",
                        "service_plugin_output": "",
                        "ip_address": host.address,
                        "last_time": "",
                        "alias": host.alias
                    }

                    if statusData['hosts'][host.host_name]['current_state'] == "0":
                        obj["host_status"] = "Up"
                    elif statusData['hosts'][host.host_name]['current_state'] == "1":
                        obj["host_status"] = "Down"
                    elif statusData['hosts'][host.host_name]['current_state'] == "2":
                        obj["host_status"] = "Down"
                    else:
                        obj["host_status"] = "Down"

                    obj["plugin_output"] = statusData['hosts'][host.host_name]["plugin_output"]
                    obj["last_time"] = statusData['hosts'][host.host_name]["last_state_change"]

                    service_names_str = ""
                    service_status_str = ""
                    service_plugin_str = ""
                    index = 0
                    servicelist = []
                    servicelist = statusData['hosts'][host.host_name]['services']

                    for serivce in servicelist:
                        if index == 0:
                            service_names_str = serivce['service_description']
                            service_plugin_str = serivce['plugin_output']
                            if serivce['current_state'] == "0":
                                service_status_str = "Ok"
                            elif serivce['current_state'] == "1":
                                service_status_str = "Warning"
                            elif serivce['current_state'] == "2":
                                service_status_str = "Critical"
                            elif serivce['current_state'] == "3":
                                service_status_str = "Unknown"
                            else:
                                service_status_str = "Pending"
                        else:
                            service_names_str = service_names_str + "," + serivce['service_description']
                            service_plugin_str = service_plugin_str + "|" + serivce['plugin_output']
                            if serivce['current_state'] == "0":
                                service_status_str = service_status_str + "," + "Ok"
                            elif serivce['current_state'] == "1":
                                service_status_str = service_status_str + "," + "Warning"
                            elif serivce['current_state'] == "2":
                                service_status_str = service_status_str + "," + "Critical"
                            elif serivce['current_state'] == "3":
                                service_status_str = service_status_str + "," + "Unknown"
                            else:
                                service_status_str = service_status_str + "," + "Pending"
                        index += 1

                    obj["service_name"] = service_names_str
                    obj["service_status"] = service_status_str
                    obj["service_plugin_output"] = service_plugin_str

                    data.append(obj)

                last_id = host.id
                first_id = host.id

            if len(data) > 0:
                ret_first_id = data[0]["id"]
                ret_last_id = data[len(data)-1]["id"]

            return jsonify({
                'data': data,
                'first_id': ret_first_id,
                'last_id': ret_last_id
            })

        else:
            statusData = get_nagios_status()
            post_data = request.get_json()
            count = post_data.get('rows_count', 10)
            first_id = post_data.get('first_id')
            last_id = post_data.get('last_id')

            ret_first_id = -1
            ret_last_id = -1
            hosts = []
            if first_id > 0:
                params = {
                    'user_filter': post_data.get('filter'),
                    'host_id': first_id,
                    'search_type': 'egt',
                    'count': count
                }
            else:
                params = {
                    'user_filter': post_data.get('filter'),
                    'host_id': last_id,
                    'search_type': 'gt',
                    'count': count
                }

            hosts = Host.search_by_id(**params)

            if not hosts:
                return make_response(jsonify({
                    'status': 'error',
                    'message': 'Hosts was not found.'
                })), 400

            for host in hosts:
                host.host_name = host.host_name.strip()

                obj = {
                    "id": host.id,
                    "host_name": host.host_name,
                    "host_status": "",
                    "street_address": host.street_address,
                    "plugin_output": "",
                    "service_name": "",
                    "service_status": "",
                    "service_plugin_output": "",
                    "ip_address": host.address,
                    "last_time": "",
                    "alias": host.alias
                }

                if statusData is not None and 'hosts' in statusData.keys() and len(statusData['hosts']) > 0:
                    try:
                        if statusData['hosts'][host.host_name]['current_state'] == "0":
                            obj["host_status"] = "Up"
                        elif statusData['hosts'][host.host_name]['current_state'] == "1":
                            obj["host_status"] = "Down"
                        elif statusData['hosts'][host.host_name]['current_state'] == "2":
                            obj["host_status"] = "Down"
                        else:
                            obj["host_status"] = "Down"

                        obj["plugin_output"] = statusData['hosts'][host.host_name]["plugin_output"]
                        obj["last_time"] = statusData['hosts'][host.host_name]["last_state_change"]

                        servicelist = statusData['hosts'][host.host_name]['services']
                        service_names_str = ""
                        service_status_str = ""
                        service_plugin_str = ""
                        index = 0
                        services_data = []

                        for service in servicelist:

                            if service['current_state'] == "0":
                                service_status = "Ok"
                            elif service['current_state'] == "1":
                                service_status = "Warning"
                            elif service['current_state'] == "2":
                                service_status = "Critical"
                            elif service['current_state'] == "3":
                                service_status = "Unknown"
                            else:
                                service_status = "Pending"

                            services_data.append({
                                'service_name': service['service_description'],
                                'service_plugin_output': service['plugin_output'],
                                'service_status': service_status,
                                'id': f'{host.host_name}-{service["service_description"]}'
                            })

                            if index == 0:
                                service_names_str = service['service_description']
                                service_plugin_str = service['plugin_output']
                                if service['current_state'] == "0":
                                    service_status_str = "Ok"
                                elif service['current_state'] == "1":
                                    service_status_str = "Warning"
                                elif service['current_state'] == "2":
                                    service_status_str = "Critical"
                                elif service['current_state'] == "3":
                                    service_status_str = "Unknown"
                                else:
                                    service_status_str = "Pending"
                            else:
                                service_names_str = service_names_str + "," + service['service_description']
                                service_plugin_str = service_plugin_str + "|" + service['plugin_output']
                                if service['current_state'] == "0":
                                    service_status_str = service_status_str + "," + "Ok"
                                elif service['current_state'] == "1":
                                    service_status_str = service_status_str + "," + "Warning"
                                elif service['current_state'] == "2":
                                    service_status_str = service_status_str + "," + "Critical"
                                elif service['current_state'] == "3":
                                    service_status_str = service_status_str + "," + "Unknown"
                                else:
                                    service_status_str = service_status_str + "," + "Pending"
                            index += 1

                        obj["service_name"] = service_names_str
                        obj["service_status"] = service_status_str
                        obj["service_plugin_output"] = service_plugin_str
                        obj["services"] = services_data
                    except:
                        #TODO: Log that there was a key error.
                        pass

                data.append(obj)

            if len(hosts) > 0:
                ret_first_id = hosts[0].id
                ret_last_id = hosts[len(hosts)-1].id

            # Find hosts and fixup snmpdata
            for the_data in data:
                query = {
                  "size": 2,
                  "query": {
                    "bool": {
                      "must": [
                        {
                          "term": {
                            "hostname.keyword": the_data["host_name"]
                          }
                        }
                      ]
                    }
                  },
                  "sort": [
                    {
                      "timestamp": {
                        "order": "desc"
                      }
                    }
                  ]
                }
                from_date = request.args.get('from_date', datetime.now().timestamp() - 3600)
                to_date = request.args.get('to_date', datetime.now().timestamp())
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
                response = nums

                services_data = {}
                for items in response:
                    if all(key in items['_source'] for key in ('type', 'snmp_type', 'snmp_subtype')):
                        if items['_source']['type'] == "SNMP":
                            if items['_source']['snmp_type'] == "traffic":
                                if items['_source']['snmp_subtype'] == "u":
                                    if not items['_source']['service_name'] in services_data:
                                        services_data[items['_source']['service_name']] = {
                                            "snmp_subtype": "u",
                                            "high_timestamp": {
                                                "timestamp": 0,
                                                "ifHCInUcastPkts": 0,
                                                "ifHCOutUcastPkts": 0
                                                }
                                            ,
                                            "low_timestamp":{
                                                "timestamp": sys.maxsize,
                                                "ifHCInUcastPkts": 0,
                                                "ifHCOutUcastPkts": 0
                                            }
                                        }
                                    if "ifHCInUcastPkts" in items['_source']:
                                        if "ifHCOutUcastPkts" in items['_source']:
                                            if items['_source']['timestamp'] > services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"]:
                                                services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                services_data[items['_source']['service_name']]["high_timestamp"]["ifHCInUcastPkts"] = items['_source']['ifHCInUcastPkts']
                                                services_data[items['_source']['service_name']]["high_timestamp"]["ifHCOutUcastPkts"] = items['_source']['ifHCOutUcastPkts']
                                            if items['_source']['timestamp'] < services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"]:
                                                services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                services_data[items['_source']['service_name']]["low_timestamp"]["ifHCInUcastPkts"] = items['_source']['ifHCInUcastPkts']
                                                services_data[items['_source']['service_name']]["low_timestamp"]["ifHCOutUcastPkts"] = items['_source']['ifHCOutUcastPkts']

                                if items['_source']['snmp_subtype'] == "e":
                                    if not items['_source']['service_name'] in services_data:
                                        services_data[items['_source']['service_name']] = {
                                            "snmp_subtype": "e",
                                            "high_timestamp": {
                                                "timestamp": 0,
                                                "ifInErrors": 0,
                                                "ifOutErrors": 0
                                                }
                                            ,
                                            "low_timestamp":{
                                                "timestamp": sys.maxsize,
                                                "ifInErrors": 0,
                                                "ifOutErrors": 0
                                            }
                                        }
                                    if "ifInErrors" in items['_source']:
                                        if "ifOutErrors" in items['_source']:
                                            if items['_source']['timestamp'] > services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"]:
                                                services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                services_data[items['_source']['service_name']]["high_timestamp"]["ifInErrors"] = items['_source']['ifInErrors']
                                                services_data[items['_source']['service_name']]["high_timestamp"]["ifOutErrors"] = items['_source']['ifOutErrors']
                                            if items['_source']['timestamp'] < services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"]:
                                                services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                services_data[items['_source']['service_name']]["low_timestamp"]["ifInErrors"] = items['_source']['ifInErrors']
                                                services_data[items['_source']['service_name']]["low_timestamp"]["ifOutErrors"] = items['_source']['ifOutErrors']

                                if items['_source']['snmp_subtype'] == "i":
                                    if not items['_source']['service_name'] in services_data:
                                        services_data[items['_source']['service_name']] = {
                                            "snmp_subtype": "i",
                                            "high_timestamp": {
                                                "timestamp": 0,
                                                "ifHCInOctets": 0,
                                                "ifHCOutOctets": 0
                                                }
                                            ,
                                            "low_timestamp":{
                                                "timestamp": sys.maxsize,
                                                "ifHCInOctets": 0,
                                                "ifHCOutOctets": 0
                                            }
                                        }
                                    if "ifHCInOctets" in items['_source']:
                                        if "ifHCOutOctets" in items['_source']:
                                            if items['_source']['timestamp'] > services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"]:
                                                services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                services_data[items['_source']['service_name']]["high_timestamp"]["ifHCInOctets"] = items['_source']['ifHCInOctets']
                                                services_data[items['_source']['service_name']]["high_timestamp"]["ifHCOutOctets"] = items['_source']['ifHCOutOctets']
                                            if items['_source']['timestamp'] < services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"]:
                                                services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                services_data[items['_source']['service_name']]["low_timestamp"]["ifHCInOctets"] = items['_source']['ifHCInOctets']
                                                services_data[items['_source']['service_name']]["low_timestamp"]["ifHCOutOctets"] = items['_source']['ifHCOutOctets']

                if "services" in the_data:
                    for a_service in the_data["services"]:
                        if a_service["service_name"] in services_data:
                            if services_data[a_service["service_name"]]["snmp_subtype"] == "i":
                                inputRate = "Input: Err "
                                outputRate = "Output: Err "
                                try:
                                    time_diff = services_data[a_service["service_name"]]["high_timestamp"]["timestamp"]-services_data[a_service["service_name"]]["low_timestamp"]["timestamp"]
                                    input_diff = services_data[a_service["service_name"]]["high_timestamp"]["ifHCInOctets"]-services_data[a_service["service_name"]]["low_timestamp"]["ifHCInOctets"]
                                    output_diff = services_data[a_service["service_name"]]["high_timestamp"]["ifHCOutOctets"]-services_data[a_service["service_name"]]["low_timestamp"]["ifHCOutOctets"]

                                    if time_diff > 0:
                                        # diff / time * 8 to get bps.  These are octect counters we are reading so they read bytes.
                                        inputRate = "Input: %s" % sizeof_bps_fmt(input_diff/time_diff*8)
                                        outputRate = "Output: %s" % sizeof_bps_fmt(output_diff/time_diff*8)
                                except:
                                    pass

                                a_service["service_plugin_output"] = inputRate + "\n" + outputRate
                            if services_data[a_service["service_name"]]["snmp_subtype"] == "u":
                                inputRate = "Input: Err "
                                outputRate = "Output: Err "
                                try:
                                    time_diff = services_data[a_service["service_name"]]["high_timestamp"]["timestamp"]-services_data[a_service["service_name"]]["low_timestamp"]["timestamp"]
                                    input_diff = services_data[a_service["service_name"]]["high_timestamp"]["ifHCInUcastPkts"]-services_data[a_service["service_name"]]["low_timestamp"]["ifHCInUcastPkts"]
                                    output_diff = services_data[a_service["service_name"]]["high_timestamp"]["ifHCOutUcastPkts"]-services_data[a_service["service_name"]]["low_timestamp"]["ifHCOutUcastPkts"]

                                    if time_diff > 0:
                                        # diff / time * 8 to get bps.  These are octect counters we are reading so they read bytes.
                                        inputRate = "Input: %s" % sizeof_bps_fmt(input_diff/time_diff, unit="pps")
                                        outputRate = "Output: %s" % sizeof_bps_fmt(output_diff/time_diff, unit="pps")
                                except:
                                    pass

                                a_service["service_plugin_output"] = inputRate + "\n" + outputRate
                            if services_data[a_service["service_name"]]["snmp_subtype"] == "e":
                                inputRate = "Input: Err "
                                outputRate = "Output: Err "
                                try:
                                    time_diff = services_data[a_service["service_name"]]["high_timestamp"]["timestamp"]-services_data[a_service["service_name"]]["low_timestamp"]["timestamp"]
                                    input_diff = services_data[a_service["service_name"]]["high_timestamp"]["ifInErrors"]-services_data[a_service["service_name"]]["low_timestamp"]["ifInErrors"]
                                    output_diff = services_data[a_service["service_name"]]["high_timestamp"]["ifOutErrors"]-services_data[a_service["service_name"]]["low_timestamp"]["ifOutErrors"]

                                    if time_diff > 0:
                                        # diff / time * 8 to get bps.  These are octect counters we are reading so they read bytes.
                                        inputRate = "Input: %s" % (str(input_diff/time_diff) + " errors per second")
                                        outputRate = "Output: %s" % (str(output_diff/time_diff) + " errors per second")
                                except:
                                    pass

                                a_service["service_plugin_output"] = inputRate + "\n" + outputRate

            return jsonify({
                'data': data,
                'first_id': ret_first_id,
                'last_id': ret_last_id
            })

class ManageHostServiceStatusRowView(MethodView):
    def post(self, jwt, row_num, status_id):
        data = []
        nagios_user = os.getenv(
            'NAGIOS_USERNAME',
            'nagiosadmin'
        )
        nagios_password = os.getenv(
            'NAGIOS_PASSWORD',
            'nagios'
        )
        auth = HTTPBasicAuth(nagios_user, nagios_password)
        count = 10

        if status_id != 0:

            statusData = get_nagios_status()
            post_data = request.get_json()
            sort_field = post_data.get('sort_field')
            sort_dir = post_data.get('sort_dir')
            user_filter = post_data.get('filter')
            include_service = post_data.get('include_service')
            found_count = 0

            while found_count < count:

                params = {
                    'user_filter': user_filter,
                    'sort_field': sort_field,
                    'sort_dir': sort_dir,
                    'last_rownum': row_num,
                    'count': 1
                }

                hosts = Host.search_by_rownum(**params)

                if hosts is None or len(hosts) == 0:
                    break
                host = hosts[0]
                found = False

                if status_id == 1:
                    if statusData['hosts'][host['host_name'].strip()]['current_state'] == str(0):
                        found = True
                else:
                    if statusData['hosts'][host['host_name'].strip()]['current_state'] != str(0):
                        found = True

                if found == True:
                    found_count += 1

                    if len(statusData['hosts']) > 0:
                        if statusData['hosts'][host['host_name'].strip()]['current_state'] == "0":
                            host["host_status"] = "UP"
                        elif statusData['hosts'][host['host_name'].strip()]['current_state'] == "1":
                            host["host_status"] = "DOWN"
                        elif statusData['hosts'][host['host_name'].strip()]['current_state'] == "2":
                            host["host_status"] = "DOWN"
                        else:
                            host["host_status"] = "DOWN"

                        host["plugin_output"] = statusData['hosts'][host['host_name'].strip()]["plugin_output"]
                        host["last_state_change"] = statusData['hosts'][host['host_name'].strip()]["last_state_change"]
                        host["last_check"] = statusData['hosts'][host['host_name'].strip()]["last_check"]

                        if include_service == True:
                            host["services"] = statusData['hosts'][host['host_name'].strip()]['services']

                            for idx in range(len(host["services"])):
                                if host['services'][idx]['current_state'] == "0":
                                    host['services'][idx]['current_state_str'] = "OK"
                                elif host['services'][idx]['current_state'] == "1":
                                    host['services'][idx]['current_state_str'] = "WARNING"
                                elif host['services'][idx]['current_state'] == "2":
                                    host['services'][idx]['current_state_str']= "CRITICAL"
                                elif host['services'][idx]['current_state'] == "3":
                                    host['services'][idx]['current_state_str']= "UNKNOWN"
                                else:
                                    host['services'][idx]['current_state_str'] = "PENDING"
                    else:
                        host["host_status"] = "UNKNOWN"

                    data.append(host)

                row_num = host['row_num']

            return jsonify({
                'data': data
            })

        else:
            if request.is_json and request.get_json(silent=True) is not None:
                statusData = get_nagios_status()
                post_data = request.get_json()
                sort_field = post_data.get('sort_field')
                sort_dir = post_data.get('sort_dir')
                include_service = post_data.get('include_service')
                total_count = post_data.get('count')
                if total_count == 0:
                    count = total_count

                hosts = []
                params = {
                    'user_filter': post_data.get('filter'),
                    'sort_field': sort_field,
                    'sort_dir': sort_dir,
                    'last_rownum': row_num,
                    'count': count
                }

                hosts = Host.search_by_rownum(**params)

                if hosts is not None:
                    for host in hosts:
                        if statusData is not None and 'hosts' in statusData.keys() and len(statusData['hosts']) > 0:
                            try:
                                if statusData['hosts'][host['host_name'].strip()]['current_state'] == "0":
                                    host["host_status"] = "UP"
                                elif statusData['hosts'][host['host_name'].strip()]['current_state'] == "1":
                                    host["host_status"] = "DOWN"
                                elif statusData['hosts'][host['host_name'].strip()]['current_state'] == "2":
                                    host["host_status"] = "DOWN"
                                else:
                                    host["host_status"] = "DOWN"

                                host["plugin_output"] = statusData['hosts'][host['host_name'].strip()]["plugin_output"]
                                host["last_state_change"] = statusData['hosts'][host['host_name'].strip()]["last_state_change"]
                                host["last_check"] = statusData['hosts'][host['host_name'].strip()]["last_check"]

                                if include_service == True:
                                    host["services"] = statusData['hosts'][host['host_name'].strip()]['services']

                                    for idx in range(len(host["services"])):
                                        if host['services'][idx]['current_state'] == "0":
                                            host['services'][idx]['current_state_str'] = "OK"
                                        elif host['services'][idx]['current_state'] == "1":
                                            host['services'][idx]['current_state_str'] = "WARNING"
                                        elif host['services'][idx]['current_state'] == "2":
                                            host['services'][idx]['current_state_str']= "CRITICAL"
                                        elif host['services'][idx]['current_state'] == "3":
                                            host['services'][idx]['current_state_str']= "UNKNOWN"
                                        else:
                                            host['services'][idx]['current_state_str'] = "PENDING"
                            except:
                                #TODO: Log that there was a key error.
                                host["host_status"] = "UNKNOWN"
                        else:
                            host["host_status"] = "UNKNOWN"

                        data.append(host)

                # Find hosts and fixup snmpdata
                for the_data in data:
                    query = {
                    "size": 2,
                    "query": {
                        "bool": {
                        "must": [
                            {
                            "term": {
                                "hostname.keyword": the_data["host_name"]
                            }
                            }
                        ]
                        }
                    },
                    "sort": [
                        {
                        "timestamp": {
                            "order": "desc"
                        }
                        }
                    ]
                    }
                    from_date = request.args.get('from_date', datetime.now().timestamp() - 3600)
                    to_date = request.args.get('to_date', datetime.now().timestamp())
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
                    response = nums

                    services_data = {}
                    for items in response:
                        if all(key in items['_source'] for key in ('type', 'snmp_type', 'snmp_subtype')):
                            if items['_source']['type'] == "SNMP":
                                if items['_source']['snmp_type'] == "traffic":
                                    if items['_source']['snmp_subtype'] == "u":
                                        if not items['_source']['service_name'] in services_data:
                                            services_data[items['_source']['service_name']] = {
                                                "snmp_subtype": "u",
                                                "high_timestamp": {
                                                    "timestamp": 0,
                                                    "ifHCInUcastPkts": 0,
                                                    "ifHCOutUcastPkts": 0
                                                    }
                                                ,
                                                "low_timestamp":{
                                                    "timestamp": sys.maxsize,
                                                    "ifHCInUcastPkts": 0,
                                                    "ifHCOutUcastPkts": 0
                                                }
                                            }
                                        if "ifHCInUcastPkts" in items['_source']:
                                            if "ifHCOutUcastPkts" in items['_source']:
                                                if items['_source']['timestamp'] > services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"]:
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["ifHCInUcastPkts"] = items['_source']['ifHCInUcastPkts']
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["ifHCOutUcastPkts"] = items['_source']['ifHCOutUcastPkts']
                                                if items['_source']['timestamp'] < services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"]:
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["ifHCInUcastPkts"] = items['_source']['ifHCInUcastPkts']
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["ifHCOutUcastPkts"] = items['_source']['ifHCOutUcastPkts']

                                    if items['_source']['snmp_subtype'] == "e":
                                        if not items['_source']['service_name'] in services_data:
                                            services_data[items['_source']['service_name']] = {
                                                "snmp_subtype": "e",
                                                "high_timestamp": {
                                                    "timestamp": 0,
                                                    "ifInErrors": 0,
                                                    "ifOutErrors": 0
                                                    }
                                                ,
                                                "low_timestamp":{
                                                    "timestamp": sys.maxsize,
                                                    "ifInErrors": 0,
                                                    "ifOutErrors": 0
                                                }
                                            }
                                        if "ifInErrors" in items['_source']:
                                            if "ifOutErrors" in items['_source']:
                                                if items['_source']['timestamp'] > services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"]:
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["ifInErrors"] = items['_source']['ifInErrors']
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["ifOutErrors"] = items['_source']['ifOutErrors']
                                                if items['_source']['timestamp'] < services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"]:
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["ifInErrors"] = items['_source']['ifInErrors']
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["ifOutErrors"] = items['_source']['ifOutErrors']

                                    if items['_source']['snmp_subtype'] == "i":
                                        if not items['_source']['service_name'] in services_data:
                                            services_data[items['_source']['service_name']] = {
                                                "snmp_subtype": "i",
                                                "high_timestamp": {
                                                    "timestamp": 0,
                                                    "ifHCInOctets": 0,
                                                    "ifHCOutOctets": 0
                                                    }
                                                ,
                                                "low_timestamp":{
                                                    "timestamp": sys.maxsize,
                                                    "ifHCInOctets": 0,
                                                    "ifHCOutOctets": 0
                                                }
                                            }
                                        if "ifHCInOctets" in items['_source']:
                                            if "ifHCOutOctets" in items['_source']:
                                                if items['_source']['timestamp'] > services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"]:
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["ifHCInOctets"] = items['_source']['ifHCInOctets']
                                                    services_data[items['_source']['service_name']]["high_timestamp"]["ifHCOutOctets"] = items['_source']['ifHCOutOctets']
                                                if items['_source']['timestamp'] < services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"]:
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["timestamp"] = items['_source']['timestamp']
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["ifHCInOctets"] = items['_source']['ifHCInOctets']
                                                    services_data[items['_source']['service_name']]["low_timestamp"]["ifHCOutOctets"] = items['_source']['ifHCOutOctets']
                    # Todo: Make this not suck
                    if "services" in the_data:
                        for a_service in the_data["services"]:
                            if a_service["service_description"] in services_data:
                                if services_data[a_service["service_description"]]["snmp_subtype"] == "i":
                                    inputRate = "Input: Err "
                                    outputRate = "Output: Err "
                                    try:
                                        time_diff = services_data[a_service["service_description"]]["high_timestamp"]["timestamp"]-services_data[a_service["service_description"]]["low_timestamp"]["timestamp"]
                                        input_diff = services_data[a_service["service_description"]]["high_timestamp"]["ifHCInOctets"]-services_data[a_service["service_description"]]["low_timestamp"]["ifHCInOctets"]
                                        output_diff = services_data[a_service["service_description"]]["high_timestamp"]["ifHCOutOctets"]-services_data[a_service["service_description"]]["low_timestamp"]["ifHCOutOctets"]

                                        if time_diff > 0:
                                            # diff / time * 8 to get bps.  These are octect counters we are reading so they read bytes.
                                            inputRate = "Input: %s" % sizeof_bps_fmt(input_diff/time_diff*8)
                                            outputRate = "Output: %s" % sizeof_bps_fmt(output_diff/time_diff*8)
                                    except:
                                        pass

                                    a_service["plugin_output"] = inputRate + "\n" + outputRate
                                if services_data[a_service["service_description"]]["snmp_subtype"] == "u":
                                    inputRate = "Input: Err "
                                    outputRate = "Output: Err "
                                    try:
                                        time_diff = services_data[a_service["service_description"]]["high_timestamp"]["timestamp"]-services_data[a_service["service_description"]]["low_timestamp"]["timestamp"]
                                        input_diff = services_data[a_service["service_description"]]["high_timestamp"]["ifHCInUcastPkts"]-services_data[a_service["service_description"]]["low_timestamp"]["ifHCInUcastPkts"]
                                        output_diff = services_data[a_service["service_description"]]["high_timestamp"]["ifHCOutUcastPkts"]-services_data[a_service["service_description"]]["low_timestamp"]["ifHCOutUcastPkts"]

                                        if time_diff > 0:
                                            # diff / time * 8 to get bps.  These are octect counters we are reading so they read bytes.
                                            inputRate = "Input: %s" % sizeof_bps_fmt(input_diff/time_diff, unit="pps")
                                            outputRate = "Output: %s" % sizeof_bps_fmt(output_diff/time_diff, unit="pps")
                                    except:
                                        pass

                                    a_service["plugin_output"] = inputRate + "\n" + outputRate
                                if services_data[a_service["service_description"]]["snmp_subtype"] == "e":
                                    inputRate = "Input: Err "
                                    outputRate = "Output: Err "
                                    try:
                                        time_diff = services_data[a_service["service_description"]]["high_timestamp"]["timestamp"]-services_data[a_service["service_description"]]["low_timestamp"]["timestamp"]
                                        input_diff = services_data[a_service["service_description"]]["high_timestamp"]["ifInErrors"]-services_data[a_service["service_description"]]["low_timestamp"]["ifInErrors"]
                                        output_diff = services_data[a_service["service_description"]]["high_timestamp"]["ifOutErrors"]-services_data[a_service["service_description"]]["low_timestamp"]["ifOutErrors"]

                                        if time_diff > 0:
                                            # diff / time * 8 to get bps.  These are octect counters we are reading so they read bytes.
                                            inputRate = "Input: %s" % (str(input_diff/time_diff) + " errors per second")
                                            outputRate = "Output: %s" % (str(output_diff/time_diff) + " errors per second")
                                    except:
                                        pass

                                    a_service["plugin_output"] = inputRate + "\n" + outputRate

                return jsonify(data=data)
            else:
                return jsonify(error=True)

class ManageHostServiceStatusHostsView(MethodView):
    def post(self, jwt):
        data = []
        nagios_user = os.getenv(
            'NAGIOS_USERNAME',
            'nagiosadmin'
        )
        nagios_password = os.getenv(
            'NAGIOS_PASSWORD',
            'nagios'
        )
        auth = HTTPBasicAuth(nagios_user, nagios_password)
        count = 10

        statusData = get_nagios_status()
        post_data = request.get_json()
        hostids = post_data.get('hosts')

        if hostids is not None:
            for hostid in hostids:
                host_obj = Host.get_by_id(hostid)
                if host_obj is None:
                    continue
                host = {
                    "id": host_obj.id,
                    "host_name": host_obj.host_name,
                    "alias": host_obj.alias,
                    "display_name": host_obj.display_name,
                    "address": host_obj.address,
                    "importance": host_obj.importance,
                    "check_command": host_obj.check_command,
                    "max_check_attempts": host_obj.max_check_attempts,
                    "check_interval": host_obj.check_interval,
                    "retry_interval": host_obj.retry_interval,
                    "active_checks_enabled": host_obj.active_checks_enabled,
                    "passive_checks_enabled": host_obj.passive_checks_enabled,
                    "check_period": host_obj.check_period,
                    "obsess_over_host": host_obj.obsess_over_host,
                    "check_freshness": host_obj.check_freshness,
                    "freshness_threshold": host_obj.freshness_threshold,
                    "event_handler": host_obj.event_handler,
                    "event_handler_enabled": host_obj.event_handler_enabled,
                    "low_flap_threshold": host_obj.low_flap_threshold,
                    "high_flap_threshold": host_obj.high_flap_threshold,
                    "flap_detection_enabled": host_obj.flap_detection_enabled,
                    "flap_detection_options": host_obj.flap_detection_options,
                    "process_perf_data": host_obj.process_perf_data,
                    "retain_status_information": host_obj.retain_status_information,
                    "retain_nonstatus_information": host_obj.retain_nonstatus_information,
                    "contacts": host_obj.contacts,
                    "contact_groups": host_obj.contact_groups,
                    "notification_interval": host_obj.notification_interval,
                    "first_notification_delay": host_obj.first_notification_delay,
                    "notification_period": host_obj.notification_period,
                    "notification_options": host_obj.notification_options,
                    "notifications_enabled": host_obj.notifications_enabled,
                    "use": host_obj.use,
                    "hostgroups": host_obj.hostgroups,
                    "street_address": host_obj.street_address,
                    "sms": host_obj.sms
                }
                if statusData is not None and 'hosts' in statusData.keys() and len(statusData['hosts']) > 0:
                    if statusData['hosts'][host['host_name'].strip()]['current_state'] == "0":
                        host["host_status"] = "UP"
                    elif statusData['hosts'][host['host_name'].strip()]['current_state'] == "1":
                        host["host_status"] = "DOWN"
                    elif statusData['hosts'][host['host_name'].strip()]['current_state'] == "2":
                        host["host_status"] = "DOWN"
                    else:
                        host["host_status"] = "DOWN"

                    host["plugin_output"] = statusData['hosts'][host['host_name'].strip()]["plugin_output"]
                    host["last_state_change"] = statusData['hosts'][host['host_name'].strip()]["last_state_change"]
                    host["last_check"] = statusData['hosts'][host['host_name'].strip()]["last_check"]
                    host["services"] = statusData['hosts'][host['host_name'].strip()]['services']

                    for idx in range(len(host["services"])):
                        if host['services'][idx]['current_state'] == "0":
                            host['services'][idx]['current_state_str'] = "OK"
                        elif host['services'][idx]['current_state'] == "1":
                            host['services'][idx]['current_state_str'] = "WARNING"
                        elif host['services'][idx]['current_state'] == "2":
                            host['services'][idx]['current_state_str']= "CRITICAL"
                        elif host['services'][idx]['current_state'] == "3":
                            host['services'][idx]['current_state_str']= "UNKNOWN"
                        else:
                            host['services'][idx]['current_state_str'] = "PENDING"
                else:
                    host["host_status"] = "UNKNOWN"

                data.append(host)

        return jsonify(data=data)

#Get DOWN status of hosts and services
class ManageHostDownStatusView(MethodView):
    def get(self, jwt):
        data = []
        host_data = []
        service_data = []
        nagios_user = os.getenv(
            'NAGIOS_USERNAME',
            'nagiosadmin'
        )
        nagios_password = os.getenv(
            'NAGIOS_PASSWORD',
            'nagios'
        )
        auth = HTTPBasicAuth(nagios_user, nagios_password)

        try:
            # Get Down host lists
            host_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=hostlist&hoststatus=down'
            host_response = requests.get(host_url, auth=auth)
            for host in host_response.json()["data"]["hostlist"].keys():
                h_obj = {
                    "hname": "",
                    "hstatus": ""
                }
                h_obj["hname"] = host
                h_obj["hstatus"] = "Down"
                host_data.append(h_obj)

            # Get Unreachable host lists
            host_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=hostlist&hoststatus=unreachable'
            host_response = requests.get(host_url, auth=auth)
            for host in host_response.json()["data"]["hostlist"].keys():
                h_obj = {
                    "hname": "",
                    "hstatus": ""
                }
                h_obj["hname"] = host
                h_obj["hstatus"] = "Unreachable"
                host_data.append(h_obj)

            data.append({"hosts": host_data})

            # Get Critical service lists
            service_url = 'http://nagios/nagios/cgi-bin/statusjson.cgi?query=servicelist&servicestatus=critical'
            service_response = requests.get(service_url, auth=auth)
            for service in service_response.json()["data"]["servicelist"].keys():
                s_obj = {
                    "hname": "",
                    "sname": "",
                    "status": ""
                }
                s_obj["hname"] = service
                for sub in service_response.json()["data"]["servicelist"][service].keys():
                    s_obj["sname"] = sub
                    break
                s_obj["status"] = "Critical"
                service_data.append(s_obj)

            data.append({"services": service_data})
        except:
            data = []

        return jsonify(data=data)


#Get Up/DOWN status of Nagios
class ManageNagiosStatusView(MethodView):
    def get(self, jwt):
        data = []
        status_data = get_nagios_statusdat_exist()
        if status_data["status"] == 'true':
            data.append({"status": "up"})
        else:
            data.append({"status": "down"})
        return jsonify(data=data)



manage_host_status_data_view = token_required(ManageHostStatusDataView.as_view('manage_host_status_data_view'))
manage_host_service_status_total_view = token_required(ManageHostServiceStatusTotalView.as_view('manage_host_service_status_total_view'))
manage_host_service_status_row_view = token_required(ManageHostServiceStatusRowView.as_view('manage_host_service_status_row_view'))
manage_host_service_status_hosts_view = token_required(ManageHostServiceStatusHostsView.as_view('manage_host_service_status_hosts_view'))
manage_service_status_data_view = token_required(ManageServiceStatusDataView.as_view('manage_service_status_data_view'))
manage_host_service_down_view = token_required(ManageHostDownStatusView.as_view('manage_host_service_down_view'))
manage_nagios_status_view = token_required(ManageNagiosStatusView.as_view('manage_nagios_status_view'))


status_data_app.add_url_rule(
    '/service_status_data/',
    defaults={'service_id': None},
    view_func=manage_service_status_data_view,
    methods=['GET']
)

status_data_app.add_url_rule(
    '/service_status_data/<int:service_id>/',
    view_func=manage_service_status_data_view,
    methods=['GET']
)

status_data_app.add_url_rule(
    '/host_status_data/',
    defaults={'host_id': None, 'host_name': None},
    view_func=manage_host_status_data_view,
    methods=['GET']
)

status_data_app.add_url_rule(
    '/host_status_data/<int:host_id>/',
    view_func=manage_host_status_data_view,
    methods=['GET']
)

status_data_app.add_url_rule(
    '/host_status_data/<string:host_name>/',
    view_func=manage_host_status_data_view,
    methods=['GET']
)

status_data_app.add_url_rule(
    '/host_service_status_total/',
    defaults={'page_id': None, 'status_id': None},
    view_func=manage_host_service_status_total_view,
    methods=['POST']
)

status_data_app.add_url_rule(
    '/host_service_status_total/page/<int:page_id>/<int:status_id>',
    view_func=manage_host_service_status_total_view,
    methods=['POST']
)

status_data_app.add_url_rule(
    '/host_service_status_total/row_num/<int:row_num>/<int:status_id>',
    view_func=manage_host_service_status_row_view,
    methods=['POST']
)

status_data_app.add_url_rule(
    '/host_service_status_total/hosts/',
    view_func=manage_host_service_status_hosts_view,
    methods=['POST']
)

status_data_app.add_url_rule(
    '/host_service_down/',
    view_func=manage_host_service_down_view,
    methods=['GET']
)

status_data_app.add_url_rule(
    '/nagios_status/',
    view_func=manage_nagios_status_view,
    methods=['GET']
)
