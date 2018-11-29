#
# Copyright (c) 2017-2018, Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

'''
Organisational units
--------------------

This section describes how to interact with organisational units.

For more information regarding reading relations involving organisational
units, refer to :http:get:`/service/(any:type)/(uuid:id)/details/`

'''

import collections
import enum
import functools
import locale
import operator
import uuid

import werkzeug
import flask

from . import address
from . import facet
from . import handlers
from . import org
from .. import common
from .. import exceptions
from .. import lora
from .. import mapping
from .. import settings
from .. import util
from .. import validator

blueprint = flask.Blueprint('orgunit', __name__, static_url_path='',
                            url_prefix='/service')


@enum.unique
class UnitDetails(enum.Enum):
    # name & userkey only
    MINIMAL = 0

    # with child count
    NCHILDREN = 1

    # with everything except child count
    SELF = 2

    # same as above, but with all parents
    FULL = 3

    # minimal and integration_data
    INTEGRATION = 4


class OrgUnitRequestHandler(handlers.ReadingRequestHandler):
    __slots__ = ()

    role_type = 'org_unit'

    @classmethod
    def has(cls, scope, reg):
        return scope.path == 'organisation/organisationenhed' and reg

    @classmethod
    def get(cls, scope, objid):
        if scope.path != 'organisation/organisationenhed':
            exceptions.ErrorCodes.E_INVALID_ROLE_TYPE()

        c = scope.connector

        return flask.jsonify([
            get_one_orgunit(
                c, objid, effect, details=UnitDetails.SELF,
                validity={
                    mapping.FROM: util.to_iso_date(start),
                    mapping.TO: util.to_iso_date(end, is_end=True),
                },
            )
            for start, end, effect in scope.get_effects(
                objid,
                {
                    'attributter': (
                        'organisationenhedegenskaber',
                    ),
                    'relationer': (
                        'enhedstype',
                        'overordnet',
                        'tilhoerer',
                    ),
                    'tilstande': (
                        'organisationenhedgyldighed',
                    ),
                },
            )
            if c.is_effect_relevant({'from': start, 'to': end}) and
            effect.get('tilstande')
                  .get('organisationenhedgyldighed')[0]
                  .get('gyldighed') == 'Aktiv'
        ])

    def prepare_create(self, req):
        c = lora.Connector()

        req = flask.request.get_json()

        name = util.checked_get(req, mapping.NAME, "", required=True)

        integration_data = util.checked_get(
            req,
            mapping.INTEGRATION_DATA,
            "",
            required=False
        )

        unitid = util.get_uuid(req, required=False)
        bvn = util.checked_get(req, mapping.USER_KEY,
                               "{} {}".format(name, uuid.uuid4()))

        parent_uuid = util.get_mapping_uuid(req, mapping.PARENT, required=True)
        organisationenhed_get = c.organisationenhed.get(parent_uuid)

        if organisationenhed_get:
            org_uuid = organisationenhed_get['relationer']['tilhoerer'][0][
                'uuid']
        else:
            organisation_get = c.organisation(uuid=parent_uuid)

            if organisation_get:
                org_uuid = parent_uuid
            else:
                exceptions.ErrorCodes.V_PARENT_NOT_FOUND(
                    parent_uuid=parent_uuid,
                    org_unit_uuid=unitid,
                )

        org_unit_type_uuid = util.get_mapping_uuid(req, mapping.ORG_UNIT_TYPE,
                                                   required=False)

        addresses = [
            address.get_relation_for(addr)
            for addr in util.checked_get(req, mapping.ADDRESSES, [])
        ]
        valid_from = util.get_valid_from(req)
        valid_to = util.get_valid_to(req)

        org_unit = common.create_organisationsenhed_payload(
            valid_from=valid_from,
            valid_to=valid_to,
            enhedsnavn=name,
            brugervendtnoegle=bvn,
            tilhoerer=org_uuid,
            enhedstype=org_unit_type_uuid,
            overordnet=parent_uuid,
            adresser=addresses,
            integration_data=integration_data,
        )

        if org_uuid != parent_uuid:
            validator.is_date_range_in_org_unit_range(parent_uuid, valid_from,
                                                      valid_to)

        self.payload = org_unit
        self.uuid = unitid

    def prepare_edit(self, req: dict):
        original_data = util.checked_get(req, 'original', {}, required=False)
        data = util.checked_get(req, 'data', {}, required=True)

        unitid = util.get_uuid(data, fallback=original_data)

        # Get the current org-unit which the user wants to change
        c = lora.Connector(virkningfra='-infinity', virkningtil='infinity')
        original = c.organisationenhed.get(uuid=unitid)

        if not original:
            exceptions.ErrorCodes.E_ORG_UNIT_NOT_FOUND(org_unit_uuid=unitid)

        new_from, new_to = util.get_validities(data)

        # Get org unit uuid for validation purposes
        parent = util.get_obj_value(
            original, mapping.PARENT_FIELD.path)[-1]
        parent_uuid = util.get_uuid(parent)

        org_uuid = util.get_obj_uuid(original, mapping.BELONGS_TO_FIELD.path)

        payload = dict()
        payload['note'] = 'Rediger organisationsenhed'

        if original_data:
            # We are performing an update
            old_from, old_to = util.get_validities(original_data)
            payload = common.inactivate_old_interval(
                old_from, old_to, new_from, new_to, payload,
                ('tilstande', 'organisationenhedgyldighed')
            )

            original_uuid = util.get_mapping_uuid(original_data,
                                                  mapping.ORG_UNIT)

            if original_uuid and original_uuid != unitid:
                exceptions.ErrorCodes.E_INVALID_INPUT(
                    'cannot change unit uuid!',
                )

        update_fields = list()

        # Always update gyldighed
        update_fields.append((
            mapping.ORG_UNIT_GYLDIGHED_FIELD,
            {'gyldighed': "Aktiv"}
        ))

        if mapping.NAME in data or mapping.INTEGRATION_DATA in data:
            attrs = mapping.ORG_UNIT_EGENSKABER_FIELD.get(original)[-1].copy()

            if mapping.NAME in data:
                attrs['enhedsnavn'] = data[mapping.NAME]

            if mapping.INTEGRATION_DATA in data:
                attrs['integrationsdata'] = data[mapping.INTEGRATION_DATA]

            update_fields.append((
                mapping.ORG_UNIT_EGENSKABER_FIELD,
                attrs,
            ))

        if mapping.ORG_UNIT_TYPE in data:
            update_fields.append((
                mapping.ORG_UNIT_TYPE_FIELD,
                {'uuid': data[mapping.ORG_UNIT_TYPE]['uuid']}
            ))

        if mapping.PARENT in data:
            parent_uuid = util.get_mapping_uuid(data, mapping.PARENT)
            validator.is_candidate_parent_valid(unitid,
                                                parent_uuid, new_from)
            update_fields.append((
                mapping.PARENT_FIELD,
                {'uuid': parent_uuid}
            ))

        payload = common.update_payload(new_from, new_to, update_fields,
                                        original, payload)

        bounds_fields = list(
            mapping.ORG_UNIT_FIELDS.difference({x[0] for x in update_fields}))
        payload = common.ensure_bounds(new_from, new_to, bounds_fields,
                                       original, payload)

        # TODO: Check if we're inside the validity range of the organisation
        if org_uuid != parent_uuid:
            validator.is_date_range_in_org_unit_range(parent_uuid, new_from,
                                                      new_to)
        self.payload = payload
        self.uuid = unitid

    def submit(self):
        c = lora.Connector()

        if self.request_type == handlers.RequestType.CREATE:
            return c.organisationenhed.create(self.payload, self.uuid)
        else:
            return c.organisationenhed.update(self.payload, self.uuid)


