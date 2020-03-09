# -*- coding: utf-8 -*-


import re
from app.models import (Host, Service, ServiceGroup, Contact, ContactGroup,
                        Command, Hostgroup)


def allowed_file(name, allowed_extension):
    return '.' in name and \
           name.rsplit('.', 1)[1].lower() in allowed_extension


def get_category_model(category):

    if category in ['host', 'hosts']:
        return Host
    elif category in ['service', 'services']:
        return Service
    elif category in ['servicegroup', 'servicegroups']:
        return ServiceGroup
    elif category in ['contact', 'contacts']:
        return Contact
    elif category in ['contactgroup', 'contactgroups']:
        return ContactGroup
    elif category in ['command', 'commands']:
        return Command
    elif category in ['hostgroup', 'hostgroups']:
        return Hostgroup

    return None


def parse_cfg(data):

    try:
        res = re.findall(r'(?<=^define)[^}]*', data, re.MULTILINE)

        final = {}
        for r in res:
            title, rw_data = r.split('{')
            title = title.strip()
            details = re.split(r'\n\s+', rw_data)

            out = []
            for each in details:
                if each.strip():
                    result = re.findall(r'(\w+)\s+(.*)', each)
                    if result:
                        out.append(result[0])

            out = dict(out)
            if title in final:
                final[title].append(out)
            else:
                final[title] = [out]

        return final
    except Exception:
        return
