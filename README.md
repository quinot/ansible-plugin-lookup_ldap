## LDAP Lookup Plugin

This lookup plugin provides iteration and lookup on LDAP query results.

#### Requirements and dependencies

Tested on Ansible 1.8

#### Variables

The plugin expects configuration in an `ldap_lookup_config` variable:

```yaml
ldap_lookup_config:
  url: ldap://ldap.example.com
  # URL of the LDAP server
  # Default: None

  base: dc=example,dc=com
  # Base DN for all queries
  # Default: None

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

The defaults can be overridden by declaring specific query contexts,
which are varibles named `ldap_lookup_config/*CONTEXT*`. Any parameter
not overridden in a context is inherited from the defaults.

#### Usage

The `with_ldap` iterator accepts either a single term, or a list of terms,
possibly preceded by one or more dict(s) with possible keys:
  - `context`: a context to use other than the default one
  - any valid configuration parameter to be overridden

LDAP connection parameters (`url`, `binddn`, `bindpw`) and returned value
parameters (`value`, and `key`) are subject to template expansion once
at the beginning of the iteration.

Search parameters (`base`, `scope`, and `filter`) are expanded for each
term. The following additional variables are defined at that point:
  -  `context`: the named context, if any, else the default one;
  -  `term`: the search term.

#### Example

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
    ldap_lookup_config/user_nophoto:
      base: ou=People,dc=example,dc=com
      value:
        - jpegPhoto: skip=True
      filter: (uid={{ term }})

    # List all users, return dn and jpegPhoto, Base64-encoded
    ldap_lookup_config/user_withphoto:
      base: ou=People,dc=example,dc=com
      key: dn
      value:
        - jpegPhoto:
            encoding: binary
      filter: (uid={{ term }})

    # List every host DN
    ldap_lookup_config/hosts:
      base: ou=NetDevices,dc=example,dc=com
      value: dn

    # List group members as plain values (no key)
    ldap_lookup_config/group_members:
      base: ou=Groups,dc=example,dc=com
      value: memberUid
      filter: (cn={{ term }})

    # List group members, with CN as key
    ldap_lookup_config/group_members_cn:
      base: ou=Groups,dc=example,dc=com
      key: cn
      value: memberUid
      filter: (cn={{ term }})

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
          base: ou={{term}},{{context.base}}
          # Here the search term is not substituted in a filter,
          # but in the search base. Also note reference to
          # the 'base' property of the named context ('host').
        - webservers
        - dbservers
```
