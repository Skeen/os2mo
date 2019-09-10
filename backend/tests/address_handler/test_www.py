#
# Copyright (c) Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from mora import exceptions
from mora.service.address_handler import www
from .. import util


class WWWAddressHandlerTests(util.TestCase):
    handler = www.WWWAddressHandler

    def test_from_effect(self):
        # Arrange
        value = 'http://www.test.org/'

        effect = {
            'relationer': {
                'adresser': [{
                    'urn': 'urn:magenta.dk:www:{}'.format(value)
                }]
            }
        }

        address_handler = self.handler.from_effect(effect)

        # Act
        actual_value = address_handler.value

        # Assert
        self.assertEqual(value, actual_value)

    def test_from_request(self):
        # Arrange
        value = 'http://www.test.org/'

        request = {
            'value': value
        }
        address_handler = self.handler.from_request(request)

        # Act
        actual_value = address_handler.value

        # Assert
        self.assertEqual(value, actual_value)

    def test_get_mo_address(self):
        # Arrange
        value = 'http://www.test.org/'
        address_handler = self.handler(value)

        expected = {
            'href': None,
            'name': value,
            'value': value
        }

        # Act
        actual = address_handler.get_mo_address_and_properties()

        # Assert
        self.assertEqual(expected, actual)

    def test_get_lora_address(self):
        # Arrange
        value = 'http://www.test.org/'
        address_handler = self.handler(value)

        expected = {
            'objekttype': 'WWW',
            'urn': 'urn:magenta.dk:www:http://www.test.org/'
        }

        # Act
        actual = address_handler.get_lora_address()

        # Assert
        self.assertEqual(expected, actual)

    def test_get_lora_properties(self):
        # Arrange
        value = 'http://www.test.org/'
        address_handler = self.handler(value)

        expected = []

        # Act
        actual = address_handler.get_lora_properties()

        # Assert
        self.assertEqual(expected, actual)

    def test_validation_fails_on_invalid_value(self):
        # Arrange
        value = '@$@#$@#$'  # Not a valid URL

        # Act & Assert
        with self.assertRaises(exceptions.HTTPException):
            self.handler.validate_value(value)

    def test_validation_succeeds_on_correct_values(self):
        # Arrange
        valid_values = [
            'http://www.test.com',
            'https://www.test.com',
            'http://subdomain.hej.com/welcome/to/test.html',
        ]

        # Act & Assert
        for value in valid_values:
            # Shouldn't raise exception
            self.handler.validate_value(value)

    def test_validation_succeeds_with_force(self):
        # Arrange
        value = 'GARBAGEGARBAGE'  # Not a valid URL

        # Act & Assert
        with self.create_app().test_request_context('?force=1'):
            self.handler.validate_value(value)