def get_one_orgunit(c, unitid, unit=None,
                    details=UnitDetails.NCHILDREN, validity=None) -> dict:
    '''Internal API for returning one organisation unit.

    '''

    if not unit:
        unit = c.organisationenhed.get(unitid)

        if not unit or not util.is_reg_valid(unit):
            return None

    attrs = unit['attributter']['organisationenhedegenskaber'][0]
    rels = unit['relationer']
    validities = unit['tilstande']['organisationenhedgyldighed']

    unittype = util.get_uuid(rels['enhedstype'][0], required=False)
    parentid = rels['overordnet'][0]['uuid']
    orgid = rels['tilhoerer'][0]['uuid']

    r = {
        'name': attrs['enhedsnavn'],
        'user_key': attrs['brugervendtnoegle'],
        'uuid': unitid,
    }

    if details is UnitDetails.NCHILDREN:
        children = c.organisationenhed(overordnet=unitid, gyldighed='Aktiv')

        r['child_count'] = len(children)

    elif details is UnitDetails.FULL:
        parent = get_one_orgunit(c, parentid, details=UnitDetails.FULL)

        r[mapping.ORG] = org.get_one_organisation(
            c, orgid,
        )

        if parentid is not None:
            if parent and parent[mapping.LOCATION]:
                r[mapping.LOCATION] = (parent[mapping.LOCATION] + '/' +
                                       parent[mapping.NAME])
            elif parent:
                r[mapping.LOCATION] = parent[mapping.NAME]
            else:
                r[mapping.LOCATION] = ''

            if unitid in settings.USER_SETTINGS['orgunit']:
                org_settings = {'orgunit':
                                settings.USER_SETTINGS['orgunit'][unitid]}
                r[mapping.USER_SETTINGS] = org_settings
            elif parent and mapping.USER_SETTINGS in parent:
                r[mapping.USER_SETTINGS] = parent[mapping.USER_SETTINGS]
            else:
                r[mapping.USER_SETTINGS] = settings.USER_SETTINGS

        r[mapping.PARENT] = parent

        r[mapping.ORG_UNIT_TYPE] = (
            facet.get_one_class(c, unittype) if unittype else None
        )

    elif details is UnitDetails.SELF:
        r[mapping.ORG] = org.get_one_organisation(c, orgid)
        r[mapping.PARENT] = get_one_orgunit(c, parentid,
                                            details=UnitDetails.MINIMAL)
        r[mapping.ORG_UNIT_TYPE] = (
            facet.get_one_class(c, unittype) if unittype else None
        )

    elif details is UnitDetails.MINIMAL:
        pass  # already done
    elif details is UnitDetails.INTEGRATION:
        r["integration_data"] = attrs.get("integrationsdata", "")
    else:
        assert False, 'enum is {}!?'.format(details)

    r[mapping.VALIDITY] = validity or util.get_effect_validity(validities[0])

    return r


