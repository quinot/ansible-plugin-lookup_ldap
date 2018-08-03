LDAP Lookup Plugin
==================

This role provides a lookup plugin to perform LDAP queries.

Requirements
------------

Tested on Ansible 1.8.

Dependencies
------------

Use of this role requires the Python LDAP client module.

Role Variables
--------------

The plugin allows default parameters to be set using the `ldap_lookup_config`
variable:

```yaml
ldap_lookup_config:
  url: ldap://ldap.example.com
  # URL of the LDAP server
  # Default: None

  base: dc=example,dc=com
  # Base DN for all queries
  # Default: None

  auth: simple
  # Authentication mechanism to use for binding (one of "simple", "gssapi")
  # Default: simple

  binddn: cn=Manager,dc=example,dc=com
  # DN to use for simple binding
  # Default: None (anonymous bind)

  bindpw: Secret!
  # Password to use for simple binding (anon binding if none)
  # Default: None

  scope: subtree
  # Scope of queries (one of "base", "onelevel", or "subtree")
  # Default: subtree

  filter: (objectClass=*)
  # Search filter
  # Default: objectClass=*
  # Search term can be referenced as {{ term }}

  value:
  # List of attributes to be returned
  # Default: None (return all attributes)

  key:
  # Key attribute to be included in returned values
  # Default: None (no key)

  tls:
  # Use STARTTLS after connecting
  # Default: False

  tls_reqcert:
  # Peer certificate verification strategy. One of 'never', 'hard', 'demand',
  # 'allow', or 'try'.  See 'TLS_REQCERT' in the ldap.conf(5) manual page.
  # Default: None (Use OS configuration file or library defaults.)
```

`value` can be:
  - a simple string denoting an attribute name;
  - a dict with a single key (the attribute name), with a value
    that is a list of key=value properties (or an equivalent
    dict);
  - a list of the above.

Valid attribute properties are:
  - `encoding`: `binary` for binary data (e.g. `jpegPhoto`), or any valid
    character set name for text data
  - `skip`: if set True, the attribute is not returned to Ansible
  - `list`: if set True, the attribute is always returned as a list of
    values, even if it has a single value.

Note that, because of the way the 'ldap-python' library works, the `tls_reqcert`
option is set on the whole library, and not per-connection.  Therefore,
specifying this option can have side-effects.

The defaults can be overridden by declaring specific query contexts,
which are dict variables following the same structure. Any parameter
not overridden in a context is inherited from the defaults.

Usage
-----

The `with_ldap` iterator accepts either a single term, or a list of terms,
possibly preceded by one or more dict(s) with possible keys:
  - `context`: a context to use other than the default one;
  - `terms': a list of additional terms to append to the terms list;
  - any valid configuration parameter to be overridden.

Note: the list of terms is not flattened. If you have declared:

```
vars:
  foobar:
    - foo
    - bar
```

and then use the following loop:

```
with_ldap:
  - context: mycontext
  - "{{ foobar }}"
```

then you get a single term which is a list. If you want to query the terms
"foo" and "bar", use instead:

```
with_ldap:
  - context: mycontext
  - terms: "{{ foobar }}"
```


LDAP connection parameters (`url`, `binddn`, `bindpw`) and returned value
parameters (`value`, and `key`) are subject to template expansion once
at the beginning of the iteration.

Search parameters (`base`, `scope`, and `filter`) are expanded for each
term. The following additional variables are defined at that point:
  - `context`: the named context, if any, else the default one;
  - `term`: the search term.

Example Playbook
----------------

```yaml

---
- hosts: localhost
  vars:
    # Default context
    ldap_lookup_config:
      url: ldap://ldap.example.com
      base: dc=example,dc=com
      # binddn:
      # bindpw:
      # scope: subtree

    # List all users, skip jpegPhoto
    user_nophoto:
      base: ou=People,dc=example,dc=com
      value:
        - jpegPhoto: skip=True
      filter: (uid={{ term }})

    # List all users, return dn and jpegPhoto, Base64-encoded
    user_withphoto:
      base: ou=People,dc=example,dc=com
      key: dn
      value:
        - jpegPhoto:
            encoding: binary
      filter: (uid={{ term }})

    # List every host DN
    hosts:
      base: ou=NetDevices,dc=example,dc=com
      value: dn

    # List group members as plain values (no key)
    group_members:
      base: ou=Groups,dc=example,dc=com
      value: memberUid
      filter: (cn={{ term }})

    # List group members, with CN as key
    group_members_cn:
      base: ou=Groups,dc=example,dc=com
      key: cn
      value: memberUid
      filter: (cn={{ term }})

    # A regular list of users
    users:
      - johndoe
      - marktwain

  tasks:
    - name: Display one user, no photo
      debug: msg="User {{ item }}"
      with_ldap:
        - context: user_nophoto
        - johndoe

    - name: Fetch user, with photo
      debug: msg="User {{ item.dn }} has photo {{ item.jpegPhoto }}"
      with_ldap:
        - context: user_withphoto
        - johndoe

    - name: Direct lookup
      debug: msg="John's full name is {{ lookup('ldap', 'johndoe', context='user_nophoto', value='cn') }}"

    - name: Fetch several users, no photo
      debug: msg="User {{ item }}"
      with_ldap:
        - context: user_nophoto
        - johndoe
        - marktwain

    - name: Fetch several users from a list, no photo
      debug: msg="User {{ item }}"
      with_ldap:
        - context: user_nophoto
        - terms: "{{ users }}"

    - name: Iterate on groups (merging contents), key is CN
      debug: msg="Group {{ item.cn }} contains {{ item.memberUid }}"
      with_ldap:
        - context: group_members_cn
        - devel
        - sales

    - name: Iterate on group members (no key)
      debug: msg="Group member {{ item }}"
      with_ldap:
        - context: group_members
        - devel
        - sales

    - name: Iterate on group members (key is DN, overridden locally)
      debug: msg="Group {{ item.dn }} contains {{ item.memberUid }}"
      with_ldap:
        - context: group_members
        - key: dn
        - devel
        - sales

    - name: Iterate over hosts of some sub-OUs
      debug: msg="Host {{ item }}"
      with_ldap:
        - context: host
          base: {% raw %}ou={{term}},{{context.base}}{% endraw %}
          # Here the search term is not substituted in a filter, but in the
          # search base. Also note reference to the 'base' property of the
          # named context ('host').
          # Note: template references in items are expanded by Ansible prior
          # to being handed off to the lookup plugin. However, references
          # to the search context and search term obviously cannot be
          # resolved at that time. The whole 'base' value therefore needs
          # to be escaped in a {% raw %} block here.
        - webservers
        - dbservers
```


LDAP Filter Plugin
==================

This role provides a few simple Ansible Jinja2 filters for working with
LDAP names.

J2 Filters
----------

* `hostname_to_dn`: Converts a hostname string into a Distinguished Name
  string.
  
  E.g.:
  ```yaml
  server_hostname: some.corp.com
  server_dn: {{ server_hostname | hostname_to_dn }}  # Set 'server_dn' to 'dc=some,dc=corp,dc=com'.
  ```

* `dn_to_hostname`: Converts a Distinguished Name string of Domain Components
  into a hostname string.
  
  E.g.:
  ```yaml
  server_dn: DC=some,DC=corp,DC=com
  server_hostname: {{ server_dn | dn_to_hostname }}  # Set 'server_hostname' to 'some.corp.com'.
  ```


License
=======

BSD


Contributors
============

Pavel Penev <https://github.com/tst-ppenev>: Minor contributions, such as J2 filters.
