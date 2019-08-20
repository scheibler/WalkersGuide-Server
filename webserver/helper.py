#!/usr/bin/python
# -*- coding: utf-8 -*-

# some small helper functions

import logging, logging.handlers
import gzip
import json
import sys


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


def send_email(subject, body):
    logger = logging.getLogger('email')
    logger.info(body, extra = {'email_subject' : subject})


class CustomSubjectSMTPHandler(logging.handlers.SMTPHandler):
    def getSubject(self, record):
        formatter = logging.Formatter(fmt=self.subject)
        return formatter.format(record)


class TTYLogFormatter(logging.Formatter):
    CHERRYPY_ACCESS = '[ACCESS] %(message)s'
    CHERRYPY_ERROR  = '[CHERRYPY] %(message)s'
    EMAIL   = '[Email] %(email_subject)s'
    DEFAULT = '[%(levelname)s] [%(filename)s, %(funcName)s, Line %(lineno)s] [%(asctime)s]\n%(message)s'
    def format(self, record):
        if record.name.startswith('cherrypy.access'):
            formatter = logging.Formatter(self.CHERRYPY_ACCESS)
        elif record.name.startswith('cherrypy.error'):
            formatter = logging.Formatter(self.CHERRYPY_ERROR)
        elif record.name == 'email':
            formatter = logging.Formatter(self.EMAIL)
        else:
            formatter = logging.Formatter(self.DEFAULT)
        return formatter.format(record)


class WebserverException(Exception):
    def __init__(self, return_code, message=None):
        self.return_code = return_code
        self.message = message
    def __str__(self):
        if self.message:
            return repr(
                    'rc={}, msg={}'.format(self.return_code, self.message))
        return repr(
                'rc={}'.format(self.return_code))

