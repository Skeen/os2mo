# SPDX-FileCopyrightText: 2017-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0

from __future__ import generator_stop
import aiohttp
import asyncio
from functools import wraps
def async_to_sync(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(f(*args, **kwargs))
        return loop.run_until_complete(future)

    return wrapper


import itertools
import uuid

import requests

import flask_saml_sso

import lora_utils
from . import exceptions
from . import settings
from . import util

session = requests.Session()
session.verify = settings.CA_BUNDLE or True
session.auth = flask_saml_sso.SAMLAuth()
session.headers = {
    'User-Agent': 'MORA/0.1',
}


def _check_response(r):
    if not r.ok:
        try:
            cause = r.json()
            msg = cause['message']
        except (ValueError, KeyError):
            cause = None
            msg = r.text

        if r.status_code == 400:
            exceptions.ErrorCodes.E_INVALID_INPUT(message=msg, cause=cause)
        elif r.status_code == 401:
            exceptions.ErrorCodes.E_UNAUTHORIZED(message=msg, cause=cause)
        elif r.status_code == 403:
            exceptions.ErrorCodes.E_FORBIDDEN(message=msg, cause=cause)
        else:
            exceptions.ErrorCodes.E_UNKNOWN(message=msg, cause=cause)

    return r

async def _acheck_response(r):
    if r.status != 200:
        try:
            cause = await r.json()
            msg = cause['message']
        except (ValueError, KeyError):
            cause = None
            msg = await r.text

        if r.status == 400:
            exceptions.ErrorCodes.E_INVALID_INPUT(message=msg, cause=cause)
        elif r.status == 401:
            exceptions.ErrorCodes.E_UNAUTHORIZED(message=msg, cause=cause)
        elif r.status == 403:
            exceptions.ErrorCodes.E_FORBIDDEN(message=msg, cause=cause)
        else:
            exceptions.ErrorCodes.E_UNKNOWN(message=msg, cause=cause)

    return r




class Connector:

    scope_map = dict(
        organisation='organisation/organisation',
        organisationenhed='organisation/organisationenhed',
        organisationfunktion='organisation/organisationfunktion',
        bruger='organisation/bruger',
        itsystem='organisation/itsystem',
        klasse='klassifikation/klasse',
        facet='klassifikation/facet',
        klassifikation='klassifikation/klassifikation',
    )

    def __init__(self, **defaults):
        self.__validity = defaults.pop('validity', None) or 'present'

        self.now = util.parsedatetime(
            defaults.pop('effective_date', None) or util.now(),
        )

        if self.__validity == 'past':
            self.start = util.NEGATIVE_INFINITY
            self.end = self.now

        elif self.__validity == 'future':
            self.start = self.now
            self.end = util.POSITIVE_INFINITY

        elif self.__validity == 'present':
            # we should probably use 'virkningstid' but that means we
            # have to override each and every single invocation of the
            # accessors later on
            if 'virkningfra' in defaults:
                self.start = self.now = util.parsedatetime(
                    defaults.pop('virkningfra'),
                )
            else:
                self.start = self.now

            if 'virkningtil' in defaults:
                self.end = util.parsedatetime(defaults.pop('virkningtil'))
            else:
                self.end = self.start + util.MINIMAL_INTERVAL

        else:
            exceptions.ErrorCodes.V_INVALID_VALIDITY(validity=self.__validity)

        defaults.update(
            virkningfra=util.to_lora_time(self.start),
            virkningtil=util.to_lora_time(self.end),
            konsolider=True,
        )

        self.__defaults = defaults

    @property
    def defaults(self):
        return self.__defaults

    @property
    def validity(self):
        return self.__validity

    def is_range_relevant(self, start, end, effect):
        if self.validity == 'present':
            return util.do_ranges_overlap(self.start, self.end, start, end)
        else:
            return start > self.start and end <= self.end

    def __getattr__(self, attr):
        try:
            path = self.scope_map[attr]
        except KeyError:
            raise AttributeError(attr)

        scope = Scope(self, path)
        setattr(self, attr, scope)

        return scope

    def is_effect_relevant(self, effect):
        return self.__is_range_relevant(util.parsedatetime(effect['from']),
                                        util.parsedatetime(effect['to']))


class Scope:
    def __init__(self, connector, path):
        self.connector = connector
        self.path = path

    @property
    def base_path(self):
        return settings.LORA_URL + self.path

    def fetch(self, **params):
        r = session.get(self.base_path, params={
            **self.connector.defaults,
            **params,
        })

        _check_response(r)

        try:
            return r.json()['results'][0]
        except IndexError:
            return []

    async def afetch(self, session, **params):
        params = dict(**self.connector.defaults, **params)
        tup_list = []
    
        def handle_pair(key, value):
            if type(value) is bool:
                tup_list.append((key, str(value)))
            elif type(value) is list:
                for val in value:
                    handle_pair(key, val)
            elif type(value) is str:
                tup_list.append((key, value))
            else:
                print("WOW")

        for key, value in params.items():
            handle_pair(key, value)

        async with session.get(self.base_path, params=tup_list) as response:

            await _acheck_response(response)

            try:
                return (await response.json())['results'][0]
            except IndexError:
                return []

    __call__ = fetch

    @async_to_sync
    async def get_all(self, *, start=0, limit=settings.DEFAULT_PAGE_SIZE, **params):
        if limit > 0:
            params['maximalantalresultater'] = limit
        params['foersteresultat'] = start

        if 'uuid' in params:
            uuids = util.uniqueify(params.pop('uuid'))[start:start + limit]
        else:
            uuids = self.fetch(**params)

        wantregs = params.keys() & {'registreretfra', 'registrerettil'}

        # as an optimisation, we want to minimize the amount of
        # roundtrips whilst also avoiding too large requests -- to
        # this, we calculate in advance how many we can request
        available_length = settings.MAX_REQUEST_LENGTH
        available_length -= 4  # for 'GET '
        available_length -= len(self.base_path)

        for k, v in itertools.chain(self.connector.defaults.items(),
                                    params.items()):
            available_length -= len(k) + len(str(v)) + 2

        per_length = 36 + len('&uuid=')

        returns = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            for chunk in util.splitlist(uuids, int(available_length / per_length)):
                tasks.append(self.afetch(session, uuid=chunk))
            for d in list(*await asyncio.gather(*tasks)):
                returns.append((d['id'], (d['registreringer'] if wantregs
                                    else d['registreringer'][0])))
        return returns

    def paged_get(self, func, *,
                  start=0, limit=settings.DEFAULT_PAGE_SIZE,
                  **params):

        uuids = self.fetch(**params)

        return {
            'total': len(uuids),
            'offset': start,
            'items': [
                func(self.connector, obj_id, obj)
                for obj_id, obj in self.get_all(
                    start=start, limit=limit, **params)
            ],
        }

    def get(self, uuid, **params):
        d = self.fetch(uuid=str(uuid), **params)

        if not d or not d[0]:
            return None

        registrations = d[0]['registreringer']

        assert len(d) == 1

        if params.keys() & {'registreretfra', 'registrerettil'}:
            return registrations
        else:
            assert len(registrations) == 1

            return registrations[0]

    def create(self, obj, uuid=None):
        if uuid:
            r = session.put('{}/{}'.format(self.base_path, uuid),
                            json=obj)
        else:
            r = session.post(self.base_path, json=obj)

        _check_response(r)
        return r.json()['uuid']

    def delete(self, uuid):
        r = session.delete('{}/{}'.format(self.base_path, uuid))
        _check_response(r)

    def update(self, obj, uuid):
        r = session.request(
            'PATCH',
            '{}/{}'.format(self.base_path, uuid),
            json=obj,
        )
        _check_response(r)
        return r.json()['uuid']

    def get_effects(self, obj, relevant, also=None, **params):
        reg = (
            self.get(obj, **params)
            if isinstance(obj, (str, uuid.UUID))
            else obj
        )

        if not reg:
            return

        effects = list(lora_utils.get_effects(reg, relevant, also))

        return filter(
            lambda a: self.connector.is_range_relevant(*a),
            effects,
        )


def get_version():
    r = session.get(settings.LORA_URL + "version")
    try:
        return r.json()["lora_version"]
    except ValueError:
        return "Could not find lora version: %s" % r.text
