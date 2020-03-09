from flask import jsonify, make_response, request, url_for, render_template
from functools import wraps
from app.models import Host
from app.models import Service
from app.models import Contact
from app.models import ContactGroup, ServiceGroup
from app.models import ContactGroup, ServiceGroup, Contact2Group, ContactService, ContactgroupService, HostContact, HostContactGroup, HostService, HostgroupHost, Service2Group, Timeperiod, Timeperioditem
from app.models import Command, Hostgroup, ServiceTemplate
import os
import glob
import requests
import time
import json
from requests.auth import HTTPBasicAuth
import re
import shutil
import json

def sizeof_bps_fmt(num, unit="bps"):
    for rate in ['','k','m','g','t','p','e','z']:
        if abs(num) < 1000.0:
            return "%3.3f%s" % (num, rate+unit)
        num /= 1000.0
    return "%.3f%s%s" % (num, ('y'+unit))

def restartNagios():
    """
    Restart Nagios
    """

    url = "http://nagios/nagios/cgi-bin/custom_start_nagios.php"

    nagios_user = os.getenv(
        'NAGIOS_USERNAME',
        'nagiosadmin'
    )
    nagios_password = os.getenv(
        'NAGIOS_PASSWORD',
        'nagios'
    )
    auth = HTTPBasicAuth(nagios_user, nagios_password)

    response = requests.request("GET", url, auth=auth)

    # Check status of Nagios
    if response.text == "1":
        return True

    return False


def writeNagiosConfigFile(newhost):
    #Todo: Have this actualy write nagios config file out.
    output_from_parsed_template = render_template(
        'generate_single_config.j2', host=newhost)
    with open("/nagiosetc/conf.d/"+str(newhost.id)+".cfg", "w") as f:
        f.write(output_from_parsed_template)
    return True


def overwriteAllNagiosConfigFiles():
    #Todo: Have this actualy write nagios config file out.
    files = glob.glob('/nagiosetc/conf.d/*.cfg')
    for f in files:
        os.remove(f)

    hosts = Host.get_all()

    for host in hosts:
        writeNagiosConfigFile(host)
    return True