@blueprint.route('/<any(o,ou):type>/<uuid:parentid>/children')
@util.restrictargs('at')
def get_children(type, parentid):
    '''Obtain the list of nested units within an organisation or an
    organisational unit.

    .. :quickref: Unit; Children

    :param type: 'o' if the parent is an organistion, and 'ou' if it's a unit.
    :param uuid parentid: The UUID of the parent.

    :queryparam date at: Show the children valid at this point in time,
        in ISO-8601 format.

    :>jsonarr string name: Human-readable name of the unit.
    :>jsonarr string user_key: Short, unique key identifying the unit.
    :>jsonarr object validity: Validity range of the organisational unit.
    :>jsonarr uuid uuid: Machine-friendly UUID of the unit.
    :>jsonarr int child_count: Number of org. units nested immediately beneath
                               the organisation.

    :status 200: Whenever the organisation or unit exists and is readable.
    :status 404: When no such organisation or unit exists, or the
                 parent was of the wrong type.

    **Example Response**:

    .. sourcecode:: json

      [
        {
          "name": "Humanistisk fakultet",
          "user_key": "hum",
          "uuid": "9d07123e-47ac-4a9a-88c8-da82e3a4bc9e",
          "child_count": 2,
          "validity": {
              "from": "2016-01-01",
              "to": "2018-12-31"
          }
        },
        {
          "name": "Samfundsvidenskabelige fakultet",
          "user_key": "samf",
          "uuid": "b688513d-11f7-4efc-b679-ab082a2055d0",
          "child_count": 0,
          "validity": {
              "from": "2016-01-01",
              "to": "2018-12-31"
          }
        }
      ]

    '''
    c = common.get_connector()

    if type == 'o':
        scope = c.organisation
    else:
        assert type == 'ou'
        scope = c.organisationenhed

    obj = scope.get(parentid)

    if not obj or not obj.get('attributter'):
        exceptions.ErrorCodes.E_ORG_UNIT_NOT_FOUND(org_unit_uuid=parentid)

    children = [
        get_one_orgunit(c, childid, child)
        for childid, child in
        c.organisationenhed.get_all(overordnet=parentid,
                                    gyldighed='Aktiv')
    ]

    children.sort(key=operator.itemgetter('name'))

    return flask.jsonify(children)


