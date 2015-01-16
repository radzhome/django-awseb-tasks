# import json
# import os
# import uuid
#
# from django.conf import settings
# from django.core import mail
# from django.core.urlresolvers import reverse
# from django.test import TestCase

import os
from fabfile import aws


def test_libraries():
    try:
        import prettytable
    except ImportError:
        raise Exception("Prettytable not installed")
    try:
        import boto
    except ImportError:
        raise Exception("Boto not installed")
    try:
        import fabric
    except ImportError:
        raise Exception("Fabric not installed")
    try:
        import prettytable
    except ImportError:
        raise Exception("Prettytable not installed")
    print 'passed import test'


def check_credential_file_exist():
    home = os.path.expanduser("~")

    try:
        assert os.path.isfile(os.path.join(home, '.boto')) == 1
    except AssertionError:
        raise Exception("Boto credentials file cannot be found.")
    print 'passed boto credentails test'


def test_env_status():
    try:
        aws.status()
    except AssertionError:
        raise Exception("Failed to run status command.")
    print 'passed status task test'

if __name__ == '__main__':
    test_libraries()
    check_credential_file_exist()
    test_env_status()