#
# Copyright (c) 2017, Magenta ApS
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import os
import unittest

import click

basedir = os.path.dirname(__file__)


def load_cli(app):
    @app.cli.command()
    @click.argument('command', required=False)
    def build(command=None):
        'Build the frontend application.'
        from subprocess import check_call, check_output

        base_dir = os.path.dirname(os.path.dirname(__file__))
        bin_dir = check_output(['npm', 'bin'], cwd=base_dir).decode().strip()

        check_call(['npm', 'install'], cwd=base_dir)
        check_call([os.path.join(bin_dir, 'grunt')] +
                   ([command] if command else []), cwd=base_dir)

    @app.cli.command(with_appcontext=False)
    @click.option('--verbose', '-v', count=True)
    @click.option('--quiet', '-q', is_flag=True)
    @click.option('--failfast/--no-failfast', '-f', default=False)
    @click.option('--buffer/--no-buffer', '-b/-B', default=True)
    @click.option('--minimox-dir')
    @click.option('--browser')
    @click.argument('tests', nargs=-1)
    def test(tests, quiet, verbose, failfast, buffer, minimox_dir, browser):
        verbosity = 0 if quiet else verbose + 1

        if minimox_dir:
            os.environ['MINIMOX_DIR'] = minimox_dir

        if browser:
            os.environ['BROWSER'] = browser

        loader = unittest.TestLoader()

        if tests:
            suite = loader.loadTestsFromNames(tests)
        else:
            suite = loader.discover(
                start_dir=os.path.join(basedir, '..', 'tests'),
                top_level_dir=os.path.join(basedir, '..'),
            )

        runner = unittest.TextTestRunner(verbosity=verbosity, buffer=buffer)
        runner.run(suite)
