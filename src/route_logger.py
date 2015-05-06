#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, string, datetime
from config import Config

class RouteLogger:
    def __init__(self, sub_folder, file_name):
        valid_chars = "-_.%s%s" % (string.ascii_letters, string.digits)
        date = datetime.datetime.now()
        log_folder = os.path.join( Config().get_param("logs_folder"), sub_folder,
                "%d" % date.year, "%02d" % date.month, "%02d" % date.day)
        if os.path.exists(log_folder) == False:
            os.makedirs(log_folder)
        self.file_name = os.path.join( log_folder, "%d.%02d.%02d_%02d-%02d-%02d---%s.log" % (date.year, date.month,
                date.day, date.hour, date.minute, date.second,
                ''.join(c if c in valid_chars else '.' for c in file_name) ))
        # cut file name if it's too long
        if self.file_name.__len__() >= os.pathconf(log_folder, 'PC_NAME_MAX'):
            self.file_name = "%s.log" \
                    % self.file_name[:os.pathconf(log_folder, 'PC_NAME_MAX')-10]
        self.append_to_log(file_name.replace(".", " ").replace("-", "  --  "))

    def append_to_log(self, data, print_on_screen = False):
        file = open(self.file_name, "a")
        file.write("%s\n" % data)
        file.close()
        if print_on_screen:
            print data