@blueprint.route('/ou/<uuid:unitid>/ancestor-tree')
@util.restrictargs('at')
def get_unit_ancestor_tree(unitid):
    '''Obtain the tree of ancestors for a given unit.

    The tree includes siblings of ancestors, with their child counts:

    * Every ancestor of the unit.
    * Every sibling of every ancestor, with a child count.

    The intent of this routine is to enable easily showing the tree
    _up to and including_ a given unit in a UI.

    .. :quickref: Unit; Ancestor tree

    :param unitid: The UUID of the organisational unit.

    :see: http:get:`/service/ou/(uuid:unitid)/`.

    **Example Response**:

    .. sourcecode:: json

     {
        "children": [
          {
            "child_count": 2,
            "name": "Humanistisk fakultet",
            "user_key": "hum",
            "uuid": "9d07123e-47ac-4a9a-88c8-da82e3a4bc9e",
            "validity": {
              "from": "2016-01-01",
              "to": null
            }
          },
          {
            "child_count": 0,
            "name": "Samfundsvidenskabelige fakultet",
            "user_key": "samf",
            "uuid": "b688513d-11f7-4efc-b679-ab082a2055d0",
            "validity": {
              "from": "2017-01-01",
              "to": null
            }
          }
        ],
        "name": "Overordnet Enhed",
        "user_key": "root",
        "uuid": "2874e1dc-85e6-4269-823a-e1125484dfd3",
        "validity": {
          "from": "2016-01-01",
          "to": null
        }
      }

    '''
    c = common.get_connector()

    def get_parent(objid):
        return mapping.PARENT_FIELD(unitcache[objid])[0]['uuid']

    unitcache = common.cache(c.organisationenhed.get)
    id_path = collections.deque([unitid])

    try:
        orgid = mapping.BELONGS_TO_FIELD(unitcache[unitid])[0]['uuid']
    except LookupError:
        exceptions.ErrorCodes.E_ORG_UNIT_NOT_FOUND.raise_with(
            org_unit_uuid=unitid,
        )

    # first, get the path to the unit
    while get_parent(id_path[0]) != orgid:
        id_path.appendleft(get_parent(id_path[0]))

    # bail if we're the root unit; that's simpler than handling it in
    # the other logic
    if len(id_path) == 1:
        return flask.jsonify(get_one_orgunit(c, unitid, unitcache[unitid],
                                             details=UnitDetails.NCHILDREN))

    # then, fetch all the ancestors
    ancestors = {
        ancestorid: get_one_orgunit(c, ancestorid, unitcache[ancestorid],
                                    details=UnitDetails.MINIMAL)
        for ancestorid in id_path
        if ancestorid != unitid
    }

    # now, inject the children, and link them up
    for ancestor in ancestors.values():
        if ancestor is None:
            continue

        # please note that the code below actually re-fetches the
        # ancestor itself -- however, that's unlikely to be what makes
        # this function slow
        ancestor['children'] = sorted(
            (
                (
                    get_one_orgunit(c, siblingid, sibling,
                                    details=UnitDetails.NCHILDREN)
                    if siblingid not in ancestors
                    else
                    ancestors[siblingid]
                )
                for siblingid, sibling in c.organisationenhed.get_all(
                    overordnet=ancestor[mapping.UUID],
                    gyldighed='Aktiv',
                )
            ),
            key=lambda u: locale.strxfrm(u[mapping.NAME]),
        )

    # finally, return the root unit
    return flask.jsonify(ancestors[id_path[0]])


