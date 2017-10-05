# Copyright (C) 2014, Thomas Quinot
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

from __future__ import absolute_import

from ansible import errors

from ansible.parsing.splitter import parse_kv
from ansible.plugins.lookup import LookupBase
from ansible.template import Templar

import base64
import ldap
import ldap.sasl
import threading

default_context = 'ldap_lookup_config'

def fill_context(ctx, inject, **kwargs):
    '''Make a complete context from a partial context from an
    iterator call, and configuration information.

    :param dict ctx: query context
    :param dict inject: Ansible variables
    :param kwargs: additional arguments from direct lookup() call
    :return: the configuration dictionary
    :rtype: dict

    '''

    # Start with default config

    fctx = inject.get(default_context, {}).copy()
    fctx['context'] = fctx.copy()

    # Load named config context and overrides from ctx and kwargs

    for d in [ctx, kwargs]:
        if 'context' in d:
            parent_context = d.pop('context')
            if parent_context in inject:
                named_ctx = inject[parent_context]
            else:
                raise errors.AnsibleError(
                    'context %s does not exist' % parent_context)

            # Update filled context with named context

            fctx.update(named_ctx)
            fctx['context'] = fctx.copy()

        fctx.update(d)

    return fctx


def encode(p, v):
    e = p.get('encoding', None)
    if e == 'binary':
        v = base64.b64encode(v)
    elif e is not None:
        v = v.decode(e)
    return v


class LookupModule(LookupBase):

    # We may have to modify LDAP library options when making a new LDAP
    # connection (e.g. to ignore server certificate validation). We don't
    # want any other thread to be attempting to modify library options at
    # the same time.
    #
    # We hope no agent besides this library is trying to set library options
    # simultaneously. Unfortunately, we don't have a way to ensure that.
    # Use library-level options with care.

    __ldap_library_lock = threading.Lock()

    def render_template(self, inject, v):
        return Templar(loader=self._loader, variables=inject).template(v)

    def run(self, terms, variables=None, **kwargs):
        if not isinstance(terms, list):
            terms = [terms]

        ctx = {}
        while len(terms) > 0 and isinstance(terms[0], dict):
            ctx.update(terms.pop(0))
        ctx = fill_context(ctx, variables, **kwargs)

        # Prepare per-term inject, making named context available, if any

        search_inject = variables.copy()

        # Extract search description from context (it may contain references
        # to {{term}}, which cannot be interpolated just yet, as the term
        # variable is still undefined.

        per_item_ctx = {
            'context': ctx.pop('context', None),
            'base':    ctx.pop('base', ''),
            'scope':   ctx.pop('scope', 'subtree'),
            'filter':  ctx.pop('filter', None)
        }
        # At this point, no term-specific items remain in ctx, and we can
        # do template substitution for connection parameters

        try:
            ctx = self.render_template(variables, ctx)
        except Exception, e:
            raise errors.AnsibleError(
                'exception while preparing LDAP parameters: %s' % e)
        self._display.vv("LDAP config: %s" % ctx)

        # Compute attribute list and attribute properties

        base_args = {}
        attr_props = {}
        single_attr = None
        value_spec = ctx.get('value')
        if value_spec is not None and not isinstance(value_spec, list):
            value_spec = [value_spec]
        if value_spec is not None:
            for attr in value_spec:
                if not isinstance(attr, dict):
                    attr_props[attr] = None
                else:
                    for attr_name, attr_prop_dict in attr.items():
                        if not isinstance(attr_prop_dict, dict):
                            attr_prop_dict = parse_kv(attr_prop_dict)
                        attr_props[attr_name] = attr_prop_dict

            base_args['attrlist'] = \
                [a.encode('ASCII') for a in attr_props
                 if attr_props[a] is None
                 or not attr_props[a].get('skip', False)]

            if len(base_args['attrlist']) == 1:
                single_attr = base_args['attrlist'][0]

        self._display.vv('Attribute props: %s' % attr_props)

        key_attr = ctx.get('key')
        if key_attr is not None \
                and key_attr != 'dn' \
                and 'attrlist' in base_args \
                and key_attr not in base_args['attrlist']:
            base_args['attrlist'].append(key_attr.encode('ASCII'))

        # Connect and bind
        with LookupModule.__ldap_library_lock:
            LookupModule.set_ldap_library_options(ctx)
            lo = ldap.initialize(ctx['url'])
            if ctx.get('auth','simple') == 'gssapi':
                auth_tokens = ldap.sasl.gssapi()
                lo.sasl_interactive_bind_s('', auth_tokens)
            else:
                lo.simple_bind_s(ctx.get('binddn', ''), ctx.get('bindpw', ''))

        ret = []

        # If no terms are provided, assume that the user specified all
        # aspects of the search with no reference to {{term}}.

        if terms == []:
            terms = [None]

        for term in terms:
            if isinstance(term, dict):
                raise errors.AnsibleError(
                    'context parameters must come before search terms')

            # Compute templated search parameters

            this_item_ctx = dict(ctx)
            this_item_ctx.update(per_item_ctx)

            search_inject['term'] = term
            search_inject['context'] = this_item_ctx.get('context')
            search_desc = self.render_template(search_inject, this_item_ctx)
            self._display.vv('LDAP search, expanded: %s' % search_desc)

            # Perform search

            base = search_desc['base']
            scope = getattr(ldap, 'SCOPE_%s' % search_desc['scope'].upper())
            args = base_args.copy()
            if search_desc['filter'] is not None:
                args['filterstr'] = search_desc['filter']

            lr = lo.search_s(base, scope, **args)

            # Process results

            for dn, attrs in lr:
                if single_attr is not None:
                    if single_attr == 'dn':
                        items = [dn]
                    else:
                        items = attrs.get(single_attr, [])

                    p = attr_props.get(single_attr) or {}
                    if key_attr is not None:
                        if key_attr == 'term':
                            key = term
                        elif key_attr == 'dn':
                            key = dn
                        else:
                            key = attrs[key_attr][0]
                        ret.extend([{key_attr: key,
                                     single_attr: encode(p, item)}
                                    for item in items])
                    else:
                        ret.extend([encode(p, item) for item in items])

                else:
                    item = {'term': term, 'dn': dn}
                    for a in attrs:
                        p = attr_props.get(a) or {}
                        if not p.get('skip', False):
                            vlist = []
                            for v in attrs[a]:
                                vlist.append(encode(p, v))

                            if 'join' in p:
                                item[a] = p['join'].join(vlist)
                            elif len(vlist) > 1 \
                                    or p.get('always_list', False):
                                item[a] = vlist
                            else:
                                item[a] = vlist[0]

                    ret.append(item)

        return ret

    @staticmethod
    def get_ldap_constant_value(value_specifier, constant_name_prefix):
        if isinstance(value_specifier, basestring):
            return getattr(ldap, constant_name_prefix + value_specifier.upper())
        else:
            return value_specifier

    @staticmethod
    def set_ldap_library_options(options_dictionary):
        value = options_dictionary.get('tls_reqcert', None)
        if not value is None and value != '':
            value = LookupModule.get_ldap_constant_value(value, 'OPT_X_TLS_')
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, value)
