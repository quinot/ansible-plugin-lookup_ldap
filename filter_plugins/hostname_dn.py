# Copyright (C) 2016, Pavel Penev
#
# This file is contributed to the `lookup_ldap` Ansible role.
# It can be used under BSD, or ISC license.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION
# OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.


import ldap.dn

def hostname_to_dn(arg):
    """Convert a hostname string into a Distinguished Name string.

    E.g.:

    >>> hostname_to_dn('some.corp.com')
    'dc=some,dc=corp,dc=com'
    """
    rdnComponents = [[('dc', name, 1)] for name in arg.split('.')]

    return ldap.dn.dn2str(rdnComponents)

def dn_to_hostname(arg):
    """Convert a Distinguished Name string of Domain Components into a hostname string.

    >>> dn_to_hostname('DC=some,DC=corp,DC=com')
    'some.corp.com'
    """

    dcValues = [[rdnValue for (rdnType, rdnValue, _) in rdnLevel if rdnType.lower() == 'dc'][0]
                for rdnLevel in ldap.dn.str2dn(arg)];

    return '.'.join(dcValues)


# Declare the available filters to Ansible:
class FilterModule(object):
    def filters(self):
        return {
            'hostname_to_dn': hostname_to_dn,
            'dn_to_hostname': dn_to_hostname
        }
