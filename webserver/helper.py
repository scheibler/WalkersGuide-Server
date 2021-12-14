#!/usr/bin/python
# -*- coding: utf-8 -*-

# some small helper functions

import logging, logging.handlers
import gzip
import json
import sys

from typing import List


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


def pretty_print_table(table: List[List[str]], justify: str = "L", column_separator: str = " ") -> str:
    """Converts a list of lists into a string formatted like a table
    with spaces separating fields and newlines separating rows"""
    # support for multiline columns
    line_break_table = []
    for row in table:
        # get line break count
        most_line_breaks_in_row = 0
        for col in row:
            if str(col).count("\n") > most_line_breaks_in_row:
                most_line_breaks_in_row = col.count("\n")
        # fill table rows
        for index in range(0, most_line_breaks_in_row+1):
            line_break_row = []
            for col in row:
                try:
                    line_break_row.append(str(col).split("\n")[index])
                except IndexError:
                    line_break_row.append("")
            line_break_table.append(line_break_row)
    # replace table variable
    table = line_break_table
    # get width for every column
    column_widths = [0] * len(table[0])
    offset = 3
    for row in table:
        for index, col in enumerate(row):
            width = len(str(col))
            if width > column_widths[index]:
                column_widths[index] = width
    table_row_list = []
    for row in table:
        single_row_list = []
        for col_index, col in enumerate(row):
            if justify == "R":  # justify right
                formated_column = str(col).rjust(column_widths[col_index] +
                                                 offset)
            elif justify == "L":  # justify left
                formated_column = str(col).ljust(column_widths[col_index] +
                                                 offset)
            elif justify == "C":  # justify center
                formated_column = str(col).center(column_widths[col_index] +
                                                  offset)
            single_row_list.append(formated_column)
        table_row_list.append(column_separator.join(single_row_list))
    return '\n'.join(table_row_list)


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

