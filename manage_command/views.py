from flask import Blueprint, request, jsonify
from flask.views import MethodView
from app.models import Command, Service
from app.auth.helper import token_required
from datetime import date, datetime
from app.nagios_functions.helper import restartNagios
from app.nagios_functions.helper import writeNagiosConfigFile
from app.nagios_functions.helper import writeNagiosCommandsConfigFile
from app.nagios_functions.helper import deleteNagiosCommandsConfigFile
from app.nagios_functions.helper import syncNagiosAllConfigWithDb
from app import db
import logging


manage_command_app = Blueprint('manage_command', __name__)


class ManageCommandView(MethodView):
    def get(self, jwt, command_id):
        data = []

        #If no command_id is passed in get all commands.
        if command_id is None:
            commands = Command.get_all()
        else:
            commands = [Command.get_by_id(command_id)]

        #Loop over results and get json form of command to return.
        if commands is not None:
            for command in commands:
                data.append(command.serialize())
                pass
            return jsonify(data=data)
        else:
            return jsonify(data=[])

    def post(self, jwt):
        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                command_name = post_data.get('command_name')
                command_line = post_data.get('command_line')

                # check if input data is empty
                if not command_name:
                    return jsonify(error=True,msg="Command name empty.")
                if not command_line:
                    return jsonify(error=True,msg="Command line empty.")

                #Confirm this contact_name doesn't already exist first.
                if Command.get_by_commandname(command_name):
                    return jsonify(error=True,msg="Command name already exists.")

                newcommand = Command(
                    command_name = command_name,
                    command_line = command_line
                )

                db.session.add(newcommand)

                writeNagiosCommandsConfigFile(newcommand)
                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")

                db.session.commit()
                return jsonify(data=newcommand.serialize())
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)

    def put(self, jwt, command_id):
        if command_id is None:
            return jsonify(error=True)

        command = Command.get_by_id(command_id)
        if command is None:
            return jsonify(error=True)

        if request.is_json and request.get_json(silent=True) is not None:
            try:
                post_data = request.get_json()

                command_line = post_data.get('command_line')

                if not command_line:
                    return jsonify(error=True,msg="Command line empty.")

                command.command_line = command_line

                writeNagiosCommandsConfigFile(command)
                if restartNagios() == False:
                    db.session.rollback()
                    syncNagiosAllConfigWithDb()
                    return jsonify(error=True, msg="Invalid process")
                    
                db.session.commit()
                return jsonify(data=command.serialize())
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)

    def delete(self, jwt, command_id):
        if command_id is None:
            return jsonify(error=True)

        command = Command.get_by_id(command_id)
        if command is None:
            return jsonify(error=True)
        else:
            try:
                # check if services exist related to this command
                services = Service.get_all_by_command_name(command.command_name)
                if services is not None and len(services) > 0:
                    return jsonify(error=True,msg="Failed to delete because there are services that's using the command!")

                deleteNagiosCommandsConfigFile(command)
                db.session.delete(command)
                db.session.commit()
                return jsonify(error=False)
            except Exception as e:
                db.session.rollback()
                syncNagiosAllConfigWithDb()
                return jsonify(error=True, msg=str(e))
            finally:
                db.session.close()
        return jsonify(error=True)


manage_command_view = token_required(ManageCommandView.as_view('manage_command_view'))


manage_command_app.add_url_rule(
    '/manage_command/',
    defaults={'command_id': None},
    view_func=manage_command_view,
    methods=['GET']
)


manage_command_app.add_url_rule(
    '/manage_command/<int:command_id>/',
    view_func=manage_command_view,
    methods=['GET', 'PUT', 'DELETE']
)


manage_command_app.add_url_rule(
    '/manage_command/',
    view_func=manage_command_view,
    methods=['POST']
)
