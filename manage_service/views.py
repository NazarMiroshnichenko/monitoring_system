from flask import Blueprint, request, jsonify
from flask.views import MethodView
from app.models import Host, Service, Contact, ContactGroup, ServiceGroup, Command
from app.models import ContactService, HostService, Service2Group, ContactgroupService, ServiceTemplate, \
    Service2Template
from app.auth.helper import token_required
from datetime import date, datetime
from app.nagios_functions.helper import restartNagios
from app.nagios_functions.helper import writeNagiosServicesConfigFile
from app.nagios_functions.helper import deleteNagiosServicesConfigFile
from app.nagios_functions.helper import writeNagiosServiceGroupsConfigFile
from app.nagios_functions.helper import syncNagiosAllConfigWithDb
from app import db
import subprocess
import re

manage_service_app = Blueprint('manage_service', __name__)

COMMON_SNTP_TRAFFIC = "snmp_traffic"
COMMON_SNTP_CPULOAD = "snmp_cpuload"
COMMON_SNTP_MEMORY = "snmp_memory"


class ManageServiceView(MethodView):
    def get(self, jwt, service_id):
        data = []

        # If no service_id is passed in get all services.
        if service_id is None:
            services = Service.get_all()
        else:
            if Service.get_by_id(service_id) is not None:
                services = [Service.get_by_id(service_id)]
            else:
                services = None

        # Loop over results and get json form of service to return.
        if services is not None:
            for service in services:
                data.append(service.serialize())
                pass
            return jsonify(data=data)
        else:
            return jsonify(error=True, msg="Service does not exist.")

    def post(self, jwt):
        OID_CPU_LOAD_1 = "laLoad.1"
        OID_CPU_LOAD_5 = "laLoad.2"
        OID_CPU_LOAD_15 = "laLoad.3"

        OID_PHYSICAL_MEM = "hrStorageSize.1"
        OID_VIRTUAL_MEM = "hrStorageSize.3"
        OID_SWAP_MEM = "hrStorageSize.10"

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                host_names = post_data.get('host_name')
                service_description = post_data.get('service_description')
                display_name = post_data.get('display_name')
                check_command_pre = post_data.get('check_command_pre')
                check_command_param = post_data.get('check_command_param')
                snmp_type = post_data.get('snmp_type', '')
                snmp_option = post_data.get('snmp_option')
                snmp_check = post_data.get('snmp_check')
                snmp_ifname = post_data.get('snmp_ifname')
                max_check_attempts = post_data.get('max_check_attempts')
                check_interval = post_data.get('check_interval')
                retry_interval = post_data.get('retry_interval')
                contacts = post_data.get('contacts')
                contact_groups = post_data.get('contact_groups')
                servicegroups = post_data.get('servicegroups')
                servicetemplates = post_data.get('use')
                warning_limit = post_data.get('warning_limit')
                critical_limit = post_data.get('critical_limit')

                host_name_str = ''
                service_group_str = ''
                contacts_str = ''
                contact_groups_str = ''
                servicetemplates_str = ''
                snmp_option_str = ''
                snmp_check_str = ''
                command_list = []

                if host_names is None:
                    return jsonify(error=True, msg="Missing host_name required field.")
                if service_description is None:
                    return jsonify(error=True, msg="Missing service_description required field.")
                if display_name is None:
                    display_name = service_description
                if check_command_pre is None:
                    return jsonify(error=True, msg="Missing check_command required field.")
                if max_check_attempts is None or not str(max_check_attempts).isdigit():
                    max_check_attempts = 5
                if check_interval is None or not str(check_interval).isdigit():
                    check_interval = 60
                if retry_interval is None or not str(retry_interval).isdigit():
                    retry_interval = 1
                if warning_limit is None or warning_limit == '':
                    warning_limit = 100
                if critical_limit is None or critical_limit == '':
                    critical_limit = 200

                if host_names is not None and len(host_names) > 0:
                    temp_data_services = Service.get_by_description(service_description)
                    # Check duplicate host for service_description
                    for tds in temp_data_services:
                        for hname in tds.host_name:
                            for name in host_names:
                                if name == hname:
                                    return jsonify(error=True, msg="Service host already exists.")
                    host_name_str = ','.join(host_names)

                if servicegroups is not None and len(servicegroups) > 0:
                    service_group_str = ','.join(servicegroups)
                if contacts is not None and len(contacts) > 0:
                    contacts_str = ','.join(contacts)
                if contact_groups is not None and len(contact_groups) > 0:
                    contact_groups_str = ','.join(contact_groups)

                if snmp_check is not None and len(snmp_check) > 0:
                    snmp_check_str = ','.join(snmp_check)

                if servicetemplates is not None and len(servicetemplates) > 0:
                    servicetemplates_str = ','.join(servicetemplates)

                if check_command_param is not None and len(check_command_param) > 0:
                    check_command_str = check_command_pre + str(check_command_param)
                    command_list.append(check_command_str)
                else:
                    check_command_str = check_command_pre
                    command = Command.get_by_commandname(check_command_pre)
                    if command is not None and command.command_line.find('check_snmp') != -1:
                        # Check existing host's community
                        host = Host.get_by_hostname(host_names)
                        if host is not None and len(host._SNMPCOMMUNITY) == 0:
                            return jsonify(error=True, msg="The community of host not exists.")

                        if snmp_type is not None and check_command_pre:
                            for option in snmp_option:
                                check_command_str = check_command_pre
                                temp = ""
                                if snmp_type == COMMON_SNTP_TRAFFIC:
                                    if snmp_check is not None and len(snmp_check) > 0:
                                        cnt = 0
                                        for check in snmp_check:
                                            cnt += 1
                                            if check == "ifUcastPkts":
                                                temp += "!ifHCInUcastPkts." + str(option) + "!ifHCOutUcastPkts." + str(
                                                    option) + "!" + str(check_interval) + "!" + str(
                                                    warning_limit) + "!" + str(critical_limit)
                                            elif check == "ifMulticastPkts":
                                                temp += "!ifHCInMulticastPkts." + str(
                                                    option) + "!ifHCOutMulticastPkts." + str(option) + "!" + str(
                                                    check_interval) + "!" + str(warning_limit) + "!" + str(
                                                    critical_limit)
                                            elif check == "ifErrors":
                                                temp += "!ifInErrors." + str(option) + "!ifOutErrors." + str(
                                                    option) + "!" + str(check_interval) + "!" + str(
                                                    warning_limit) + "!" + str(critical_limit)
                                        if cnt == 3:
                                            temp = "!ifHCInOctets." + str(option) + "!ifHCOutOctets." + str(
                                                option) + temp
                                    else:
                                        temp = "!ifHCInOctets." + str(option) + "!ifHCOutOctets." + str(
                                            option) + "!" + str(check_interval) + "!" + str(warning_limit) + "!" + str(
                                            critical_limit)
                                    check_command_str += temp
                                elif snmp_type == COMMON_SNTP_CPULOAD:
                                    temp = "!" + OID_CPU_LOAD_1 + "!" + OID_CPU_LOAD_5 + "!" + OID_CPU_LOAD_15
                                    check_command_str += temp
                                elif snmp_type == COMMON_SNTP_MEMORY:
                                    temp = "!" + OID_PHYSICAL_MEM + "!" + OID_VIRTUAL_MEM + "!" + OID_SWAP_MEM
                                    check_command_str += temp

                                command_list.append(check_command_str)
                    else:
                        command_list.append(check_command_str)

                idx = 0
                for one_command in command_list:
                    if len(snmp_option) > idx:
                        snmp_option_str = snmp_option[idx]
                    if len(command_list) > 1 and snmp_ifname:
                        service_name = service_description + "-" + snmp_ifname[idx]
                        display_name = service_name
                    else:
                        service_name = service_description
                    idx += 1

                    # Create first Ping Service
                    newservice = Service(
                        host_name=host_name_str.strip(),
                        hostgroup_name=None,
                        service_description=service_name.strip(),
                        display_name=display_name.strip(),
                        importance=None,
                        servicegroups=service_group_str.strip(),
                        is_volatile=None,
                        check_command=one_command.strip(),
                        check_command_pre=check_command_pre.strip(),
                        check_command_param=check_command_param,
                        snmp_type=snmp_type.strip(),
                        snmp_option=snmp_option_str,
                        snmp_check=snmp_check_str,
                        max_check_attempts=max_check_attempts,
                        check_interval=str(check_interval),
                        retry_interval=retry_interval,
                        active_checks_enabled=True,
                        passive_checks_enabled=False,
                        check_period="24x7",
                        obsess_over_host=None,
                        check_freshness=None,
                        freshness_threshold=None,
                        event_handler=None,
                        event_handler_enabled=None,
                        low_flap_threshold=None,
                        high_flap_threshold=None,
                        flap_detection_enabled=None,
                        flap_detection_options=None,
                        process_perf_data=True,
                        retain_status_information=True,
                        retain_nonstatus_information=True,
                        contacts=contacts_str,
                        contact_groups=contact_groups_str,
                        notification_interval=60,
                        first_notification_delay=5,
                        notification_period="24x7",
                        notification_options="w,c,r",
                        notifications_enabled=True,
                        use=servicetemplates_str,
                        command=None,
                        retry_check_interval=None,
                        normal_check_interval=None,
                        name=None,
                        warning=warning_limit,
                        critical=str(critical_limit),
                    )

                    newservice.check_interval = round(int(check_interval) / 60, 1)
                    service_id = newservice.save()
                    writeNagiosServicesConfigFile(newservice)
                    newservice.check_interval = str(check_interval)

                    # Create all relations
                    if host_names:
                        Service.create_hosts_relations(service_id, host_names)
                    if contacts:
                        Service.create_contacts_relations(service_id, contacts)
                    if contact_groups:
                        Service.create_contactgroups_relations(service_id, contact_groups)
                    if servicegroups:
                        Service.create_servicegroups_relations(service_id, servicegroups)
                    if servicetemplates:
                        Service.create_servicetemplate_relations(service_id, servicetemplates)

                if not restartNagios():
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                return jsonify(data=newservice.serialize())
            except Exception as e:
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
        return jsonify(error=True)

    def put(self, jwt, service_id):
        OID_CPU_LOAD_1 = "laLoad.1"
        OID_CPU_LOAD_5 = "laLoad.2"
        OID_CPU_LOAD_15 = "laLoad.3"

        OID_PHYSICAL_MEM = "hrStorageSize.1"
        OID_VIRTUAL_MEM = "hrStorageSize.3"
        OID_SWAP_MEM = "hrStorageSize.10"

        if service_id is None:
            return jsonify(error=True)

        service = Service.get_by_id(service_id)
        if service is None:
            return jsonify(error=True)

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                host_name = post_data.get('host_name')
                service_description = post_data.get('service_description')
                display_name = post_data.get('display_name')
                check_command_pre = post_data.get('check_command_pre')
                check_command_param = post_data.get('check_command_param')
                snmp_type = post_data.get('snmp_type')
                snmp_option = post_data.get('snmp_option')
                snmp_check = post_data.get('snmp_check')
                max_check_attempts = post_data.get('max_check_attempts')
                check_interval = post_data.get('check_interval')
                retry_interval = post_data.get('retry_interval')
                contacts = post_data.get('contacts')
                contact_groups = post_data.get('contact_groups')
                servicegroups = post_data.get('servicegroups')
                servicetemplates = post_data.get('use')
                warning_limit = post_data.get('warning_limit')
                critical_limit = post_data.get('critical_limit')

                servicegroup_names_to_update = []

                if service.servicegroups:
                    servicegroup_names_to_update = servicegroup_names_to_update + service.servicegroups.split(',')
                if servicegroups:
                    servicegroup_names_to_update = servicegroup_names_to_update + servicegroups

                if host_name:
                    service.host_name = ','.join(host_name)

                if service_description is not None:
                    service.service_description = service_description.strip()

                if check_command_pre is not None:
                    service.check_command_pre = check_command_pre.strip()
                    if service.check_command_param is not None:
                        if snmp_type != COMMON_SNTP_TRAFFIC:
                            service.check_command = check_command_pre + service.check_command_param.strip()
                    else:
                        service.check_command = check_command_pre.strip()

                if check_command_param is not None and len(check_command_param) > 0:
                    service.check_command_param = check_command_param.strip()
                    service.check_command = service.check_command_pre + check_command_param.strip()

                command = Command.get_by_commandname(check_command_pre)
                if command is not None and command.command_line.find('check_snmp') != -1:
                    if snmp_type is not None and len(snmp_type) > 0:
                        temp = ""
                        service.snmp_type = snmp_type.strip()
                        if snmp_type == COMMON_SNTP_TRAFFIC:
                            for option in snmp_option:
                                if snmp_check is not None and len(snmp_check) > 0:
                                    for check in snmp_check:
                                        if check == "ifUcastPkts":
                                            temp += "!ifHCInUcastPkts." + str(option) + "!ifHCOutUcastPkts." + str(
                                                option) + "!" + str(check_interval) + "!" + str(
                                                warning_limit) + "!" + str(critical_limit)
                                        elif check == "ifMulticastPkts":
                                            temp += "!ifHCInMulticastPkts." + str(
                                                option) + "!ifHCOutMulticastPkts." + str(option) + "!" + str(
                                                check_interval) + "!" + str(warning_limit) + "!" + str(critical_limit)
                                        elif check == "ifErrors":
                                            temp += "!ifInErrors." + str(option) + "!ifOutErrors." + str(
                                                option) + "!" + str(check_interval) + "!" + str(
                                                warning_limit) + "!" + str(critical_limit)
                                else:
                                    temp += "!ifHCInOctets." + str(option) + "!ifHCOutOctets." + str(
                                        option) + "!" + str(check_interval) + "!" + str(warning_limit) + "!" + str(
                                        critical_limit)
                                break
                            service.check_command = check_command_pre + temp
                        elif snmp_type == COMMON_SNTP_CPULOAD:
                            temp = "!" + OID_CPU_LOAD_1 + "!" + OID_CPU_LOAD_5 + "!" + OID_CPU_LOAD_15
                            service.check_command = check_command_pre + temp
                        elif snmp_type == COMMON_SNTP_MEMORY:
                            temp = "!" + OID_PHYSICAL_MEM + "!" + OID_VIRTUAL_MEM + "!" + OID_SWAP_MEM
                            service.check_command = check_command_pre + temp

                if snmp_option is not None and len(snmp_option) > 0:
                    snmp_option_str = ','.join("{0}".format(n) for n in snmp_option)
                    service.snmp_option = snmp_option_str

                if snmp_check is not None and len(snmp_check) > 0:
                    snmp_check_str = ','.join(snmp_check)
                    service.snmp_check = snmp_check_str

                if max_check_attempts is not None and str(max_check_attempts).isdigit():
                    service.max_check_attempts = max_check_attempts

                if check_interval is not None and str(check_interval).isdigit():
                    service.check_interval = str(round(int(check_interval) / 60, 1))

                if retry_interval is not None and str(retry_interval).isdigit():
                    service.retry_interval = retry_interval

                if warning_limit is not None and str(warning_limit).isdigit():
                    service.warning = warning_limit

                if critical_limit is not None and str(critical_limit).isdigit():
                    service.critical = str(critical_limit)

                if contacts is not None:
                    service.contacts = ','.join(contacts)

                if contact_groups is not None:
                    service.contact_groups = ','.join(contact_groups)

                if servicegroups is not None:
                    service.servicegroups = ','.join(servicegroups)

                if servicetemplates is not None:
                    service.use = ','.join(servicetemplates)

                writeNagiosServicesConfigFile(service)

                if check_interval is not None and str(check_interval).isdigit():
                    service.check_interval = str(check_interval)

                updated = service.update()

                if host_name:
                    Service.delete_all_hosts_relations(service_id)
                    Service.create_hosts_relations(service_id, host_name)
                if contacts:
                    Service.delete_all_contacts_relations(service_id)
                    Service.create_contacts_relations(service_id, contacts)
                if contact_groups:
                    Service.delete_all_contactgroups_relations(service_id)
                    Service.create_contactgroups_relations(service_id, contact_groups)
                if servicegroups:
                    Service.delete_all_servicegroups_relations(service_id)
                    Service.create_servicegroups_relations(service_id, servicegroups)
                if servicetemplates:
                    Service.delete_all_servicetemplate_relations(service_id)
                    Service.create_servicetemplate_relations(service_id, servicetemplates)

                if not restartNagios():
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                if updated:
                    service = Service.get_by_id(service_id)
                    return jsonify(data=service.serialize())
            except Exception as e:
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
        return jsonify(error=True)

    def delete(self, jwt, service_id):
        if service_id is None:
            return jsonify(error=True)

        service = Service.get_by_id(service_id)
        if service is None:
            return jsonify(error=True)
        else:
            try:
                Service.delete_all_hosts_relations(service_id)
                Service.delete_all_contacts_relations(service_id)
                Service.delete_all_contactgroups_relations(service_id)
                Service.delete_all_servicegroups_relations(service_id)
                Service.delete_all_servicetemplate_relations(service_id)

                service = Service.get_by_id(service_id)
                deleteNagiosServicesConfigFile(service)
                service.delete()

                if not restartNagios():
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                return jsonify(error=False)
            except Exception as e:
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))


