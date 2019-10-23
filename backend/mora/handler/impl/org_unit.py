#
# Copyright (c) Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
import logging

from .. import reading
from ... import common
from ... import exceptions
from ... import mapping
from ... import util
from ...service import orgunit

ROLE_TYPE = "org_unit"

logger = logging.getLogger(__name__)


@reading.register(ROLE_TYPE)
class OrgUnitReader(reading.ReadingHandler):
    @classmethod
    def get(cls, c, search_fields):
        object_tuples = c.organisationenhed.get_all(**search_fields)
        return cls.get_obj_effects(c, object_tuples)

    @classmethod
    def get_from_type(cls, c, type, objid):
        if type != "ou":
            exceptions.ErrorCodes.E_INVALID_ROLE_TYPE()

        return cls.get(c, {"uuid": [objid]})

    @classmethod
    def get_effects(cls, c, obj, **params):

        relevant = {
            "attributter": ("organisationenhedegenskaber",),
            "relationer": ("enhedstype", "opgaver", "overordnet", "tilhoerer"),
            "tilstande": ("organisationenhedgyldighed",),
        }

        return c.organisationenhed.get_effects(obj, relevant, {}, **params)

    @classmethod
    def get_mo_object_from_effect(cls, effect, start, end, obj_id):
        c = common.get_connector()

        return orgunit.get_one_orgunit(
            c,
            obj_id,
            effect,
            details=orgunit.UnitDetails.FULL,
            validity={
                mapping.FROM: util.to_iso_date(start),
                mapping.TO: util.to_iso_date(end, is_end=True),
            },
        )
