from flask import Blueprint, request, abort
from app.auth.helper import token_required
from app.health.helper import response
from sqlalchemy import exc
import os

health = Blueprint('health', __name__)


@health.route('/health', methods=['GET'])
@token_required
def health_information():
    """
    This is used for things to check the health of the app.
    """
    return response(
        'up',
        'Services up! Thanks for checking ',
        200
    )


@health.errorhandler(404)
def item_not_found(e):
    """
    Custom response to 404 errors.
    :param e:
    :return:
    """
    return response('failed', 'Item not found', 404)


@health.errorhandler(400)
def bad_method(e):
    """
    Custom response to 400 errors.
    :param e:
    :return:
    """
    return response('failed', 'Bad request', 400)


@health.errorhandler(503)
def services_down(e):
    """
    Custom response to 503 errors.
    :param e:
    :return:
    """
    return response('down', 'Services down', 503)
