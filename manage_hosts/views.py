from flask import Blueprint, request, jsonify
from flask.views import MethodView
from app.models import Host, Service, HostService, Command, HostContact, Contact, ContactGroup, HostContactGroup
from app.models import Hostgroup, HostgroupHost, HostTemplate, Host2Template
from app.auth.helper import token_required
from datetime import date, datetime
from app.nagios_functions.helper import restartNagios, get_nagios_status
from app.nagios_functions.helper import writeNagiosConfigFile
from app.nagios_functions.helper import deleteNagiosConfigFile
from app.nagios_functions.helper import overwriteAllNagiosConfigFiles
from app.nagios_functions.helper import writeNagiosServicesConfigFile
from app.nagios_functions.helper import deleteNagiosServicesConfigFile
from app.nagios_functions.helper import writeNagiosCommandsConfigFile
from app.nagios_functions.helper import deleteNagiosHostgroupsConfigFile
from app.nagios_functions.helper import writeNagiosHostgroupsConfigFile
from app.nagios_functions.helper import syncNagiosAllConfigWithDb
from math import floor
from app import db

manage_host_app = Blueprint('manage_hosts', __name__)


class ManageHostView(MethodView):
    def get(self, jwt, host_id, page_id, host_name=None):
        data = []

        # If page_id is None do it the slow way.
        if page_id is None:
            # If no host_id is passed in get all hosts.
            if (host_id is None) and (host_name is None):
                # This is slow so lets just return an error
                # hosts = Host.get_all()
                return jsonify(error=True,
                               msg="Getting all hosts is slow. Please use the pagination endpoint at ./manage_host/page/")
            elif host_id:
                if Host.get_by_id(host_id):
                    hosts = [Host.get_by_id(host_id)]
                else:
                    hosts = []
            elif host_name:
                hosts = [Host.get_by_hostname(host_name)]

            # Loop over results and get json form of host to return.
            if len(hosts) > 0:
                for host in hosts:
                    temp_data = host.serialize()
                    temp_data_services = Service.get_all_by_host_name(
                        host.host_name)
                    temp_data["all_services"] = []
                    for tds in temp_data_services:
                        temp_data["all_services"].append(tds.serialize())
                    data.append(temp_data)
                    pass
                return jsonify(data=data)
            else:
                return jsonify(error=True, msg="Host does not exist.")
        else:
            per_page = 10
            totalhosts = Host.get_count()
            total_pages = floor(totalhosts / per_page)
            hosts = Host.get_by_page((page_id * per_page), per_page)

            if hosts is not None:
                for host in hosts:
                    temp_data = host.serialize()
                    temp_data_services = Service.get_all_by_host_name(
                        host.host_name)
                    temp_data["all_services"] = []
                    for tds in temp_data_services:
                        temp_data["all_services"].append(tds.serialize())
                    data.append(temp_data)

            return jsonify({
                "data": data,
                "totalhosts": totalhosts,
                "this_page": page_id,
                "more": (page_id < total_pages)
            })

    def post(self, jwt):
        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()
                host_name = post_data.get('host_name')
                alias = post_data.get('alias')
                address = post_data.get('address')
                contact_groups = post_data.get('contact_groups')
                contacts = post_data.get('contacts')
                sms = post_data.get('sms')
                street_address = post_data.get('street_address', '')
                notes = post_data.get('notes')
                notes_url = post_data.get('notes_url')

                hosttemplates = post_data.get('use')
                host_templates_str = ""
                if hosttemplates is not None:
                    host_templates_str = ','.join(hosttemplates)
                notification_period = post_data.get('notification_period', "24x7")
                notification_options = "d,u,r"
                if post_data.get('notification_options') is not None:
                    notification_options = ','.join(post_data.get('notification_options'))
                notifications_enabled = 1 if post_data.get('notifications_enabled') == True else 0
                check_interval = post_data.get('check_interval', 5)
                retry_interval = post_data.get('retry_interval', 1)
                max_check_attempts = post_data.get('max_check_attempts', 5)
                notification_interval = post_data.get('notification_interval', 120)
                check_command = post_data.get('check_command', "check-host-alive")
                _SNMPVERSION = post_data.get('_SNMPVERSION', "2c")
                _SNMPCOMMUNITY = post_data.get('_SNMPCOMMUNITY', '')

                # Confirm this hostname doesn't already exist first.
                if Host.get_by_hostname(host_name):
                    return jsonify(error=True, msg="Hostname already exists.")

                if host_name is None:
                    return jsonify(error=True, msg="Missing host_name required field.")
                if alias is None:
                    return jsonify(error=True, msg="Missing alias required field.")
                if address is None:
                    return jsonify(error=True, msg="Missing address required field.")

                contacts_str = ''
                if contacts is not None and len(contacts) > 0:
                    contacts_str = ','.join(contacts)

                newhost = Host(
                    host_name=host_name.strip(),
                    alias=alias.strip(),
                    display_name=None,
                    address=address.strip(),
                    importance=None,
                    check_command=check_command.strip(),
                    max_check_attempts=max_check_attempts,
                    check_interval=check_interval,
                    retry_interval=retry_interval,
                    active_checks_enabled=True,
                    passive_checks_enabled=True,
                    check_period="24x7",
                    obsess_over_host=False,
                    check_freshness=True,
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
                    contact_groups="",
                    notification_interval=notification_interval,
                    first_notification_delay=None,
                    notification_period=notification_period.strip(),
                    notification_options=notification_options,
                    notifications_enabled=notifications_enabled,
                    use=host_templates_str,
                    hostgroups="null",
                    street_address=street_address.strip(),
                    sms=sms.strip(),
                    notes=notes.strip(),
                    notes_url=notes_url.strip(),
                    icon_image='',
                    icon_image_alt='',
                    _SNMPVERSION=_SNMPVERSION,
                    _SNMPCOMMUNITY=_SNMPCOMMUNITY
                )
                host_id = newhost.save()

                newservice = Service(
                    host_name=host_name.strip(),
                    hostgroup_name=None,
                    service_description="PING",
                    display_name="PING",
                    importance=None,
                    servicegroups="",
                    is_volatile=None,
                    check_command="PING",
                    check_command_pre=None,
                    check_command_param=None,
                    snmp_type=None,
                    snmp_option=None,
                    snmp_check=None,
                    max_check_attempts=5,
                    check_interval=str(1),
                    retry_interval=1,
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
                    contact_groups="",
                    notification_interval=60,
                    first_notification_delay=5,
                    notification_period="24x7",
                    notification_options="w,c,r",
                    notifications_enabled=True,
                    use="",
                    command=None,
                    retry_check_interval=None,
                    normal_check_interval=None,
                    name=None,
                    warning=None,
                    critical=None,
                )
                service_id = newservice.save()

                # create relations
                if contacts:
                    Host.create_contacts_relations(host_id, contacts)
                    Service.create_contacts_relations(service_id, contacts)
                if contact_groups:
                    Host.create_contactgroups_relations(host_id, contact_groups)
                    Service.create_contactgroups_relations(service_id, contact_groups)
                if hosttemplates:
                    Host.create_hosttemplate_relations(host_id, hosttemplates)

                Service.create_hosts_relations(service_id, [host_name.strip()])

                writeNagiosConfigFile(newhost)
                writeNagiosServicesConfigFile(newservice)

                if not restartNagios():
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                return jsonify(data=newhost.serialize())
            except Exception as e:
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
        return jsonify(error=True)

    def put(self, jwt, host_id, host_name, page_id):

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()
                host = None
                hostname_org = None
                index = post_data.get('index')
                if index is not None:
                    host = Host.get_by_id(index)

                if host is None:
                    return jsonify(error=True)

                hostname_org = host.host_name
                host_name = post_data.get('host_name')
                alias = post_data.get('alias')
                address = post_data.get('address')
                contact_groups = post_data.get('contact_groups')
                contacts = post_data.get('contacts')
                sms = post_data.get('sms')
                street_address = post_data.get('street_address', '')
                notes = post_data.get('notes')
                notes_url = post_data.get('notes_url')

                hosttemplates = post_data.get('use')

                notification_period = "24x7"
                if post_data.get('notification_period') is not None and len(post_data.get('notification_period')) > 0:
                    notification_period = post_data.get('notification_period')
                notification_options = "d,u,r"
                if post_data.get('notification_options') is not None and len(post_data.get('notification_options')) > 0:
                    notification_options = ','.join(
                        post_data.get('notification_options'))
                notifications_enabled = 1
                if post_data.get('notifications_enabled') is not None and len(
                    str(post_data.get('notifications_enabled'))) > 0:
                    notifications_enabled = 1 if post_data.get(
                        'notifications_enabled') == True else 0
                check_interval = 5
                if post_data.get('check_interval') is not None and len(str(post_data.get('check_interval'))) > 0:
                    check_interval = post_data.get('check_interval')
                retry_interval = 1
                if post_data.get('retry_interval') is not None and len(str(post_data.get('retry_interval'))) > 0:
                    retry_interval = post_data.get('retry_interval')
                max_check_attempts = 5
                if post_data.get('max_check_attempts') is not None and len(
                    str(post_data.get('max_check_attempts'))) > 0:
                    max_check_attempts = post_data.get('max_check_attempts')
                notification_interval = 120
                if post_data.get('notification_interval') is not None and len(
                    str(post_data.get('notification_interval'))) > 0:
                    notification_interval = post_data.get(
                        'notification_interval')
                check_command = "check-host-alive"
                if post_data.get('check_command') is not None and len(post_data.get('check_command')) > 0:
                    check_command = post_data.get('check_command')
                _SNMPVERSION = "2c"
                if post_data.get('_SNMPVERSION') is not None and len(post_data.get('_SNMPVERSION')) > 0:
                    _SNMPVERSION = post_data.get('_SNMPVERSION')
                _SNMPCOMMUNITY = ""
                if post_data.get('_SNMPCOMMUNITY') is not None and len(post_data.get('_SNMPCOMMUNITY')) > 0:
                    _SNMPCOMMUNITY = post_data.get('_SNMPCOMMUNITY')

                # Confirm this hostname doesn't already exist first.
                if hostname_org != host_name and Host.get_by_hostname(host_name):
                    return jsonify(error=True, msg="Hostname already exists.")

                if host_name is None:
                    return jsonify(error=True, msg="Missing host_name required field.")
                if alias is None:
                    return jsonify(error=True, msg="Missing alias required field.")
                if address is None:
                    return jsonify(error=True, msg="Missing address required field.")

                host.host_name = host_name.strip()
                host.alias = alias.strip()
                host.address = address.strip()

                if contact_groups is not None:
                    host.contact_groups = ','.join(contact_groups)

                if contacts is not None:
                    host.contacts = ','.join(contacts)

                if sms is not None:
                    host.sms = sms.strip()

                if street_address is not None:
                    host.street_address = street_address.strip()

                if notes is not None:
                    host.notes = notes.strip()

                if notes_url is not None:
                    host.notes_url = notes_url.strip()

                host_templates_str = host.use
                if hosttemplates is not None:
                    host_templates_str = ','.join(hosttemplates)

                host.use = host_templates_str
                host.notification_period = notification_period.strip()
                host.notification_options = notification_options
                host.notifications_enabled = notifications_enabled
                host.check_interval = check_interval
                host.retry_interval = retry_interval
                host.max_check_attempts = max_check_attempts
                host.notification_interval = notification_interval
                host.check_command = check_command.strip()
                host._SNMPVERSION = _SNMPVERSION
                host._SNMPCOMMUNITY = _SNMPCOMMUNITY

                writeNagiosConfigFile(host)
                host_id = host.update()
                # update host_contact table
                Host.delete_all_contact_relations(host_id)
                Host.delete_all_contactgroup_relations(host_id)
                Host.delete_all_host_template_relations(host_id)

                Host.create_contacts_relations(host_id, contacts)
                Host.create_contactgroups_relations(host_id, contact_groups)
                Host.create_hosttemplate_relations(host_id, hosttemplates)

                # re-name of host in services table
                if hostname_org != host_name:
                    services = Service.get_by_hostname_keyword(hostname_org)
                    for service in services:
                        hostnames = service.host_name
                        hostnames = hostnames.replace(hostname_org, host.host_name)
                        service.host_name = hostnames
                        tmp_checkInterval = service.check_interval
                        service.check_interval = round(int(service.check_interval) / 60, 1)
                        writeNagiosServicesConfigFile(service)
                        service.check_interval = tmp_checkInterval
                        service.update()

                    # re-name of host in hostgroups table
                    hostgroups = Hostgroup.get_by_hostname_keyword(hostname_org)
                    for hostgroup in hostgroups:
                        hostnames = hostgroup.members
                        hostnames = hostnames.replace(hostname_org, host.host_name)
                        hostgroup.members = hostnames
                        hostgroup.update()
                        writeNagiosHostgroupsConfigFile(hostgroup)

                if not restartNagios():
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                if host_id:
                    host = Host.get_by_id(host_id)
                    return jsonify(data=host.serialize())
            except Exception as e:
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
        return jsonify(error=True)

    def delete(self, jwt, host_name, host_id, page_id):
        # if host_name is None:
        #     return jsonify(error=True)

        if host_id is not None:
            host = Host.get_by_id(host_id)
        elif host_name is not None:
            host = Host.get_by_hostname(host_name)
        else:
            return jsonify(error=True)

        if host is None:
            return jsonify(error=True)
        else:
            try:
                host_id = host.id
                relations = HostService.query.filter_by(host_id=host_id).all()
                relation_service_ids = []
                if relations is not None:
                    for relation in relations:
                        relation_service_ids.append(relation.service_id)

                relationgroups = HostgroupHost.query.filter_by(
                    host_id=host_id).all()
                relation_hostgroup_ids = []
                if relationgroups is not None:
                    for relationgroup in relationgroups:
                        relation_hostgroup_ids.append(
                            relationgroup.hostgroup_id)

                # delete all relations

                Host.delete_all_host_service_relations(host_id)
                Host.delete_all_contact_relations(host_id)
                Host.delete_all_contactgroup_relations(host_id)
                Host.delete_all_host_template_relations(host_id)
                Host.delete_all_hostgroup_host_relations(host_id)

                host = Host.get_by_id(host_id)
                deleteNagiosConfigFile(host)
                host.delete()

                for relation in relation_service_ids:
                    service = Service.get_by_id(relation)
                    if not service:
                        continue
                    hosts = HostService.get_all_by_sevice(service.id)
                    if hosts:
                        host_ids = [h.id for h in hosts]
                        host_names_str = ','.join(host_ids)
                        service.host_name = host_names_str
                        tmp_check_interval = service.check_interval
                        service.check_interval = round(int(service.check_interval) / 60, 1)
                        writeNagiosServicesConfigFile(service)
                        service.check_interval = tmp_check_interval
                        service.update()
                    else:
                        deleteNagiosServicesConfigFile(service)
                        service.delete()

                for relation in relation_hostgroup_ids:
                    host_group = Hostgroup.get_by_id(relation)
                    if not host_group:
                        continue
                    host_group_hosts = HostgroupHost.get_all_by_hostgroup(host_group.id)
                    if host_group_hosts:
                        host_ids = [h.id for h in host_group_hosts]
                        host_names_str = ','.join(host_ids)
                        host_group.members = host_names_str
                        writeNagiosHostgroupsConfigFile(host_group)
                        host_group.update()
                    else:
                        deleteNagiosHostgroupsConfigFile(host_group)
                        host_group.delete()

                if not restartNagios():
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                return jsonify(error=False)
            except Exception as e:
                syncNagiosAllConfigWithDb()
                print(e.__dict__)
                return jsonify(error=True, msg=str(e))


