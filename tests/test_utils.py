#
# Copyright (c) 2017, Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import unittest

import flask
from iso8601 import iso8601

from mora import util


class TestUtils(unittest.TestCase):

    def test_to_lora_time(self):
        self.assertEqual(util.to_lora_time('31-12-2017'),
                         '2017-12-31T00:00:00+01:00')
        self.assertEqual(util.to_lora_time('infinity'), 'infinity')
        self.assertEqual(util.to_lora_time('-infinity'), '-infinity')

        # the frontend doesn't escape the 'plus' in ISO 8601 dates, so
        # we get it as a space
        self.assertEqual(util.to_lora_time('2017-07-31T22:00:00 00:00'),
                         '2017-07-31T22:00:00+00:00')

        # 15 is not a valid month
        self.assertRaises(ValueError, util.to_lora_time,
                          '1999-15-11 00:00:00+01')

    def test_to_frontend_time(self):
        self.assertEqual(util.to_frontend_time('2017-12-31 00:00:00+01'),
                         '31-12-2017')
        self.assertEqual(util.to_frontend_time('infinity'), 'infinity')
        self.assertEqual(util.to_frontend_time('-infinity'), '-infinity')

    def test_splitlist(self):
        self.assertEqual(
            list(util.splitlist([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 3)),
            [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10]],
        )
        self.assertEqual(
            list(util.splitlist([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 4)),
            [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]],
        )
        self.assertEqual(
            list(util.splitlist([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 11)),
            [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
        )
        self.assertRaises(ValueError,
                          list, util.splitlist([], 0))
        self.assertRaises(ValueError,
                          list, util.splitlist([], -1))
        self.assertRaises(TypeError,
                          list, util.splitlist([], 'horse'))

    def test_is_uuid(self):
        self.assertTrue(util.is_uuid('00000000-0000-0000-0000-000000000000'))
        self.assertFalse(util.is_uuid('42'))
        self.assertFalse(util.is_uuid(None))


class TestAppUtils(unittest.TestCase):
    def test_restrictargs(self):
        app = flask.Flask(__name__)

        @app.route('/')
        @util.restrictargs('hest')
        def root():
            return 'Hest!'

        client = app.test_client()

        with app.app_context():
            self.assertEquals(client.get('/').status,
                              '200 OK')
            self.assertEquals(client.get('/?hest=').status,
                              '200 OK')
            self.assertEquals(client.get('/?hest=42').status,
                              '200 OK')
            self.assertEquals(client.get('/?HeSt=42').status,
                              '200 OK')
            self.assertEquals(client.get('/?fest=').status,
                              '200 OK')
            self.assertEquals(client.get('/?fest=42').status,
                              '501 NOT IMPLEMENTED')
