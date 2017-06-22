#
# Copyright (c) 2017, Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import functools
import os
import unittest
import urllib

import requests_mock

from .. import util
from mora import app


class AddrTests(util.TestCase):
    '''Address conversion and autocomplete tests'''

    def create_app(self):
        app.app.config['DEBUG'] = False
        app.app.config['TESTING'] = True
        app.app.config['LIVESERVER_PORT'] = 0
        app.app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False

        return app.app

    @requests_mock.mock()
    def test_fetch_address_invalid_args(self, m):
        self.assertRequestFails('/addressws/geographical-location', 501)
        self.assertRequestFails('/addressws/geographical-location?asd', 501)
        self.assertRequestFails('/addressws/geographical-location?asd=42', 501)
        self.assertRequestFails('/addressws/geographical-location?vejnavn=',
                                501)

    @util.with_mock_fixture('dawa.json')
    def test_autocomplete_address(self, mock):
        aarhus_road = urllib.parse.quote_plus('Åbogade 15')

        self.assertRequestResponse(
            '/addressws/geographical-location?vejnavn=' + aarhus_road,
            util.get_fixture('addressws/aabogade.json'),
        )

        self.assertRequestResponse(
            '/addressws/geographical-location?'
            'local=456362c4-0ee4-4e5e-a72c-751239745e62'
            '&vejnavn=' + aarhus_road,
            util.get_fixture('addressws/aabogade.json'),
        )

        cph_road = urllib.parse.quote_plus('Pilestræde 43')

        self.assertRequestResponse(
            '/addressws/geographical-location?vejnavn=' + cph_road,
            util.get_fixture('addressws/pilestraede.json'),
        )

        self.assertRequestResponse(
            '/addressws/geographical-location?'
            'local=456362c4-0ee4-4e5e-a72c-751239745e62'
            '&vejnavn=' + cph_road,
            []
        )