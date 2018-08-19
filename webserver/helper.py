#!/usr/bin/python
# -*- coding: utf-8 -*-

# some small helper functions

import gzip
import json
import StringIO
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


def convert_dict_values_to_utf8(input):
    if isinstance(input, dict):
        return {convert_dict_values_to_utf8(key): convert_dict_values_to_utf8(value) for key, value in input.iteritems()}
    elif isinstance(input, list):
        return [ convert_dict_values_to_utf8(element) for element in input]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input


def zip_data(data):
    json_string = json.dumps(data, encoding="utf-8")
    out = StringIO.StringIO()
    with gzip.GzipFile(fileobj=out, mode="w") as f:
        f.write(json_string)
    return out.getvalue()


def send_email(recipient, subject, body):
    send_email_process= Popen(
            ["mail", "-s", subject, recipient],
            stdin=PIPE, stdout=PIPE, stderr=STDOUT)
    send_email_process.communicate(input=body)
    return send_email_process.wait()