def get_unit_tree(c, orgid, unitids):
    '''Return a tree, bounded by the given unitid.

    The tree includes siblings of ancestors, with their child counts.

    '''

    def get_parent(unitid):
        try:
            return mapping.PARENT_FIELD(units[unitid])[0]['uuid']
        except LookupError:
            return None

    def get_unit(unitid):
        r = get_one_orgunit(
            c, unitid, units[unitid], details=UnitDetails.MINIMAL,
        )

        if unitid in children:
            r['children'] = get_units(children.getlist(unitid))

        return r

    def get_units(unitids):
        r = sorted(
            map(get_unit, unitids),
            key=lambda u: locale.strxfrm(u[mapping.NAME]),
        )

        return r

    units = {}
    children = werkzeug.datastructures.MultiDict()

    leaves = set(unitids)

    while any(leaves):
        units.update(c.organisationenhed.get_all(uuid=leaves))

        parentids = {leaf: get_parent(leaf) for leaf in leaves}

        children.update(zip(parentids.values(), parentids.keys()))

        leaves = set(parentids.values()) - units.keys()

    return get_units(children.getlist(orgid))


@blueprint.route('/ou/<uuid:unitid>/')
@util.restrictargs('at', 'unitdetails')
def get_orgunit(unitid):
    '''Get an organisational unit

    .. :quickref: Unit; Get

    :param uuid unitid: UUID of the unit to retrieve.

    :queryparam date at: Show the unit at this point in time,
        in ISO-8601 format.

    :>json string name: The name of the org unit
    :>json string user_key: A unique key for the org unit.
    :>json uuid uuid: The UUId of the org unit
    :>json uuid parent: The parent org unit or organisation
    :>json uuid org: The organisation the unit belongs to
    :>json uuid org_unit_type: The type of org unit
    :>json object validity: The validity of the created object.

    :status 200: Whenever the object exists.
    :status 404: Otherwise.

    **Example Response**:

    .. sourcecode:: json

      {
        "location": "Overordnet Enhed/Humanistisk fakultet/Historisk Institut",
        "name": "Afdeling for Fortidshistorik",
        "user_key": "frem",
        "uuid": "04c78fc2-72d2-4d02-b55f-807af19eac48",
        "org": {
          "name": "Aarhus Universitet",
          "user_key": "AU",
          "uuid": "456362c4-0ee4-4e5e-a72c-751239745e62"
        },
        "org_unit_type": {
          "example": null,
          "name": "Afdeling",
          "scope": null,
          "user_key": "afd",
          "uuid": "32547559-cfc1-4d97-94c6-70b192eff825"
        },
        "parent": {
          "name": "Historisk Institut",
          "user_key": "hist",
          "uuid": "da77153e-30f3-4dc2-a611-ee912a28d8aa",
          "validity": {
            "from": "2016-01-01",
            "to": "2018-12-31"
          }
        },
        "validity": {
          "from": "2016-01-01",
          "to": "2018-12-31"
        }
      }

    '''
    c = common.get_connector()

    details = flask.request.args.get("unitdetails", UnitDetails.FULL)

    if isinstance(details, str):
        enum_details = getattr(UnitDetails, details, False)
        if not enum_details:
            raise exceptions.HTTPException(
                exceptions.ErrorCodes.E_DETAILS_SPEC_NOT_FOUND,
                detail_spec=details,
            )
        details = enum_details

    r = get_one_orgunit(c, unitid, details=details)

    if not r:
        exceptions.ErrorCodes.E_ORG_UNIT_NOT_FOUND(org_unit_uuid=unitid)

    return flask.jsonify(r)


