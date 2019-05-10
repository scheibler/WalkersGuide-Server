#!/usr/bin/python
# -*- coding: utf-8 -*-

# some small helper functions

import gzip
import json
import sys

from subprocess import Popen, PIPE, STDOUT


def exit(message, prefix="Error in config file\n"):
    """Exit with a message and a return code indicating an error in the config
    file.
    This function doesn't return, it calls sys.exit.
    :param message: the message to print
    :type message: str
    :param prefix: the prefix to put in front of the message
    :type prefix: str
    :returns: does not return
    """
    print(prefix+message)
    sys.exit(1)


def zip_data(data):
    return gzip.compress(
            bytes(json.dumps(data), 'utf-8'))


def send_email(recipient, subject, body):
    send_email_process= Popen(
            ["mail", "-s", subject, recipient],
            stdin=PIPE, stdout=PIPE, stderr=STDOUT)
    send_email_process.communicate(input=bytes(body, encoding='utf8'))
    return send_email_process.wait()

