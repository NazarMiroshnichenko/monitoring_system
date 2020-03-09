from flask import Blueprint, request, jsonify
from flask.views import MethodView
from app.models import Contact, Service, ContactGroup, Contact2Group, ContactService
from app.models import ContactTemplate, Contact2Template
from app.auth.helper import token_required
from datetime import date, datetime
from app.nagios_functions.helper import restartNagios
from app.nagios_functions.helper import writeNagiosConfigFile
from app.nagios_functions.helper import writeNagiosContactsConfigFile
from app.nagios_functions.helper import deleteNagiosContactsConfigFile
from app.nagios_functions.helper import writeNagiosContactGroupsConfigFile
from app.nagios_functions.helper import writeNagiosServicesConfigFile
from app.nagios_functions.helper import syncNagiosAllConfigWithDb
from app import db


manage_contact_app = Blueprint('manage_contact', __name__)


class ManageContactView(MethodView):
    
    def get(self, jwt, contact_id):
        data = []

        #If no contact_id is passed in get all contacts.
        if contact_id is None:
            contacts = Contact.get_all()
        else:
            contacts = [Contact.get_by_id(contact_id)]

        #Loop over results and get json form of contact to return.
        if contacts is not None:
            for contact in contacts:
                data.append(contact.serialize())
                pass
            return jsonify(data=data)
        else:
            return jsonify(data=[])

    def post(self, jwt):
        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                contact_name = post_data.get('contact_name')
                alias = post_data.get('alias')
                email = post_data.get('email')
                text_number = int(post_data.get('_text_number')) if post_data.get('_text_number') else None
                contactgroups = post_data.get('contactgroups')
                contacttemplates = post_data.get('use')
                host_notifications_enabled = 1 if post_data.get('host_notifications_enabled') == True else 0
                host_notification_period = post_data.get('host_notification_period')
                host_notification_options = ','.join(post_data.get('host_notification_options'))
                host_notification_commands = 'notify-host-by-email'
                if len(post_data.get('host_notification_commands')) > 0:
                    host_notification_commands = ','.join(post_data.get('host_notification_commands'))
                service_notifications_enabled = 1 if post_data.get('service_notifications_enabled') == True else 0
                service_notification_period = post_data.get('service_notification_period')
                service_notification_commands = 'notify-service-by-email'
                if len(post_data.get('service_notification_commands')) > 0:
                    service_notification_commands = ','.join(post_data.get('service_notification_commands'))
                # service_notification_options = ','.join(post_data.get('service_notification_options'))
                service_notification_options = 1
                contactgroups_str = ''
                contacttemplates_str = ''

                #Confirm this contact_name doesn't already exist first.
                if Contact.get_by_contactname(contact_name):
                    return jsonify(error=True, msg="Contact name already exists.")

                if contact_name is None:
                    return jsonify(error=True, msg="Missing contact_name required field.")

                if contactgroups is not None and len(contactgroups) > 0:
                    contactgroups_str = ','.join(contactgroups)

                if contacttemplates is not None and len(contacttemplates) > 0:
                    contacttemplates_str = ','.join(contacttemplates)

                newcontact = Contact(
                    contact_name=contact_name,
                     alias=alias,
                     contactgroups=contactgroups_str,
                     minimum_importance=1,
                     host_notifications_enabled=host_notifications_enabled,
                     service_notifications_enabled=service_notifications_enabled,
                     host_notification_period=host_notification_period,
                     service_notification_period=service_notification_period,
                     host_notification_options=host_notification_options,
                     service_notification_options=service_notification_options,
                     host_notification_commands=host_notification_commands,
                     service_notification_commands=service_notification_commands,
                     email=email,
                     pager="",
                     addressx="",
                     can_submit_commands=1,
                     retain_status_information=1,
                     retain_nonstatus_information=1,
                     use=contacttemplates_str,
                     text_number=text_number
                )
                db.session.add(newcontact)
                db.session.flush()
                writeNagiosContactsConfigFile(newcontact)

                for contactgroup_name in contactgroups:

                    contactgroup = ContactGroup.get_by_contactgroupname(contactgroup_name)
                    if contactgroup is None:
                        continue

                    # insert contact_contactgroup table
                    newrelation = Contact2Group(
                        contact_id = newcontact.id,
                        contactgroup_id = contactgroup.id
                    )
                    db.session.add(newrelation)
                    db.session.flush()

                    # update members field of contactgroups table
                    contact_names_str = ""
                    connection = db.session.connection()
                    result = connection.execute(
                        "SELECT GROUP_CONCAT(B.contact_name) contact_names FROM contact_contactgroup A" +
                        " LEFT JOIN contacts B ON A.contact_id=B.id" +
                        " WHERE A.contactgroup_id = '%s'" +
                        " GROUP BY A.contactgroup_id"
                        , (contactgroup.id))
                    for row in result:
                        contact_names_str = row['contact_names']
                        contactgroup.members = contact_names_str
                        writeNagiosContactGroupsConfigFile(contactgroup)
                        break

                for contacttemplate_name in contacttemplates:
                    contacttemplate = ContactTemplate.get_by_contacttemplatename(contacttemplate_name)
                    if contacttemplate is None:
                        continue

                    # insert contact_contacttemplate table
                    newrelation = Contact2Template(
                        contact_id = newcontact.id,
                        contacttemplate_id = contacttemplate.id
                    )
                    db.session.add(newrelation)
                    db.session.flush()

                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                db.session.commit()
                return jsonify(data=newcontact.serialize())
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)

    def put(self, jwt, contact_id):
        if contact_id is None:
            return jsonify(error=True)

        contact = Contact.get_by_id(contact_id)
        if contact is None:
            return jsonify(error=True)

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                contact_name = post_data.get('contact_name')
                alias = post_data.get('alias')
                email = post_data.get('email')
                text_number = int(post_data.get('_text_number')) if post_data.get('_text_number') else None
                contactgroups = post_data.get('contactgroups')
                contacttemplates = post_data.get('use')
                host_notifications_enabled = 1 if post_data.get('host_notifications_enabled') == True else 0
                host_notification_period = post_data.get('host_notification_period')
                host_notification_options = ','.join(post_data.get('host_notification_options'))
                host_notification_commands = 'notify-host-by-email'
                if len(post_data.get('host_notification_commands')) > 0:
                    host_notification_commands = ','.join(post_data.get('host_notification_commands'))
                service_notifications_enabled = 1 if post_data.get('service_notifications_enabled') == True else 0
                service_notification_period = post_data.get('service_notification_period')
                service_notification_commands = 'notify-service-by-email'
                if len(post_data.get('service_notification_commands')) > 0:
                    service_notification_commands = ','.join(post_data.get('service_notification_commands'))
                # service_notification_options = ','.join(post_data.get('service_notification_options'))
                service_notification_options = 1
                contactgroup_names_to_update = []

                if contact.contactgroups:
                    contactgroup_names_to_update = contactgroup_names_to_update + contact.contactgroups.split(',')
                if contactgroups:
                    contactgroup_names_to_update = contactgroup_names_to_update + contactgroups

                if contact_name is not None:
                    contact.contact_name = contact_name

                if alias is not None:
                    contact.alias = alias

                if email is not None:
                    contact.email = email

                if text_number is not None:
                    contact.text_number = text_number

                if contactgroups is not None:
                    contact.contactgroups = ','.join(contactgroups)

                if contacttemplates is not None:
                    contact.use = ','.join(contacttemplates)

                if host_notifications_enabled is not None:
                    contact.host_notifications_enabled = host_notifications_enabled

                if host_notification_options is not None:
                    contact.host_notification_options = host_notification_options

                if host_notification_commands is not None:
                    contact.host_notification_commands = host_notification_commands

                if host_notification_period is not None:
                    contact.host_notification_period = host_notification_period

                if service_notifications_enabled is not None:
                    contact.service_notifications_enabled = service_notifications_enabled

                if service_notification_period is not None:
                    contact.service_notification_period = service_notification_period

                if service_notification_commands is not None:
                    contact.service_notification_commands = service_notification_commands

                if service_notification_options is not None:
                    contact.service_notification_options = service_notification_options

                writeNagiosContactsConfigFile(contact)

                # update contact_contactgroup table
                connection = db.session.connection()
                connection.execute("DELETE FROM contact_contactgroup WHERE contact_id = '%s'", (contact.id))

                for contactgroup_name in contactgroups:
                    contactgroup = ContactGroup.get_by_contactgroupname(contactgroup_name)
                    if contactgroup is None:
                        continue

                    newrelation = Contact2Group(
                        contact_id = contact.id,
                        contactgroup_id = contactgroup.id
                    )
                    db.session.add(newrelation)
                    db.session.flush()

                # update contact_contacttemplate table
                connection = db.session.connection()
                connection.execute("DELETE FROM contact_contacttemplate WHERE contact_id = '%s'", (contact.id))

                for contacttemplate_name in contacttemplates:
                    contacttemplate = ContactTemplate.get_by_contacttemplatename(contacttemplate_name)
                    if contacttemplate is None:
                        continue

                    # insert contact_contacttemplate table
                    newrelation = Contact2Template(
                        contact_id = contact.id,
                        contacttemplate_id = contacttemplate.id
                    )
                    db.session.add(newrelation)
                    db.session.flush()

                # update members field of contactgroups table
                for contactgroup_name in contactgroup_names_to_update:
                    contactgroup = ContactGroup.get_by_contactgroupname(contactgroup_name)
                    if contactgroup is None:
                        continue

                    contact_names_str = ""
                    connection = db.session.connection()
                    result = connection.execute(
                        "SELECT GROUP_CONCAT(B.contact_name) contact_names FROM contact_contactgroup A" +
                        " LEFT JOIN contacts B ON A.contact_id=B.id" +
                        " WHERE A.contactgroup_id = '%s'" +
                        " GROUP BY A.contactgroup_id"
                        , (contactgroup.id))
                    if len(result._saved_cursor._result.rows) == 0:
                       contactgroup.members = None
                       writeNagiosContactGroupsConfigFile(contactgroup)
                    else:
                        for row in result:
                            contact_names_str = row['contact_names']
                            contactgroup.members = contact_names_str
                            writeNagiosContactGroupsConfigFile(contactgroup)
                            break

                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                db.session.commit()
                return jsonify(data=contact.serialize())
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)

    def delete(self, jwt, contact_id):
        if contact_id is None:
            return jsonify(error=True)

        contact = Contact.get_by_id(contact_id)
        if contact is None:
            return jsonify(error=True)
        else:
            try:
                deleteNagiosContactsConfigFile(contact)
                db.session.delete(contact)

                # process contact_contactgroup table
                relations = Contact2Group.query.filter_by(contact_id=contact_id).all()
                relation_contactgroup_ids = []
                if relations is not None:
                    for relation in relations:
                        relation_contactgroup_ids.append(relation.contactgroup_id)

                # delete from contact_contactgroup table
                connection = db.session.connection()
                connection.execute("DELETE FROM contact_contactgroup WHERE contact_id = '%s'", (contact_id))

                # delete from contact_contacttemplate table
                connection = db.session.connection()
                connection.execute("DELETE FROM contact_contacttemplate WHERE contact_id = '%s'", (contact_id))

                # update contactgroup table
                for relation_contactgroup_id in relation_contactgroup_ids:
                    contactgroup = ContactGroup.get_by_id(relation_contactgroup_id)
                    if contactgroup is None:
                        continue

                    connection = db.session.connection()
                    result = connection.execute(
                        "SELECT GROUP_CONCAT(B.contact_name) contact_names FROM contact_contactgroup A" +
                        " LEFT JOIN contacts B ON A.contact_id=B.id" +
                        " WHERE A.contactgroup_id = '%s'" +
                        " GROUP BY A.contactgroup_id"
                        , (contactgroup.id))
                    if len(result._saved_cursor._result.rows) == 0:
                        contactgroup.members = None
                        writeNagiosContactGroupsConfigFile(contactgroup)
                    else:
                        for row in result:
                            contact_names_str = row['contact_names']
                            contactgroup.members = contact_names_str
                            writeNagiosContactGroupsConfigFile(contactgroup)
                            break

                # process contact_service table
                csrelations = ContactService.query.filter_by(contact_id=contact_id).all()
                relation_service_ids = []
                if csrelations is not None:
                    for csrelation in csrelations:
                        relation_service_ids.append(csrelation.service_id)

                # delete from contact_service table
                connection = db.session.connection()
                connection.execute("DELETE FROM contact_service WHERE contact_id = '%s'", (contact_id))

                # update service table
                for relation_service_id in relation_service_ids:
                    service = Service.get_by_id(relation_service_id)
                    if service is None:
                        continue

                    connection = db.session.connection()
                    result = connection.execute(
                        "SELECT GROUP_CONCAT(B.contact_name) contact_names FROM contact_service A" +
                        " LEFT JOIN contacts B ON A.contact_id=B.id" +
                        " WHERE A.service_id = '%s'" +
                        " GROUP BY A.service_id"
                        , (service.id))
                    if len(result._saved_cursor._result.rows) == 0:
                        service.contacts = ''
                        tmp_checkInterval = service.check_interval
                        service.check_interval = round(int(service.check_interval) / 60, 1)
                        writeNagiosServicesConfigFile(service)
                        service.check_interval = tmp_checkInterval
                    else:
                        for row in result:
                            contact_names_str = row['contact_names']
                            service.contacts = contact_names_str
                            tmp_checkInterval = service.check_interval
                            service.check_interval = round(int(service.check_interval) / 60, 1)
                            writeNagiosServicesConfigFile(service)
                            service.check_interval = tmp_checkInterval
                            break

                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")
                    
                db.session.commit()
                return jsonify(error=False)
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)


manage_contact_view = token_required(ManageContactView.as_view('manage_contact_view'))


manage_contact_app.add_url_rule(
    '/manage_contact/',
    defaults={'contact_id': None},
    view_func=manage_contact_view,
    methods=['GET']
)


manage_contact_app.add_url_rule(
    '/manage_contact/<int:contact_id>/',
    view_func=manage_contact_view,
    methods=['GET', 'PUT', 'DELETE']
)


manage_contact_app.add_url_rule(
    '/manage_contact/',
    view_func=manage_contact_view,
    methods=['POST']
)