class ManageServiceSNMPTrafficView(MethodView):

    def post(self, jwt):
        OID_INTERFACE_COUNT = ".1.3.6.1.2.1.2.2.1.1"
        OID_IFDESCR = "1.3.6.1.2.1.2.2.1.2."
        OID_IFOPERSTATUS = "1.3.6.1.2.1.2.2.1.8."
        OID_IFSPEED = "1.3.6.1.2.1.2.2.1.5."
        OID_IFTYPE = "1.3.6.1.2.1.2.2.1.3."

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                host_name = post_data.get('host_name')
                oid_type = post_data.get('snmp_type')

                data = []
                community_str = ""
                version_str = ""
                ip_str = ""

                if host_name is None:
                    return jsonify(error=True, msg="Missing host_name required field.")

                if oid_type is None:
                    return jsonify(error=True, msg="Missing OID type required field.")

                host = Host.get_by_hostname(host_name)
                if host is None:
                    return jsonify(error=True)
                else:
                    ip_str = host.address
                    # version_str = host._SNMPVERSION
                    version_str = "2c"
                    community_str = host._SNMPCOMMUNITY
                    if version_str is None or len(version_str) == 0:
                        return jsonify(error=True, msg="Missing SNMP version.")
                    if community_str is None or len(community_str) == 0:
                        return jsonify(error=True, msg="Missing SNMP community.")

                    # Get the bandwidth of interface
                    if oid_type == COMMON_SNTP_TRAFFIC:
                        # Request the interface list using snmpwalk tool
                        subout = subprocess.Popen(
                            ['snmpwalk', '-Oqv', '-v', version_str, '-c', community_str, ip_str, OID_INTERFACE_COUNT],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            universal_newlines=True)
                        stdout, stderr = subout.communicate()
                        inf_cnt_str = str(stdout)

                        time_pattern = re.compile("[Tt]imeout")
                        if time_pattern.search(inf_cnt_str):
                            obj = {
                                "index": "0",
                                "ifname": inf_cnt_str,
                                "status": "",
                                "speed": "",
                                "type": ""
                            }
                            data.append(obj)
                            return jsonify(data=data)

                        # Extract interface list from response
                        inf_cnt_list = inf_cnt_str.split('\n')
                        for i in inf_cnt_list:
                            if len(i) <= 0:
                                continue
                            subout = subprocess.Popen(
                                ['snmpget', '-Oqv', '-v', version_str, '-c', community_str, ip_str,
                                 OID_IFDESCR + str(i), OID_IFOPERSTATUS + str(i), OID_IFSPEED + str(i),
                                 OID_IFTYPE + str(i)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                universal_newlines=True)
                            stdout, stderr = subout.communicate()
                            resp_str = str(stdout)
                            respList = resp_str.split('\n')
                            obj_status = ""
                            obj_type = ""

                            if respList[1] == "1":
                                obj_status = "Connected"
                            else:
                                obj_status = "Disconnected"

                            if respList[3] == "6":
                                obj_type = "Ethernet"
                            elif respList[3] == "24":
                                obj_type = "Loopback"
                            else:
                                obj_type = "Ethernet"

                            obj = {
                                "index": str(i),
                                "ifname": respList[0].replace("\"", "") if (len(respList[0]) > 0) else respList[0],
                                "status": obj_status,
                                "speed": str(int(int(respList[2]) / 1000000)) + " MBit/s",
                                "type": obj_type
                            }

                            data.append(obj)

                        return jsonify(data=data)
                    elif oid_type == COMMON_SNTP_CPULOAD:
                        # process snmp cpu
                        return jsonify(data=data)
                    elif oid_type == COMMON_SNTP_MEMORY:
                        # process snmp memory
                        return jsonify(data=data)
                return jsonify(error=False)
            except Exception as e:
                return jsonify(error=True, msg=str(e))
        return jsonify(error=True)


class ManageServiceSNMPTypeView(MethodView):

    def post(self, jwt):
        data = []
        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                host_name = post_data.get('host_name')

                community_str = ""

                if host_name is None:
                    return jsonify(error=True, msg="Missing host_name required field.")

                host = Host.get_by_hostname(host_name)
                if host is None:
                    return jsonify(error=True)
                else:
                    community_str = host._SNMPCOMMUNITY
                    if community_str is None or len(community_str) == 0:
                        return jsonify(error=True, msg="Missing SNMP community.")

                    data.append({
                        "id": "1",
                        "type_name": "snmp_cpuload",
                        "type_alias": "SNMP CPU Load",
                        "type_info": "Monitors the load of a CPU via SNMP"
                    })

                    data.append({
                        "id": "2",
                        "type_name": "snmp_traffic",
                        "type_alias": "SNMP Traffic",
                        "type_info": "Monitors bandwidth and traffic on servers, PCs, switches, etc. using SNMP"
                    })

                    data.append({
                        "id": "3",
                        "type_name": "snmp_memory",
                        "type_alias": "SNMP Memory",
                        "type_info": "Monitors the memory usage via SNMP"
                    })
            except Exception as e:
                return jsonify(error=True, msg=str(e))

        return jsonify(data=data)


class ManageServiceThresholdView(MethodView):

    def post(self, jwt):
        data = []
        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                service_name = post_data.get('service_name')

                warning_str = ""
                critical_str = ""

                if service_name is None:
                    return jsonify(error=True, msg="Missing service name required field.")

                services = Service.get_by_description(service_name)
                if services is None:
                    return jsonify(error=True)
                else:
                    for service in services:
                        warning_str = str(service.warning)
                        critical_str = service.critical
                        break

                    data.append({
                        "warning": warning_str,
                        "critical": critical_str
                    })

            except Exception as e:
                return jsonify(error=True, msg=str(e))

        return jsonify(data=data)


manage_service_view = token_required(ManageServiceView.as_view('manage_service_view'))
manage_service_snmptraffic_view = token_required(
    ManageServiceSNMPTrafficView.as_view('manage_service_snmptraffic_view'))
manager_service_snmptype_view = token_required(ManageServiceSNMPTypeView.as_view('manager_service_snmptype_view'))
manager_service_threshold_view = token_required(ManageServiceThresholdView.as_view('manager_service_threshold_view'))

manage_service_app.add_url_rule(
    '/manage_service/',
    defaults={'service_id': None},
    view_func=manage_service_view,
    methods=['GET']
)

manage_service_app.add_url_rule(
    '/manage_service/<int:service_id>/',
    view_func=manage_service_view,
    methods=['GET', 'PUT', 'DELETE']
)

manage_service_app.add_url_rule(
    '/manage_service/',
    view_func=manage_service_view,
    methods=['POST']
)

manage_service_app.add_url_rule(
    '/manage_service/snmptraffic/',
    view_func=manage_service_snmptraffic_view,
    methods=['POST']
)

manage_service_app.add_url_rule(
    '/manage_service/snmptype/',
    view_func=manager_service_snmptype_view,
    methods=['POST']
)

manage_service_app.add_url_rule(
    '/manage_service/threshold/',
    view_func=manager_service_threshold_view,
    methods=['POST']
)
