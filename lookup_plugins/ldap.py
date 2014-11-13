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

from ansible import utils, errors
from ansible.callbacks import vv
from ansible.utils import template

import base64
import os

conf_prefix = 'ldap_lookup_config'

HAVE_LDAP = False
try:
    import ldap
    HAVE_LDAP = True
except ImportError, e:
    print e
    pass


def attr_name(attr_spec):
    '''Return the LDAP attribute name for an attribute spec

    :param str or dict attr_spec: attribute spec
    :return: attribute name
    :rtype: str

    attr_spec may be a naked attribute name (in which case
    it is returned unchanged), or a dict with a single key:

      {<attr_name>: {properties}}

    in which case the key is returned.

    '''

    if isinstance(attr_spec, dict):
        k = attr_spec.keys()
        assert(len(k) == 1)
        return k[0]

    else:
        return attr_spec


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

    fctx = inject[conf_prefix].copy()
    fctx['context'] = fctx.copy()

    # Load named config context and overrides from ctx and kwargs

    for d in [ctx, kwargs]:
        if 'context' in d:
            named_ctx = inject['%s/%s' % (conf_prefix, d.pop('context'))]

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


class LookupModule(object):

    def __init__(self, basedir=None, **kwargs):
        self.basedir = basedir
        if HAVE_LDAP == False:
            raise errors.AnsibleError(
                "Can't LOOKUP(ldap): module ldap is not installed")

    def run(self, terms, inject=None, **kwargs):

        terms = utils.listify_lookup_plugin_terms(terms, self.basedir, inject)

        if not isinstance(terms, list):
            terms = [terms]

        ctx = {}
        while isinstance(terms[0], dict):
            ctx.update(terms.pop(0))
        ctx = fill_context(ctx, inject, **kwargs)

        # Template substitution on connection parameters

        try:
            ctx = template.template(self.basedir, ctx, inject)
        except Exception, e:
            print "exception: %s" % e
        vv("LDAP config: %s" % ctx)

        # Prepare per-term inject, making named context available, if any

        search_inject = inject.copy()
        search_inject['context'] = ctx.get('context')

        # Compute attribute list and attribute properties

        base_args = {}
        attr_props = {}
        single_attr = None
        value_spec = ctx.get('value')
        if isinstance(value_spec, str):
            value_spec = [value_spec]
        if value_spec is not None:
            for attr in value_spec:
                if isinstance(attr, str):
                    attr_props[attr] = None
                else:
                    for attr_name, attr_prop_dict in attr.items():
                        if isinstance(attr_prop_dict, str):
                            attr_prop_dict = utils.parse_kv(attr_prop_dict)
                        attr_props[attr_name] = attr_prop_dict

            base_args['attrlist'] = \
                [a for a in attr_props
                 if attr_props[a] is None
                 or not attr_props[a].get('skip', False)]

            if len(base_args['attrlist']) == 1:
                single_attr = base_args['attrlist'][0]

        vv('Attribute props: %s' % attr_props)

        key_attr = ctx.get('key')
        if key_attr is not None \
                and key_attr != 'dn' \
                and 'attrlist' in base_args \
                and key_attr not in base_args['attrlist']:
            base_args['attrlist'].append(key_attr)

        # Connect and bind

        lo = ldap.initialize(ctx['url'])
        lo.simple_bind_s(ctx.get('binddn', ''), ctx.get('bindpw', ''))

        ret = []
        for term in terms:
            if isinstance(term, dict):
                raise errors.AnsibleError(
                    'context parameters must come before search terms')

            # Compute templated search parameters

            search_inject['term'] = term

            search_desc = {
                'base':   ctx.get('base', ''),
                'scope':  ctx.get('scope', 'subtree'),
                'filter': ctx.get('filter')
            }
            search_desc = template.template(
                self.basedir, search_desc, search_inject)
            vv('LDAP search, expanded: %s' % search_desc)

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
                        items = attrs[single_attr]

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
