#  -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2022-2023. Antonio Bulgheroni.
#  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
#  documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so, subject to the following conditions:
#  The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
#  Software.
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
#  WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
#  OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#  OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ----------------------------------------------------------------------------------------------------------------------

import ctypes
import logging
import sys

from autologbook import autocli, autogui, autotools

log = logging.getLogger()
autotools.add_logging_level('VIPDEBUG', logging.INFO - 5, )

# use this to catch all exceptions in the GUI
sys.excepthook = autotools.my_excepthook


def main(cli_args, prog):
    """
    Define main function to start the event loop.

    Returns
    -------
    None.

    """
    # get the cli args from the parser
    parser = autotools.main_parser()
    if prog:
        parser.prog = prog

    args = parser.parse_args(cli_args)

    # to set the icon on the window task bar
    myappid = u'ecjrc.autologook.gui.v1.0.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    if args.cli:
        autocli.main_cli(args)
    else:
        autogui.main_gui(args)