def deleteNagiosConfigFile(host):
    try:
        os.remove("/nagiosetc/conf.d/"+str(host.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def get_nagios_status():
    """
    Parse the Nagios status.dat file into a dict to give the ability to report
    on host/service information

    `path` is the absolute path to the Nagios status.dat

    Return dict() if OK
    """
    hosts = {}
    services = {}

    if os.path.isfile('/nagiosvar/status.dat'):
        fh = open('/nagiosvar/status.dat')
        status_raw = fh.read()
        pattern = re.compile('([\w]+)\s+\{([\S\s]*?)\}',re.DOTALL)
        matches = pattern.findall(status_raw)
        for def_type, data in matches:
            lines = [line.strip() for line in data.split("\n")]
            pairs = [line.split("=", 1) for line in lines if line != '']
            data = dict(pairs)

            if def_type == "servicestatus":
                services[data['service_description']] = data
                if 'host_name' in data:
                    hosts[data['host_name']]['services'].append(data)

            if def_type == "hoststatus":
                data['services'] = []
                hosts[data['host_name']] = data
    return {
        'hosts': hosts,
        'services': services,
    }

def get_nagios_statusdat_exist():
    """
    Check existing a status.dat file of Nagios
    Return true or false
    """
    result = 'true'
    if os.path.isfile('/nagiosvar/status.dat'):
        result = 'true'
    else:
        result = 'false'

    return { 'status': result }

def writeNagiosContactsConfigFile(newcontact):
    """
    Add/Edit contact *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_contacts_config.j2', contact=newcontact)
    filename = "/nagiosetc/conf.d/contacts/"+str(newcontact.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    contactgroups = ContactGroup.get_all()
    for group in contactgroups:
        writeNagiosContactGroupsConfigFile(group)
    return True

def deleteNagiosContactsConfigFile(newcontact):
    """
    Delete contact *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/contacts/"+str(newcontact.id) +".cfg")

        contactgroups = ContactGroup.get_all()
        for group in contactgroups:
            writeNagiosContactGroupsConfigFile(group)
        return True
    except OSError:
        pass
    return False

def writeNagiosContactTemplatesConfigFile(newcontacttemplate):
    """
    Add/Edit contact template *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_contacttemplates_config.j2', contacttemplate=newcontacttemplate)
    filename = "/nagiosetc/conf.d/contacttemplates/"+str(newcontacttemplate.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosContactTemplatesConfigFile(newcontacttemplate):
    """
    Delete contact template *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/contacttemplates/"+str(newcontacttemplate.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosContactGroupsConfigFile(newcontactgroup):
    """
    Add/Edit contact groups *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_contactgroups_config.j2', contactgroup=newcontactgroup)
    filename = "/nagiosetc/conf.d/contactgroups/"+str(newcontactgroup.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)
    return True

def deleteNagiosContactGroupsConfigFile(newcontactgroup):
    """
    Delete contact groups *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/contactgroups/"+str(newcontactgroup.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosServicesConfigFile(newservice):
    """
    Add/Edit service *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_services_config.j2', service=newservice)
    filename = "/nagiosetc/conf.d/services/"+str(newservice.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    servicegroups = ServiceGroup.get_all()
    for group in servicegroups:
        writeNagiosServiceGroupsConfigFile(group)

    return True

def deleteNagiosServicesConfigFile(newservice):
    """
    Delete service *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/services/"+str(newservice.id) +".cfg")

        servicegroups = ServiceGroup.get_all()
        for group in servicegroups:
            writeNagiosServiceGroupsConfigFile(group)
        return True
    except OSError:
        pass
    return False

def writeNagiosServiceGroupsConfigFile(newservicegroup):
    """
    Add/Edit service groups *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_servicegroups_config.j2', servicegroup=newservicegroup)
    filename = "/nagiosetc/conf.d/servicegroups/"+str(newservicegroup.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)
    return True

def deleteNagiosServiceGroupsConfigFile(newservicegroup):
    """
    Delete service groups *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/servicegroups/"+str(newservicegroup.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosCommandsConfigFile(newcommand):
    """
    Add/Edit command *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_commands_config.j2', command=newcommand)
    filename = "/nagiosetc/conf.d/commands/"+str(newcommand.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosCommandsConfigFile(newcommand):
    """
    Delete command *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/commands/"+str(newcommand.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosTimeperiodsConfigFile(newtimeperiod, newtimeperiodItems):
    """
    Add/Edit timeperiod *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_timeperiods_config.j2', timeperiod=newtimeperiod, timeperioditems=newtimeperiodItems)
    filename = "/nagiosetc/conf.d/timeperiods/"+str(newtimeperiod.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosTimeperiodsConfigFile(newtimeperiod):
    """
    Delete timeperiod *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/timeperiods/"+str(newtimeperiod.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosHostgroupsConfigFile(newhostgroup):
    """
    Add/Edit host group *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_hostgroups_config.j2', hostgroup=newhostgroup)
    filename = "/nagiosetc/conf.d/hostgroups/"+str(newhostgroup.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosHostgroupsConfigFile(newhostgroup):
    """
    Delete host group *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/hostgroups/"+str(newhostgroup.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def deleteNagiosAllConfigFile():
    """
    Delete all *.cfg files
    """
    try:
        shutil.rmtree("/nagiosetc/conf.d")
        conf_dir = "/nagiosetc/conf.d/"
        os.makedirs(os.path.dirname(conf_dir), exist_ok=True)
        return True
    except OSError:
        pass
    return False

def writeNagiosHostTemplatesConfigFile(newhosttemplate):
    """
    Add/Edit host template *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_hosttemplates_config.j2', hosttemplate=newhosttemplate)
    filename = "/nagiosetc/conf.d/hosttemplates/"+str(newhosttemplate.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosHostTemplatesConfigFile(newhosttemplate):
    """
    Delete host template *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/hosttemplates/"+str(newhosttemplate.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosHostReportsConfigFile(newhostreport):
    """
    Add/Edit host report *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_hostreports_config.j2', hosttemplate=newhostreport)
    filename = "/nagiosetc/conf.d/hostreports/"+str(newhostreport.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosHostReportsConfigFile(newhostreport):
    """
    Delete host report *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/hostreports/"+str(newhostreport.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def writeNagiosServiceTemplatesConfigFile(newservicetemplate):
    """
    Add/Edit service template *.cfg file
    """
    output_from_parsed_template = render_template(
        'generate_servicetemplates_config.j2', servicetemplate=newservicetemplate)
    filename = "/nagiosetc/conf.d/servicetemplates/"+str(newservicetemplate.id)+".cfg"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(output_from_parsed_template)

    return True

def deleteNagiosServiceTemplatesConfigFile(newservicetemplate):
    """
    Delete service template *.cfg file
    """
    try:
        os.remove("/nagiosetc/conf.d/servicetemplates/"+str(newservicetemplate.id) +".cfg")
        return True
    except OSError:
        pass
    return False

def syncNagiosAllConfigWithDb():
    # Delete all nagios config files
    deleteNagiosAllConfigFile()

    # Delete all relation tables
    Contact2Group.delete_all()
    ContactService.delete_all()
    ContactgroupService.delete_all()
    HostContact.delete_all()
    HostContactGroup.delete_all()
    HostService.delete_all()
    HostgroupHost.delete_all()
    Service2Group.delete_all()

    # Sync all settings
    # sync timerperiods table
    timeperiods = Timeperiod.get_all()
    if timeperiods is not None:
        for timeperiod in timeperiods:
            timeperioditems = Timeperioditem.get_by_timeperiodid(timeperiod.id)
            writeNagiosTimeperiodsConfigFile(timeperiod, timeperioditems)

    # sync servicetemplate tables
    servicetemplates = ServiceTemplate.get_all()
    if servicetemplates is not None:
        for servicetemplate in servicetemplates:
            writeNagiosServiceTemplatesConfigFile(servicetemplate)

    # sync commands table
    commands = Command.get_all()
    if commands is not None:
        for command in commands:
            writeNagiosCommandsConfigFile(command)

    # sync servicegroups table
    servicegroups = ServiceGroup.get_all()
    if servicegroups is not None:
        for servicegroup in servicegroups:
            writeNagiosServiceGroupsConfigFile(servicegroup)

    # sync contactgroups table
    contactgroups = ContactGroup.get_all()
    if contactgroups is not None:
        for contactgroup in contactgroups:
            writeNagiosContactGroupsConfigFile(contactgroup)

    # sync contacts table
    contacts = Contact.get_all()
    contact_to_group_relations = []
    if contacts is not None:
        for contact in contacts:
            writeNagiosContactsConfigFile(contact)
            contactgroup_str = contact.contactgroups

            if contactgroup_str is not None and len(contactgroup_str) > 0 and contactgroup_str != "NULL":
                contactgroups = contactgroup_str.split(',')

                for contactgroup_name in contactgroups:
                    contactgroup = ContactGroup.get_by_contactgroupname(contactgroup_name)
                    if contactgroup is None:
                        continue

                    # insert contact_contactgroup table
                    newrelation = Contact2Group(
                        contact_id=contact.id,
                        contactgroup_id=contactgroup.id
                    )
                    contact_to_group_relations.append(newrelation)
        Contact2Group.save_all(contact_to_group_relations)

    # sync hostgroups table
    hostgroups = Hostgroup.get_all()
    hots_to_group_relations = []
    if hostgroups is not None:
        for hostgroup in hostgroups:
            writeNagiosHostgroupsConfigFile(hostgroup)
            hostgroup_str = hostgroup.members

            if hostgroup_str is not None and len(hostgroup_str) > 0 and hostgroup_str != "NULL":
                members = hostgroup_str.split(',')

                for member in members:
                    host = Host.get_by_hostname(member)
                    if host is None:
                        continue

                    # insert hostgroup_host table
                    newrelation = HostgroupHost(
                        hostgroup_id=hostgroup.id,
                        host_id=host.id
                    )
                    hots_to_group_relations.append(newrelation)
        HostgroupHost.save_all(hots_to_group_relations)

    # sync services table
    services = Service.get_all()
    hots_to_service_relations = []
    contact_to_service_relations = []
    contactgroup_to_service_relations = []
    service_to_group_relations = []
    if services is not None:
        for service in services:
            tmp_checkInterval = service.check_interval
            service.check_interval = round(int(service.check_interval) / 60, 1)
            writeNagiosServicesConfigFile(service)
            service.check_interval = tmp_checkInterval

            # Create relation table between hosts and services
            host_str = service.host_name
            if host_str is not None and len(host_str) > 0 and host_str != "NULL":
                hosts = host_str.split(',')

                for hname in hosts:
                    hostname = Host.get_by_hostname(hname)
                    if hostname is None:
                        continue

                    # insert host_service table
                    newhostrelation = HostService(
                        service_id=service.id,
                        host_id=hostname.id
                    )
                    hots_to_service_relations.append(newhostrelation)

            # Create relation table between contacts and services
            contact_str = service.contacts
            if contact_str is not None and len(contact_str) > 0 and contact_str != "NULL":
                contacts = contact_str.split(',')

                for contact in contacts:
                    contactname = Contact.get_by_contactname(contact)
                    if contactname is None:
                        continue

                    # insert contact_service table
                    newcontactrelation = ContactService(
                        service_id=service.id,
                        contact_id=contactname.id
                    )
                    contact_to_service_relations.append(newcontactrelation)

            # Create relation table between contactgroups and services
            contactgroup_str = service.contact_groups
            if contactgroup_str is not None and len(contactgroup_str) > 0 and contactgroup_str != "NULL":
                contact_groups = contactgroup_str.split(',')

                for contactgroup in contact_groups:
                    contactgroupname = ContactGroup.get_by_contactgroupname(contactgroup)
                    if contactgroupname is None:
                        continue

                    # insert contactgroup_service table
                    newgrouprelation = ContactgroupService(
                        service_id=service.id,
                        contactgroup_id=contactgroupname.id
                    )
                    contactgroup_to_service_relations.append(newgrouprelation)

            # Create relation table between services and servicegroups
            servicegroup_str = service.servicegroups
            if servicegroup_str is not None and len(servicegroup_str) > 0 and servicegroup_str != "NULL":
                servicegroups = servicegroup_str.split(',')

                for servicegroup_name in servicegroups:
                    servicegroup = ServiceGroup.get_by_servicegroupname(servicegroup_name)
                    if servicegroup is None:
                        continue

                    # insert service_servicegroup table
                    newservicerelation = Service2Group(
                        service_id=service.id,
                        servicegroup_id=servicegroup.id
                    )
                    service_to_group_relations.append(newservicerelation)
        HostService.save_all(hots_to_service_relations)
        ContactService.save_all(contact_to_service_relations)
        ContactgroupService.save_all(contactgroup_to_service_relations)
        Service2Group.save_all(service_to_group_relations)

    # sync hosts table
    hosts = Host.get_all()
    host_to_contact_relations = []
    host_to_contactgroup_relations = []
    if hosts is not None:
        for host in hosts:
            writeNagiosConfigFile(host)

            contact_str = host.contacts
            if contact_str is not None and len(contact_str) > 0 and contact_str != "NULL":
                contacts = contact_str.split(',')

                for contact_name in contacts:
                    contact = Contact.get_by_contactname(contact_name)
                    if contact is None:
                        continue
                    newhostcontact = HostContact(
                        host_id=host.id,
                        contact_id=contact.id
                    )
                    host_to_contact_relations.append(newhostcontact)

            contactgroup_str = host.contact_groups
            if contactgroup_str is not None and len(contactgroup_str) > 0 and contactgroup_str != "NULL":
                contactgroups = contactgroup_str.split(',')

                for contactgroup_name in contactgroups:
                    contactgroup = ContactGroup.get_by_contactgroupname(contactgroup_name)
                    if contactgroup is None:
                        continue
                    newhostcontactgroup = HostContactGroup(
                        host_id=host.id,
                        contactgroup_id=contactgroup.id
                    )
                    host_to_contactgroup_relations.append(newhostcontactgroup)
        HostContact.save_all(contactgroup_to_service_relations)
        HostContactGroup.save_all(service_to_group_relations)

    restartNagios()
