#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2016, Peter Sagerson <psagers@getcloak.com>
# (c) 2016, Jiri Tyr <jiri.tyr@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import (absolute_import, division, print_function)

__metaclass__ = type


DOCUMENTATION = """
---
module: ldap_attr
short_description: Add or remove LDAP attribute values.
description:
  - Add or remove LDAP attribute values.
notes:
  - This only deals with attributes on existing entries. To add or remove
    whole entries, see M(community.general.ldap_entry).
  - The default authentication settings will attempt to use a SASL EXTERNAL
    bind over a UNIX domain socket. This works well with the default Ubuntu
    install for example, which includes a cn=peercred,cn=external,cn=auth ACL
    rule allowing root to modify the server configuration. If you need to use
    a simple bind to access your server, pass the credentials in I(bind_dn)
    and I(bind_pw).
  - For I(state=present) and I(state=absent), all value comparisons are
    performed on the server for maximum accuracy. For I(state=exact), values
    have to be compared in Python, which obviously ignores LDAP matching
    rules. This should work out in most cases, but it is theoretically
    possible to see spurious changes when target and actual values are
    semantically identical but lexically distinct.
author:
  - Jiri Tyr (@jtyr)
requirements:
  - python-ldap
options:
  bind_dn:
    type: str
    required: false
    default: null
    description:
      - A DN to bind with. If this is omitted, we'll try a SASL bind with
        the EXTERNAL mechanism. If this is blank, we'll use an anonymous
        bind.
  bind_pw:
    type: str
    required: false
    default: null
    description:
      - The password to use with I(bind_dn).
  dn:
    type: str
    required: true
    description:
      - The DN of the entry to modify.
  name:
    type: str
    required: true
    description:
      - The name of the attribute to modify.
  server_uri:
    type: str
    required: false
    default: ldapi:///
    description:
      - A URI to the LDAP server. The default value lets the underlying
        LDAP client library look for a UNIX domain socket in its default
        location.
  start_tls:
    type: bool
    required: false
    default: 'no'
    description:
      - If true, we'll use the START_TLS LDAP extension.
  state:
    type: str
    required: false
    choices: [present, absent, exact]
    default: present
    description:
      - The state of the attribute values. If C(present), all given
        values will be added if they're missing. If C(absent), all given
        values will be removed if present. If C(exact), the set of values
        will be forced to exactly those provided and no others. If
        I(state=exact) and I(value) is empty, all values for this
        attribute will be removed.
  values:
    type: raw
    required: true
    description:
      - The value(s) to add or remove. This can be a string or a list of
        strings. The complex argument format is required in order to pass
        a list of strings (see examples).
  params:
    type: dict
    description:
        - parameters to be passed
"""

EXAMPLES = """
- name: Configure directory number 1 for example.com
  ldap_attr:
    dn: olcDatabase={1}hdb,cn=config
    name: olcSuffix
    values: dc=example,dc=com
    state: exact
# The complex argument format is required here to pass a list of ACL strings.
- name: Set up the ACL
  ldap_attr:
    dn: olcDatabase={1}hdb,cn=config
    name: olcAccess
    values:
      - >-
        {0}to attrs=userPassword,shadowLastChange
        by self write
        by anonymous auth
        by dn="cn=admin,dc=example,dc=com" write
        by * none'
      - >-
        {1}to dn.base="dc=example,dc=com"
        by dn="cn=admin,dc=example,dc=com" write
        by * read
    state: exact
- name: Declare some indexes
  ldap_attr:
    dn: olcDatabase={1}hdb,cn=config
    name: olcDbIndex
    values: "{{ item }}"
  with_items:
    - objectClass eq
    - uid eq
- name: Set up a root user, which we can use later to bootstrap the directory
  ldap_attr:
    dn: olcDatabase={1}hdb,cn=config
    name: "{{ item.key }}"
    values: "{{ item.value }}"
    state: exact
  with_dict:
    olcRootDN: cn=root,dc=example,dc=com
    olcRootPW: "{SSHA}tabyipcHzhwESzRaGA7oQ/SDoBZQOGND"
- name: Get rid of an unneeded attribute
  ldap_entry:
    dn: uid=jdoe,ou=people,dc=example,dc=com
    name: shadowExpire
    value: ""
    state: exact
    server_uri: ldap://localhost/
    bind_dn: cn=admin,dc=example,dc=com
    bind_pw: password
#
# The same as in the previous example but with the authentication details
# stored in the ldap_auth variable:
#
# ldap_auth:
#   server_uri: ldap://localhost/
#   bind_dn: cn=admin,dc=example,dc=com
#   bind_pw: password
- name: Get rid of an unneeded attribute
  ldap_entry:
    dn: uid=jdoe,ou=people,dc=example,dc=com
    name: shadowExpire
    value: ""
    state: exact
    params: "{{ ldap_auth }}"
"""