@blueprint.route('/o/<uuid:orgid>/ou/')
@util.restrictargs('at', 'start', 'limit', 'query')
def list_orgunits(orgid):
    '''Query organisational units in an organisation.

    .. :quickref: Unit; List & search

    :param uuid orgid: UUID of the organisation to search.

    :queryparam date at: Show the units valid at this point in time,
        in ISO-8601 format.
    :queryparam int start: Index of first unit for paging.
    :queryparam int limit: Maximum items
    :queryparam string query: Filter by units matching this string.

    :>json string items: The returned items.
    :>json string offset: Pagination offset.
    :>json string total: Total number of items available on this query.

    :>jsonarr string name: Human-readable name.
    :>jsonarr string uuid: Machine-friendly UUID.
    :>jsonarr string user_key: Short, unique key identifying the unit.
    :>jsonarr object validity: Validity range of the organisational unit.

    :status 200: Always.

    **Example Response**:

    .. sourcecode:: json

      {
        "items": [
          {
            "name": "Humanistisk fakultet",
            "user_key": "hum",
            "uuid": "9d07123e-47ac-4a9a-88c8-da82e3a4bc9e",
            "validity": {
              "from": "2016-01-01",
              "to": null
            }
          },
          {
            "name": "Samfundsvidenskabelige fakultet",
            "user_key": "samf",
            "uuid": "b688513d-11f7-4efc-b679-ab082a2055d0",
            "validity": {
              "from": "2017-01-01",
              "to": null
            }
          }
        ],
        "offset": 0,
        "total": 2
      }

    '''
    c = common.get_connector()

    args = flask.request.args

    limits = dict(
        limit=int(args.get('limit', 0)) or settings.DEFAULT_PAGE_SIZE,
        start=int(args.get('start', 0)) or 0,
    )

    kwargs = dict(
        tilhoerer=orgid,
        gyldighed='Aktiv',
    )

    if 'query' in args:
        kwargs.update(vilkaarligattr='%{}%'.format(args['query']))

    return flask.jsonify(
        c.organisationenhed.paged_get(
            functools.partial(get_one_orgunit, details=UnitDetails.MINIMAL),
            **limits,
            **kwargs,
        )
    )


@blueprint.route('/ou/create', methods=['POST'])
def create_org_unit():
    """Creates new organisational unit

    .. :quickref: Unit; Create

    :statuscode 200: Creation succeeded.

    **Example Request**:

    :<json string name: The name of the org unit
    :<json uuid parent: The parent org unit or organisation
    :<json uuid org_unit_type: The type of org unit
    :<json list addresses: A list of address objects.
    :<json object validity: The validity of the created object.

    The parameter ``org_unit_type`` should contain
    an UUID obtained from the respective facet endpoint.
    See :http:get:`/service/o/(uuid:orgid)/f/(facet)/`.
    For the ``addresses`` parameter, see :ref:`Adresses <address>`.

    Validity objects are defined as such:

    :<jsonarr string from: The from date, in ISO 8601.
    :<jsonarr string to: The to date, in ISO 8601.

    .. sourcecode:: json

      {
        "name": "Name",
        "parent": {
          "uuid": "62ec821f-4179-4758-bfdf-134529d186e9"
        },
        "org_unit_type": {
          "uuid": "3ef81e52-0deb-487d-9d0e-a69bbe0277d8"
        },
        "validity": {
          "from": "2016-01-01",
          "to": null
        },
        "addresses": [{
          "value": "0101501234",
          "address_type": {
            "example": "5712345000014",
            "name": "EAN",
            "scope": "EAN",
            "user_key": "EAN",
            "uuid": "e34d4426-9845-4c72-b31e-709be85d6fa2"
          },
          "validity": {
            "from": "2016-01-01",
            "to": "2017-12-31"
          }
        }]
      }

    :returns: UUID of created org unit

    """

    req = flask.request.get_json()
    request = OrgUnitRequestHandler(req, handlers.RequestType.CREATE)

    return flask.jsonify(request.submit()), 201


