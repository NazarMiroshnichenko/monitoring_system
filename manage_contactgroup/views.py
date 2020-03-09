from flask import Blueprint, request, jsonify
from flask.views import MethodView
from app.models import ContactGroup, Contact2Group, Contact, Service, ContactgroupService
from app.auth.helper import token_required
from datetime import date, datetime
from app.nagios_functions.helper import restartNagios
from app.nagios_functions.helper import writeNagiosConfigFile
from app.nagios_functions.helper import writeNagiosContactGroupsConfigFile
from app.nagios_functions.helper import writeNagiosContactsConfigFile
from app.nagios_functions.helper import deleteNagiosContactGroupsConfigFile
from app.nagios_functions.helper import writeNagiosServicesConfigFile
from app.nagios_functions.helper import syncNagiosAllConfigWithDb
from app import db


manage_contactgroup_app = Blueprint('manage_contactgroup', __name__)


class ManageContactGroupView(MethodView):
    def get(self, jwt, contactgroup_id):
        data = []

        #If no contactgroup_id is passed in get all contactgroups.
        if contactgroup_id is None:
            contactgroups = ContactGroup.get_all()
        else:
            contactgroups = [ContactGroup.get_by_id(contactgroup_id)]

        #Loop over results and get json form of contactgroup to return.
        if contactgroups is not None:
            for contactgroup in contactgroups:
                data.append(contactgroup.serialize())
                pass
            return jsonify(data=data)
        else:
            return jsonify(data=[])

    def post(self, jwt):
        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                contactgroup_name = post_data.get('contactgroup_name')
                alias = post_data.get('alias')

                if contactgroup_name is None:
                    return jsonify(error=True, msg="Missing contactgroup_name required field.")

                #Confirm this contactgroup_name doesn't already exist first.
                if ContactGroup.get_by_contactgroupname(contactgroup_name):
                    return jsonify(error=True,msg="Contactgroup name already exists.")

                newcontactgroup = ContactGroup(
                    contactgroup_name = contactgroup_name,
                    alias = alias,
                    members = None,
                    contactgroup_members = None
                )

                db.session.add(newcontactgroup)
                db.session.flush()
                writeNagiosContactGroupsConfigFile(newcontactgroup)
                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                db.session.commit()
                return jsonify(data=newcontactgroup.serialize())
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)

    def put(self, jwt, contactgroup_id):
        if contactgroup_id is None:
            return jsonify(error=True)

        contactgroup = ContactGroup.get_by_id(contactgroup_id)
        if contactgroup is None:
            return jsonify(error=True)

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()
                contactgroup_name = post_data.get('contactgroup_name')
                alias = post_data.get('alias')

                if contactgroup_name is not None:
                    contactgroup.contactgroup_name = contactgroup_name

                if alias is not None:
                    contactgroup.alias = alias

                writeNagiosContactGroupsConfigFile(contactgroup)
                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                db.session.commit()
                return jsonify(data=contactgroup.serialize())
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)

    def delete(self, jwt, contactgroup_id):
        if contactgroup_id is None:
            return jsonify(error=True)

        contactgroup = ContactGroup.get_by_id(contactgroup_id)
        if contactgroup is None:
            return jsonify(error=True)
        else:
            try:
                deleteNagiosContactGroupsConfigFile(contactgroup)
                db.session.delete(contactgroup)

                # process contact_contactgroup table
                relations = Contact2Group.query.filter_by(contactgroup_id=contactgroup_id).all()
                relation_contact_ids = []
                if relations is not None:
                    for relation in relations:
                        relation_contact_ids.append(relation.contact_id)

                # delete from contact_contactgroup table
                connection = db.session.connection()
                connection.execute("DELETE FROM contact_contactgroup WHERE contactgroup_id = '%s'", (contactgroup_id))

                # update contact table
                for relation_contact_id in relation_contact_ids:
                    contact = Contact.get_by_id(relation_contact_id)
                    if contact is None:
                        continue

                    connection = db.session.connection()
                    result = connection.execute(
                        "SELECT GROUP_CONCAT(B.contactgroup_name) contactgroup_names FROM contact_contactgroup A" +
                        " LEFT JOIN contactgroups B ON A.contactgroup_id=B.id" +
                        " WHERE A.contact_id = '%s'" +
                        " GROUP BY A.contact_id"
                        , (contact.id))
                    if len(result._saved_cursor._result.rows) == 0:
                        contact.contactgroups = ''
                        writeNagiosContactsConfigFile(contact)
                    else:
                        for row in result:
                            contactgroup_names_str = row['contactgroup_names']
                            contact.contactgroups = contactgroup_names_str
                            writeNagiosContactsConfigFile(contact)
                            break

                # process contactgroup_service table
                csrelations = ContactgroupService.query.filter_by(contactgroup_id=contactgroup_id).all()
                relation_service_ids = []
                if csrelations is not None:
                    for csrelation in csrelations:
                        relation_service_ids.append(csrelation.service_id)

                # delete from contactgroup_service table
                connection = db.session.connection()
                connection.execute("DELETE FROM contactgroup_service WHERE contactgroup_id = '%s'", (contactgroup_id))

                # update service table
                for relation_service_id in relation_service_ids:
                    service = Service.get_by_id(relation_service_id)
                    if service is None:
                        continue

                    connection = db.session.connection()
                    result = connection.execute(
                        "SELECT GROUP_CONCAT(B.contactgroup_name) contactgroup_names FROM contactgroup_service A" +
                        " LEFT JOIN contactgroups B ON A.contactgroup_id=B.id" +
                        " WHERE A.service_id = '%s'" +
                        " GROUP BY A.service_id"
                        , (service.id))
                    if len(result._saved_cursor._result.rows) == 0:
                        service.contact_groups = ''
                        tmp_checkInterval = service.check_interval
                        service.check_interval = round(int(service.check_interval) / 60, 1)
                        writeNagiosServicesConfigFile(service)
                        service.check_interval = tmp_checkInterval
                    else:
                        for row in result:
                            contactgroup_names_str = row['contactgroup_names']
                            service.contact_groups = contactgroup_names_str
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

class ManageContactGroupSearchView(MethodView):
    def post(self, jwt):
        data = []
        order = None

        if request.is_json and request.get_json(silent=True) is not None:
            post_data = request.get_json()
            order = post_data.get('order')

        contactgroups = ContactGroup.search(order)

        #Loop over results and get json form of contactgroup to return.
        if contactgroups is not None:
            for contactgroup in contactgroups:
                data.append(contactgroup.serialize())
                pass
            return jsonify(data=data)
        else:
            return jsonify(data=[])


manage_contactgroup_view = token_required(ManageContactGroupView.as_view('manage_contactgroup_view'))
manage_contactgroup_search_view = token_required(ManageContactGroupSearchView.as_view('manage_contactgroup_search_view'))


manage_contactgroup_app.add_url_rule(
    '/manage_contactgroup/',
    defaults={'contactgroup_id': None},
    view_func=manage_contactgroup_view,
    methods=['GET']
)


manage_contactgroup_app.add_url_rule(
    '/manage_contactgroup/<int:contactgroup_id>/',
    view_func=manage_contactgroup_view,
    methods=['GET', 'PUT', 'DELETE']
)


manage_contactgroup_app.add_url_rule(
    '/manage_contactgroup/',
    view_func=manage_contactgroup_view,
    methods=['POST']
)


manage_contactgroup_app.add_url_rule(
    '/manage_contactgroup/search',
    view_func=manage_contactgroup_search_view,
    methods=['POST']
)