class ManageHostSearchView(MethodView):
    def get(self, jwt, keyword=None):
        # If no service_id is passed in get all services.
        if keyword is None:
            return jsonify(error=True, msg="Invalid keyword")
        if keyword == "undefined":
            keyword = ""
        data = []
        hosts = Host.get_by_hostname_keyword(keyword, 100)

        if hosts is not None:
            for host in hosts:
                data.append(host.serialize())
                pass
        return jsonify(data=data)


class ManageHostAllView(MethodView):
    def get(self, jwt):
        host_data = []
        hosts = Host.get_all()
        status_data = get_nagios_status()
        for host in hosts:
            status_data_hosts = status_data['hosts']
            host_status = ""
            host_name = host.host_name
            if status_data is not None and 'hosts' in status_data.keys() and len(status_data_hosts) > 0:
                h_name = host_name.strip()
                if h_name in status_data['hosts']:
                    current_state = status_data['hosts'][h_name]['current_state']
                    if current_state == "0":
                        host_status = "UP"
                    elif current_state == "1":
                        host_status = "DOWN"
                    elif current_state == "2":
                        host_status = "DOWN"
                    else:
                        host_status = "DOWN"
                else:
                    host_status = "DOWN"

            host_data.append({
                'id': host.id,
                'ip_address': host.address,
                'street_address': host.street_address,
                'host_name': host_name,
                'host_status': host_status,
            })

        return jsonify({
            "data": host_data,
        })


