# -*- coding: utf-8 -*-
"""
Created on Thu May 19 11:26:27 2022

@author: elog-admin
"""

#  Copyright (c) 2022.  Antonio Bulgheroni.
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
#  documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
#  Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
#  WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
#  OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#  OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#
#  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
#   documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
#   rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#   permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
#
#
#
#
#
import logging
import sys

import urllib3

from autologbook import autoconfig

urllib3.disable_warnings()

log = logging.getLogger('__main__')


def main_cli(args):
    if log.hasHandlers():
        for h in log.handlers:
            log.removeHandler(h)
    loglevel = autoconfig.LEVELS.get(args.loglevel.lower())
    log.setLevel(level=loglevel)
    cli_handler = logging.StreamHandler(sys.stdout)
    fs = '[%(asctime)s] %(threadName)-15s %(levelname)-7s %(message)s'
    formatter = logging.Formatter(fs, datefmt='%Y%m%d-%H:%M:%S')
    cli_handler.setFormatter(formatter)
    log.addHandler(cli_handler)
    log.info('Welcome to the autologbook CLI!')


# def main():
#     parser = argparse.ArgumentParser(
#         description='Start the automatic watchdog for logbook generation')
#     parser.add_argument('path', help='The path to be monitored. It must be on the shared folder R:\\A226\\Results',
#                         type=Path)
#     parser.add_argument('-l', '--log', type=int, nargs=1, dest='loglevel', choices=range(0, 50, 10), default='20',
#                         help='The verbosity of the logging messages. 10=Debug --> 50=Error. Default=20')
#     parser.add_argument('-m', '--microscope', type=str, nargs=1, dest='microscope', choices={'quattro', 'versa'},
#                         default='quattro', help='The type of microscope')
#     parser.add_argument('--host', type=str, nargs=1, dest='elog_hostname', default='https://10.166.16.24/',
#                         help='The FQDN of the elog server. Leave it to default if you don\'t know it')
#     parser.add_argument('--port', type=int, nargs=1, dest='elog_port', default=8080,
#                         help='The port at which the elog is listening. Leave it to default if you don\'t know it')

#     args = parser.parse_args()

#     logging.basicConfig(format="%(levelname)s: %(message)s",
#                         level=args.loglevel)

#     path = args.path

#     elog_user = 'log-robot'
#     elog_password = 'IchBinRoboter'

#     if args.microscope.lower() == 'quattro':
#         autolog = autologbook.QuattroELOGProtocol(
#             path=path,
#             elog_hostname=args.elog_hostname,
#             elog_port=args.elog_port,
#             elog_user=elog_user,
#             elog_password=elog_password)
#         autologbook.HTMLObject.reset_html_content()
#         autologbookEventHandler = autologbook.QuattroELOGProtocolEventHandler(
#             autolog)
#     else:
#         logging.error(
#             'Sorry for this microscope we still don\'t have an automatic protocol generator')
#         return

#     observer = watchdog.observers.Observer()
#     observer.schedule(autologbookEventHandler, path=path, recursive=True)
#     autologbookEventHandler.process_already_existing_items()
#     observer.start()

#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         observer.stop()
#     observer.join()
#     autologbook.HTMLObject.reset_html_content()
#     autolog.generate_html()
#     autolog.post_elog_message(skip_attachments=False)


# if __name__ == '__main__':
#     main()
