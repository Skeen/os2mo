#
# Copyright (c) 2017, Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import atexit
import json
import os
import select
import signal
import socket
import subprocess
import unittest

import flask_testing

from mora import lora, app

TESTS_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.dirname(TESTS_DIR)
FIXTURE_DIR = os.path.join(TESTS_DIR, 'fixtures')


def jsonfile_to_dict(path):
    """
    Reads JSON from resources folder and converts to Python dictionary
    :param path: path to json resource
    :return: dictionary corresponding to the resource JSON
    """
    with open(path) as f:
        return json.load(f)


def get_unused_port():
    '''Obtain an unused port suitable for connecting to a server.

    '''
    with socket.socket() as sock:
        sock.bind(('', 0))
        return sock.getsockname()[1]


def load_fixture(path, fixture_name, uuid):
    '''Load a fixture, i.e. a JSON file with the 'fixtures' directory,
    into LoRA at the given path & UUID.

    '''
    with open(os.path.join(FIXTURE_DIR, fixture_name)) as fp:
        data = json.load(fp)

    return lora.create(path, data, uuid)


def load_sample_structures():
    '''Inject our test data into LoRA.

    '''
    load_fixture(
        'klassifikation/klasse',
        'create_klasse_fakultet.json',
        '4311e351-6a3c-4e7e-ae60-8a3b2938fbd6',
    )
    load_fixture(
        'klassifikation/klasse',
        'create_klasse_afdeling.json',
        '32547559-cfc1-4d97-94c6-70b192eff825',
    )
    load_fixture(
        'klassifikation/klasse',
        'create_klasse_institut.json',
        'ca76a441-6226-404f-88a9-31e02e420e52',
    )
    load_fixture(
        'organisation/organisation',
        'create_organisation_AU.json',
        '456362c4-0ee4-4e5e-a72c-751239745e62',
    )

    for unitkey, unitid in {
        'root': '79ae5c4a-b604-48e8-a9a6-94fdf42e21e6',
        'hum': '9d07123e-47ac-4a9a-88c8-da82e3a4bc9e',
        'samf': 'b688513d-11f7-4efc-b679-ab082a2055d0',
        'root': '2874e1dc-85e6-4269-823a-e1125484dfd3',
        'fil': '85715fc7-925d-401b-822d-467eb4b163b6',
        'hist': 'da77153e-30f3-4dc2-a611-ee912a28d8aa',
        'frem': '04c78fc2-72d2-4d02-b55f-807af19eac48',
    }.items():
        load_fixture(
            'organisation/organisationenhed',
            'create_organisationenhed_{}.json'.format(unitkey),
            unitid,
        )


class LoRATestCase(flask_testing.TestCase):
    '''Base class for LoRA testcases; the test creates an empty LoRA
    instance, and deletes all objects between runs.
    '''

    maxDiff = None

    def create_app(self):
        app.app.config['TESTING'] = True
        app.app.config['LIVESERVER_PORT'] = 0
        app.app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False
        return app.app

    def load_sample_structures(self):
        self.assertIsNone(self.minimox.poll(), 'LoRA is not running!')
        load_sample_structures()

    @unittest.skipUnless('MINIMOX_DIR' in os.environ, 'MINIMOX_DIR not set!')
    @classmethod
    def setUpClass(cls):
        port = get_unused_port()
        MINIMOX_DIR = os.getenv('MINIMOX_DIR')

        # Start a 'minimox' instance -- which is LoRA with the testing
        # tweaks in the 'minimox' branch. We use a separate process
        # since LoRA doesn't support Python 3, yet; the main downside
        # to this is that we have to take measures not to leak that
        # process.
        cls.minimox = subprocess.Popen(
            [os.path.join(MINIMOX_DIR, 'run-mox.py'), str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=MINIMOX_DIR,
        )

        cls._orig_lora = lora.LORA_URL
        lora.LORA_URL = 'http://localhost:{}/'.format(port)

        # This is the first such measure: if the interpreter abruptly
        # exits for some reason, tell the subprocess to exit as well
        atexit.register(cls.minimox.send_signal, signal.SIGINT)

        # wait for the process to launch and print out its 'Listening...' line
        cls.minimox.stdout.readline()

        self.assertIsNone(self.minimox.poll(), 'LoRA startup failed!')

    @classmethod
    def tearDownClass(cls):
        # first, we're cleaning up now, so clear the exit handler
        atexit.unregister(cls.minimox.send_signal)

        # second, terminate our child process
        cls.minimox.send_signal(signal.SIGINT)

        # read output from the server process
        print(cls.minimox.stdout.read())

        lora.LORA_URL = cls._orig_lora

    def tearDown(self):
        # delete all objects in the test instance; this does 'leak'
        # information in that they continue to exist as registrations,
        # but it's faster than recreating the database fully
        for t in lora.organisation, lora.organisationenhed, lora.klasse:
            for objid in t(bvn='%'):
                t.delete(objid)

        # our test-runner enforces buffering of stdout, so we can
        # safely print out the process output; this ensures any
        # exceptions, etc. get reported to the user/test-runner
        while select.select((self.minimox.stdout,), (), (), 0)[0]:
            print(self.minimox.stdout.readline(), end='')

    def assertRequestResponse(self, path, expected, message=None):
        '''Issue a request and assert that it succeeds (and does not
        redirect) and yields the expected output.
        '''
        message = message or 'request {!r} failed'.format(path)

        r = self.client.get(path)

        self.assertLess(r.status_code, 300, message)
        self.assertGreaterEqual(r.status_code, 200, message)
        self.assertEqual(expected, r.json, message)


if __name__ == '__main__':
    # allow running this script with 'python -m'
    load_sample_structures()