RETURN = """
modlist:
  description: list of modified parameters
  returned: success
  type: list
  sample: '[[2, "olcRootDN", ["cn=root,dc=example,dc=com"]]]'
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native, to_bytes, to_text

try:
    import ldap
    import ldap.sasl

    HAS_LDAP = True
except ImportError:
    HAS_LDAP = False


class LdapAttr(object):
    def __init__(self, module):
        # Shortcuts
        self.module = module
        self.bind_dn = self.module.params['bind_dn']
        self.bind_pw = self.module.params['bind_pw']
        self.dn = self.module.params['dn']
        self.name = self.module.params['name']
        self.server_uri = self.module.params['server_uri']
        self.start_tls = self.module.params['start_tls']
        self.state = self.module.params['state']

        # Normalize values
        if isinstance(self.module.params['values'], list):
            self.values = map(str, self.module.params['values'])
        else:
            self.values = [str(self.module.params['values'])]

        # Establish connection
        self.connection = self._connect_to_ldap()

    def add(self):
        values_to_add = filter(self._is_value_absent, self.values)

        if len(values_to_add) > 0:
            modlist = [(ldap.MOD_ADD, self.name, values_to_add)]
        else:
            modlist = []

        return modlist

    def delete(self):
        values_to_delete = filter(self._is_value_present, self.values)

        if len(values_to_delete) > 0:
            modlist = [(ldap.MOD_DELETE, self.name, values_to_delete)]
        else:
            modlist = []

        return modlist

    def exact(self):
        try:
            results = self.connection.search_s(
                self.dn, ldap.SCOPE_BASE, attrlist=[self.name])
        except ldap.LDAPError as e:
            self.module.fail_json(
                msg="Cannot search for attribute %s" % self.name,
                details=str(e))

        current = results[0][1].get(self.name, [])
        modlist = []

        if frozenset(self.values) != frozenset(current):
            if len(current) == 0:
                modlist = [(ldap.MOD_ADD, self.name, self.values)]
            elif len(self.values) == 0:
                modlist = [(ldap.MOD_DELETE, self.name, None)]
            else:
                modlist = [(ldap.MOD_REPLACE, self.name, self.values)]

        return modlist

    def _is_value_present(self, value):
        """ True if the target attribute has the given value. """
        try:
            is_present = bool(
                self.connection.compare_s(self.dn, self.name, value))
        except ldap.NO_SUCH_ATTRIBUTE:
            is_present = False

        return is_present

    def _is_value_absent(self, value):
        """ True if the target attribute doesn't have the given value. """
        return not self._is_value_present(value)

    def _connect_to_ldap(self):
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        connection = ldap.initialize(self.server_uri)

        if self.start_tls:
            try:
                connection.start_tls_s()
            except ldap.LDAPError as e:
                self.module.fail_json(msg="Cannot start TLS.", details=str(e))

        try:
            if self.bind_dn is not None:
                connection.simple_bind_s(self.bind_dn, self.bind_pw)
            else:
                connection.sasl_interactive_bind_s('', ldap.sasl.external())
        except ldap.LDAPError as e:
            self.module.fail_json(
                msg="Cannot bind to the server.", details=str(e))

        return connection


def main():
    module = AnsibleModule(
        argument_spec={
            'bind_dn': dict(default=None),
            'bind_pw': dict(default='', no_log=True),
            'dn': dict(required=True),
            'name': dict(required=True),
            'params': dict(type='dict'),
            'server_uri': dict(default='ldapi:///'),
            'start_tls': dict(default=False, type='bool'),
            'state': dict(
                default='present',
                choices=['present', 'absent', 'exact']),
            'values': dict(required=True, type='raw'),
        },
        supports_check_mode=True,
    )

    if not HAS_LDAP:
        module.fail_json(
            msg="Missing requried 'ldap' module (pip install python-ldap)")

    # Update module parameters with user's parameters if defined
    if 'params' in module.params and isinstance(module.params['params'], dict):
        module.params.update(module.params['params'])
        # Remove the params
        module.params.pop('params', None)

    # Instantiate the LdapAttr object
    ldap = LdapAttr(module)

    state = module.params['state']

    # Perform action
    if state == 'present':
        modlist = ldap.add()
    elif state == 'absent':
        modlist = ldap.delete()
    elif state == 'exact':
        modlist = ldap.exact()

    changed = False

    if len(modlist) > 0:
        changed = True

        if not module.check_mode:
            try:
                ldap.connection.modify_s(ldap.dn, modlist)
            except Exception as e:
                module.fail_json(msg="Attribute action failed.", details=to_native(e))

    module.exit_json(changed=changed, modlist=modlist)


if __name__ == '__main__':
    main()
