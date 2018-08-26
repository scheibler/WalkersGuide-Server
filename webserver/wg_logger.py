#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, string, datetime

class WGLogger:
    def __init__(self, basic_folder, file_name, logging_allowed):
        valid_chars = "-_.%s%s" % (string.ascii_letters, string.digits)
        date = datetime.datetime.now()
        self.logging_allowed = logging_allowed
        # construct log folder
        self.log_folder_name = os.path.join(basic_folder, "%d" % date.year,
                "%02d" % date.month, "%02d" % date.day)
        # file name
        self.log_file_name = "%04d.%02d.%02d_%02d-%02d-%02d---%s.log" \
                % (date.year, date.month, date.day, date.hour, date.minute, date.second,
                        ''.join(c if c in valid_chars else '.' for c in file_name))
        # create log file
        self.append_to_log(file_name.replace(".", " ").replace("-", "  --  "))

    def append_to_log(self, data, print_on_screen = False):
        if self.logging_allowed:
            # create log folder if not present
            if not os.path.exists(self.log_folder_name):
                os.makedirs(self.log_folder_name)
            # construct full log file
            log_folder_and_file_name = os.path.join(
                    self.log_folder_name, self.log_file_name)
            # cut file name if it's too long
            if log_folder_and_file_name.__len__() >= os.pathconf(self.log_folder_name, 'PC_NAME_MAX'):
                log_folder_and_file_name = "%s.log" \
                        % log_folder_and_file_name[:os.pathconf(self.log_folder_name, 'PC_NAME_MAX')-10]
            # append to log file
            with open(log_folder_and_file_name, "a") as log_file:
                log_file.write("%s\n" % data)
            # print on stdout (optional)
            if print_on_screen:
                print data

