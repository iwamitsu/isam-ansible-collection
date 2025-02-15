#!/usr/bin/python
# Copyright (c) 2020 IBM
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = '''
---
module: isamcompare
short_description: This module will make calls to connection
description: This module will make calls to connection
author: Ram Sreerangam (@ram-ibm)
options:
    log:
        description:
            - level for log setting
        type: str
        required: False
        default: INFO
        choices:
            - DEBUG
            - INFO
            - ERROR
            - CRITICAL
    action:
        description:
            - name of the ibmsecurity call
        type: str
        required: True
    appliance1:
        description: ip address of the first appliance
        type: str
        required: True
    lmi_port1:
        description: port of the first appliance
        type: int
        required: False
        default: 443
    username1:
        description: username to log into the first appliance
        type: str
        required: False
    password1:
        description: password to log into the first appliance
        type: str
        required: True
    appliance2:
        description: ip address of the 2nd appliance
        type: str
        required: True
    lmi_port2:
        description: port of the 2nd appliance
        type: int
        required: False
        default: 443
    username2:
        description: username to log into the 2nd appliance
        type: str
        required: False
    password2:
        description: password to log into the 2nd appliance
        type: str
        required: True
    isamapi:
        description: parameters to pass to the ibmsecurity call
        type: dict
        required: False
'''

EXAMPLES = '''
- name: Configure access control attributes
  ibm.isam.isam:
    log:       "{{ log_level | default(omit) }}"
    force:     "{{ force | default(omit) }}"
    action: ibmsecurity.isam.aac.attributes.get
    isamapi: "{{ item }}"
  when: item is defined
  with_items: "{{ get_access_control_attributes }}"
  register: ret_obj
'''
import logging
import logging.config
import sys
import importlib
from ansible.module_utils.basic import AnsibleModule
from io import StringIO
import datetime
from ansible.module_utils.six import string_types


try:
    from ibmsecurity.appliance.isamappliance import ISAMAppliance
    from ibmsecurity.appliance.ibmappliance import IBMError
    from ibmsecurity.user.applianceuser import ApplianceUser
    HAS_IBMSECURITY = True
except ImportError:
    HAS_IBMSECURITY = False

logger = logging.getLogger(sys.argv[0])


def main():
    module = AnsibleModule(
        argument_spec=dict(
            log=dict(required=False, default='INFO', choices=['DEBUG', 'INFO', 'ERROR', 'CRITICAL']),
            action=dict(required=True),
            appliance1=dict(required=True),
            lmi_port1=dict(required=False, default=443, type='int'),
            username1=dict(required=False),
            password1=dict(required=True, no_log=True),
            appliance2=dict(required=True),
            lmi_port2=dict(required=False, default=443, type='int'),
            username2=dict(required=False),
            password2=dict(required=True, no_log=True),
            isamapi=dict(required=False, type='dict')
        ),
        supports_check_mode=False
    )

    module.debug('Started isamcompare module')

    # Process all Arguments
    logLevel = module.params['log']
    action = module.params['action']
    appliance1 = module.params['appliance1']
    lmi_port1 = module.params['lmi_port1']
    username1 = module.params['username1']
    password1 = module.params['password1']
    appliance2 = module.params['appliance2']
    lmi_port2 = module.params['lmi_port2']
    username2 = module.params['username2']
    password2 = module.params['password2']

    # Setup logging for format, set log level and redirect to string
    strlog = StringIO()
    DEFAULT_LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '[%(asctime)s] [PID:%(process)d TID:%(thread)d] [%(levelname)s] [%(name)s] [%(funcName)s():%(lineno)s] %(message)s'
            },
        },
        'handlers': {
            'default': {
                'level': logLevel,
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
                'stream': strlog
            },
        },
        'loggers': {
            '': {
                'handlers': ['default'],
                'level': logLevel,
                'propagate': True
            },
            'requests.packages.urllib3.connectionpool': {
                'handlers': ['default'],
                'level': 'ERROR',
                'propagate': True
            }
        }
    }
    logging.config.dictConfig(DEFAULT_LOGGING)

    # Create appliance object to be used for all calls
    if username1 == '' or username1 is None:
        u1 = ApplianceUser(password=password1)
    else:
        u1 = ApplianceUser(username=username1, password=password1)
    isam_server1 = ISAMAppliance(hostname=appliance1, user=u1, lmi_port=lmi_port1)
    if username2 == '' or username2 is None:
        u2 = ApplianceUser(password=password2)
    else:
        u2 = ApplianceUser(username=username2, password=password2)
    isam_server2 = ISAMAppliance(hostname=appliance2, user=u2, lmi_port=lmi_port2)

    # Create options string to pass to action method
    options = 'isamAppliance1=isam_server1, isamAppliance2=isam_server2'
    if isinstance(module.params['isamapi'], dict):
        for key, value in module.params['isamapi'].items():
            if isinstance(value, string_types):
                options = options + ', ' + key + '="' + value + '"'
            else:
                options = options + ', ' + key + '=' + str(value)
    module.debug('Option to be passed to action: ' + options)

    # Dynamically process the module to be compared
    # Simple check to restrict calls to just "isam" ones for safety
    if action.startswith('ibmsecurity.isam.'):
        try:
            mod = importlib.import_module(action)
            method_name = 'compare'  # Standard function to be implemented in every module
            func_ptr = getattr(mod, method_name)  # Convert 'compare' to actual function pointer
            func_call = 'func_ptr(' + options + ')'

            startd = datetime.datetime.now()

            # Execute compare for given action
            ret_obj = eval(func_call)

            endd = datetime.datetime.now()
            delta = endd - startd

            ret_obj['stdout'] = strlog.getvalue()
            ret_obj['stdout_lines'] = strlog.getvalue().split()
            ret_obj['start'] = str(startd)
            ret_obj['end'] = str(endd)
            ret_obj['delta'] = str(delta)
            ret_obj['cmd'] = action + ".compare(" + options + ")"
            srv_facts = {}
            srv_facts['server1'] = isam_server1.facts
            srv_facts['server2'] = isam_server2.facts
            ret_obj['ansible_facts'] = srv_facts

            module.exit_json(**ret_obj)

        except ImportError:
            module.fail_json(name=action, msg='Error> action belongs to a module that is not found!',
                             log=strlog.getvalue())
        except AttributeError:
            module.fail_json(name=action, msg='Error> invalid action was specified, method not found in module!',
                             log=strlog.getvalue())
        except TypeError:
            module.fail_json(name=action,
                             msg='Error> action does not have the right set of arguments or there is a code bug! Options: ' + options,
                             log=strlog.getvalue())
        except IBMError as e:
            module.fail_json(name=action, msg=str(e), log=strlog.getvalue())
    else:
        module.fail_json(name=action, msg='Error> invalid action specified, needs to be isam!',
                         log=strlog.getvalue())


if __name__ == '__main__':
    main()
