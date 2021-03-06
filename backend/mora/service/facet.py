# SPDX-FileCopyrightText: 2018-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0

'''
Facets
------

This sections describes how to interact with facets, i.e. the types of
objects.

    .. http:>jsonarr string name:: Human-readable name.
    .. http:>jsonarr string uuid:: Machine-friendly UUID.
    .. http:>jsonarr string user_key:: Short, unique key.
    .. http:>jsonarr string example:: An example value for the address field.
        A value of `<UUID>` means that this is a `DAR`_ address UUID.

'''

import locale
import uuid

import flask

from .. import common
from .. import exceptions
from .. import mapping
from .. import util

blueprint = flask.Blueprint('facet', __name__, static_url_path='',
                            url_prefix='/service')


@blueprint.route('/o/<uuid:orgid>/f/')
@util.restrictargs()
def list_facets(orgid):
    '''List the facet types available in a given organisation.

    :param uuid orgid: Restrict search to this organisation.

    .. :quickref: Facet; List types

    :>jsonarr string name: The facet name.
    :>jsonarr string path: The location on the web server.
    :>jsonarr string user_key: Short, unique key identifying the facet
    :>jsonarr string uuid: The UUID of the facet.

    :status 200: Always.

    **Example Response**:

    .. sourcecode:: json

      [
        {
          "name": "address",
          "path": "/service/o/456362c4-0ee4-4e5e-a72c-751239745e62/f/address/",
          "user_key": "Adressetype",
          "uuid": "e337bab4-635f-49ce-aa31-b44047a43aa1"
        },
        {
          "name": "ou",
          "path": "/service/o/456362c4-0ee4-4e5e-a72c-751239745e62/f/ou/",
          "user_key": "Enhedstype",
          "uuid": "fc917e7c-fc3b-47c2-8aa5-a0383342a280"
        }
      ]

    '''

    c = common.get_connector()

    r = []

    for facetid, facet in c.facet.get_all(ansvarlig=orgid,
                                          publiceret='Publiceret'):
        r.append(get_one_facet(c, facetid, orgid, facet))

    return flask.jsonify(sorted(
        r,
        # use locale-aware sorting
        key=lambda f: locale.strxfrm(f['name']) if f.get('name') else '',
    ))


def get_one_facet(c, facetid, orgid, facet=None, data=None):
    if not facet:
        facet = c.facet.get(facetid)

    bvn = facet['attributter']['facetegenskaber'][0]['brugervendtnoegle']
    r = {
        'uuid': facetid,
        'user_key': bvn,
        'path': bvn and flask.url_for('facet.get_classes', orgid=orgid,
                                      facet=bvn),
    }

    if data:
        r['data'] = data

    return r


def get_one_class(c, classid, clazz=None):

    only_primary_uuid = flask.request.args.get('only_primary_uuid')
    if only_primary_uuid:
        return {
            mapping.UUID: classid
        }

    if not clazz:
        clazz = c.klasse.get(classid)

        if not clazz:
            return None
            # exceptions.ErrorCodes.E_INVALID_INPUT(
            #     'no such class {!r}'.format(classid),
            # )

    attrs = clazz['attributter']['klasseegenskaber'][0]

    return {
        'uuid': classid,
        'name': attrs.get('titel'),
        'user_key': attrs.get('brugervendtnoegle'),
        'example': attrs.get('eksempel'),
        'scope': attrs.get('omfang'),
    }


@blueprint.route('/o/<uuid:orgid>/f/<facet>/')
@util.restrictargs('limit', 'start')
def get_classes(orgid: uuid.UUID, facet: str):
    '''List classes available in the given facet.

    .. :quickref: Facet; Get

    :param uuid orgid: Restrict search to this organisation.
    :param string facet: One of the facet names listed by
        :http:get:`/service/o/(uuid:orgid)/f/`

    :queryparam int start: Index of first item for paging.
    :queryparam int limit: Maximum items.

    :>jsonarr string name: Human-readable name.
    :>jsonarr string uuid: Machine-friendly UUID.
    :>jsonarr string user_key: Short, unique key.
    :>jsonarr string example: An example value. In most cases the
        value is meant to be presented to the user as an aid.
    :>jsonarr string scope: A representation of the type of value, see
        the table below for details.

    :status 200: On success.
    :status 404: Whenever the facet isn't found.

    **Example Response**:

    .. sourcecode:: json

      {
        "name": "address_type",
        "path":
          "/service/o/456362c4-0ee4-4e5e-a72c-751239745e62/f/address_type/",
        "user_key": "Adressetype",
        "uuid": "e337bab4-635f-49ce-aa31-b44047a43aa1",
        "data": {
          "items": [
            {
              "example": "http://www.korsbaek.dk/",
              "name": "Hjemmeside",
              "scope": "WWW",
              "user_key": "URL",
              "uuid": "160ecaed-50b0-4800-bebc-0d0289a4f624"
            },
            {
              "example": "<UUID>",
              "name": "Lokation",
              "scope": "DAR",
              "user_key": "AdresseLokation",
              "uuid": "031f93c3-6bab-462e-a998-87cad6db3128"
            },
            {
              "example": "Mandag 10:00-12:00 Tirsdag 14:00-16:00",
              "name": "Åbningstid, telefon",
              "scope": "TEXT",
              "user_key": "Åbningstid Telefon",
              "uuid": "0836ffbf-3b3e-410f-8cbf-face7e6844ef"
            }
          ],
          "offset": 0,
          "total": 3
        }
      }

    '''

    c = common.get_connector()

    start = int(flask.request.args.get('start') or 0)
    limit = int(flask.request.args.get('limit') or 0)

    facetids = c.facet(
        bvn=facet,
        ansvarlig=orgid,
        publiceret='Publiceret',
    )

    if not facetids:
        return exceptions.HTTPException(
            exceptions.ErrorCodes.E_NOT_FOUND,
            message="Facet {} not found.".format(facet)
        )

    assert len(facetids) <= 1, 'Facet is not unique'

    return flask.jsonify(
        facetids and get_one_facet(
            c,
            facetids[0],
            orgid,
            data=c.klasse.paged_get(get_one_class,
                                    facet=facetids,
                                    ansvarlig=orgid,
                                    publiceret='Publiceret',
                                    start=start, limit=limit),
        ))
