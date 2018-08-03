#!/usr/bin/python
# -*- coding: utf-8 -*-

# some small helper functions
import StringIO, gzip, json, smtplib
from config import Config
from email.mime.text import MIMEText
from email.header import Header


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


def send_email(subject, body):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = Config().get_param("sender_mail_server_login")
    msg['To'] = Config().get_param("recipient_address")
    s = smtplib.SMTP(Config().get_param("sender_mail_server_address"), Config().get_param("sender_mail_server_port"))
    try:
        s.ehlo()
        s.starttls()
        s.login(Config().get_param("sender_mail_server_login"), Config().get_param("sender_mail_server_password"))
        s.sendmail(msg['From'], msg['To'], msg.as_string())
    finally:
        s.quit()