@blueprint.route('/ou/<uuid:unitid>/terminate', methods=['POST'])
def terminate_org_unit(unitid):
    """Terminates an organisational unit from a specified date.

    .. :quickref: Unit; Terminate

    :statuscode 200: The termination succeeded.
    :statuscode 404: No such unit found.
    :statuscode 409: Validation failed, see below.

    :param unitid: The UUID of the organisational unit to be terminated.

    :<json object validity: The date on which the termination should happen,
        in ISO 8601.

    **Example Request**:

    .. sourcecode:: json

      {
        "validity": {
          "to": "2015-12-31"
        }
      }

    :returns: UUID of the terminated org unit

    **Validation**:

    Prior to terminating an organisational unit, all nested units and
    association details must be terminated. Should this not be the
    case, we return a :http:statuscode:`409`, and a response such as this:

    .. sourcecode:: json

      {
          "description": "cannot terminate unit with 1 active children",
          "error": true,
          "cause": "validation",
          "status": 400,

          "child_count": 1,
          "role_count": 0,
          "child_units": [
              {
                  "child_count": 0,
                  "name": "Afdeling for Fremtidshistorik",
                  "user_key": "frem",
                  "uuid": "04c78fc2-72d2-4d02-b55f-807af19eac48"
              }
          ]
      }

    """
    date = util.get_valid_to(flask.request.get_json())

    c = lora.Connector(effective_date=util.to_iso_date(date))

    validator.is_date_range_in_org_unit_range(
        unitid, date - util.MINIMAL_INTERVAL, date,
    )

    children = c.organisationenhed.paged_get(
        get_one_orgunit,
        overordnet=unitid,
        gyldighed='Aktiv',
        limit=5,
    )

    roles = c.organisationfunktion(
        tilknyttedeenheder=unitid,
        gyldighed='Aktiv',
    )

    if children['total'] or roles:
        exceptions.ErrorCodes.V_TERMINATE_UNIT_WITH_CHILDREN_OR_ROLES(
            child_units=children['items'],
            child_count=children['total'],
            role_count=len(roles),
        )

    obj_path = ('tilstande', 'organisationenhedgyldighed')
    val_inactive = {
        'gyldighed': 'Inaktiv',
        'virkning': common._create_virkning(date, 'infinity')
    }

    payload = util.set_obj_value(dict(), obj_path, [val_inactive])
    payload['note'] = 'Afslut enhed'

    c.organisationenhed.update(payload, unitid)

    return flask.jsonify(unitid)

    # TODO: Afkort adresser?


@blueprint.route('/ou/<uuid:unitid>/history/', methods=['GET'])
def get_org_unit_history(unitid):
    """
    Get the history of an org unit

    .. :quickref: Unit; Get history

    :param unitid: The UUID of the org unit

    **Example response**:

    :>jsonarr string from: When the change is active from
    :>jsonarr string to: When the change is active to
    :>jsonarr string action: The action performed
    :>jsonarr string life_cycle_code: The type of action performed
    :>jsonarr string user_ref: A reference to the user who made the change

    .. sourcecode:: json

      [
        {
          "from": "2018-02-21T13:25:24.391793+01:00",
          "to": "infinity",
          "action": "Afslut enhed",
          "life_cycle_code": "Rettet",
          "user_ref": "42c432e8-9c4a-11e6-9f62-873cf34a735f"
        },
        {
          "from": "2018-02-21T13:25:24.343010+01:00",
          "to": "2018-02-21T13:25:24.391793+01:00",
          "action": "Rediger organisationsenhed",
          "life_cycle_code": "Rettet",
          "user_ref": "42c432e8-9c4a-11e6-9f62-873cf34a735f"
        },
        {
          "from": "2018-02-21T13:25:24.271516+01:00",
          "to": "2018-02-21T13:25:24.343010+01:00",
          "action": "Rediger organisationsenhed",
          "life_cycle_code": "Rettet",
          "user_ref": "42c432e8-9c4a-11e6-9f62-873cf34a735f"
        },
        {
          "from": "2018-02-21T13:25:24.214514+01:00",
          "to": "2018-02-21T13:25:24.271516+01:00",
          "action": "Oprettet i MO",
          "life_cycle_code": "Opstaaet",
          "user_ref": "42c432e8-9c4a-11e6-9f62-873cf34a735f"
        }
      ]

    """

    c = lora.Connector()
    unit_registrations = c.organisationenhed.get(uuid=unitid,
                                                 registreretfra='-infinity',
                                                 registrerettil='infinity')

    if not unit_registrations:
        exceptions.ErrorCodes.E_ORG_UNIT_NOT_FOUND(org_unit_uuid=unitid)

    history_entries = list(map(common.convert_reg_to_history,
                               unit_registrations))

    return flask.jsonify(history_entries)
