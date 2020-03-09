from flask import Blueprint
from datetime import datetime
from app.core import es_client

def object_is_safe(data):
    """
    Stupid Helper for now
    Todo: Do this right
    """
    return True