manage_host_view = token_required(ManageHostView.as_view('manage_host_view'))
manage_host_all_view = token_required(ManageHostAllView.as_view('manage_host_all_view'))
manage_host_search_view = token_required(
    ManageHostSearchView.as_view('manage_host_search_view'))

manage_host_app.add_url_rule(
    '/manage_host/',
    defaults={'host_id': None, 'page_id': None},
    view_func=manage_host_view,
    methods=['GET']
)

manage_host_app.add_url_rule(
    '/manage_host/page/<int:page_id>/',
    defaults={'host_id': None, 'page_id': 0},
    view_func=manage_host_view,
    methods=['GET']
)

manage_host_app.add_url_rule(
    '/manage_host/search/<string:keyword>/',
    view_func=manage_host_search_view,
    methods=['GET']
)

manage_host_app.add_url_rule(
    '/manage_host/<int:host_id>/',
    defaults={'page_id': None, 'host_name': None},
    view_func=manage_host_view,
    methods=['GET', 'PUT', 'DELETE']
)

manage_host_app.add_url_rule(
    '/manage_host/<string:host_name>/',
    defaults={'host_id': None, 'page_id': None},
    view_func=manage_host_view,
    methods=['GET', 'PUT', 'DELETE']
)

manage_host_app.add_url_rule(
    '/manage_host/',
    view_func=manage_host_view,
    methods=['POST']
)

manage_host_app.add_url_rule(
    '/manage_host_all/',
    view_func=manage_host_all_view,
    methods=['GET']
)
