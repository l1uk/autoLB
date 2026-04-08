# -*- coding: utf-8 -*-
"""
Created on Wed Jun 29 14:22:06 2022

@author: elog-admin
"""
# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2022-2023.  Antonio Bulgheroni.
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

import datetime
import logging
from pathlib import Path

import piexif

#
# LOGGING PARAMETERS
#
LEVELS = {'debug': logging.DEBUG,
          'vipdebug': logging.INFO - 5,
          'info': logging.INFO,
          'warn': logging.WARNING,
          'warning': logging.WARNING,
          'error': logging.ERROR,
          'critical': logging.CRITICAL}

#
# GENERAL
#
CUSTOMID_START = 1000
CUSTOMID_TIFFCODE = 37510
VEGA_TIFFCODE = 50431
VEGA_JPEG_ID_CODE = piexif.ExifIFD.UserComment
VERSION = '0.1.8'
THREAD_STATUS_UPDATE = 1000  # in ms
AUTO_SAVE_INTERVAL = 300000  # in ms
MAX_ATTACHMENTS = 50  # it is a limitation of elog
ELOG_PAGE_SIZE_LIMIT = 240000  # the real max is 250000, I kept a 10k as a safety margin.
#
# ELOG PARAMETERS
#
ELOG_USER = 'log-robot'
ELOG_PASSWORD = 'mTZtK2iFHhwqixkhJV0JkplSqMMu9ykWOhcNY/1WyL7'
ELOG_HOSTNAME = 'https://10.166.16.24'
ELOG_PORT = 8080
USE_SSL = True
MAX_AUTH_ERROR = 5
ELOG_TIMEOUT = 10  # seconds
ELOG_TIMEOUT_MAX_RETRY = 5
ELOG_TIMEOUT_WAIT = 5  # seconds
#
# EXTERNAL TOOLS
#
NOTEPAD_BEST = Path("C:\\Program Files\\Notepad++\\notepad++.exe")
ROBOCOPY_EXE = Path("C:\\Windows\\System32\\Robocopy.exe")
#
# WATCHDOGS
#
AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS = 5
AUTOLOGBOOK_WATCHDOG_WAIT_MIN = 1
AUTOLOGBOOK_WATCHDOG_WAIT_MAX = 5
AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT = 1
AUTOLOGBOOK_WATCHDOG_MIN_DELAY = 600  # it is used to be 45, increased to 600 to avoid useless server overload.
AUTOLOGBOOK_WATCHDOG_TIMEOUT = 0.5
#
# MIRRORING WATCHDOG
#
AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS = 2
AUTOLOGBOOK_MIRRORING_WAIT = 0.5
AUTOLOGBOOK_MIRRORING_TIMEOUT = 0.2
#
# IMAGESERVER
#
IMAGE_SERVER_BASE_PATH = Path('R:\\A226\\Results')
IMAGE_SERVER_ROOT_URL = 'https://10.166.16.24/micro'
IMAGE_SAMPLE_THUMB_MAX_WIDTH = 400
#
#
# FEI
#
FEI_AUTO_CALIBRATION = True
FEI_DATABAR_REMOVAL = False
#
# QUATTRO
#
IMAGE_NAVIGATION_MAX_WIDTH = 500
QUATTRO_LOGBOOK = 'Quattro-Analysis'
#
# VERSA
#
VERSA_LOGBOOK = 'Versa-Analysis'
#
# VEGA
#
VEGA_LOGBOOK = 'Vega-Analysis'
VEGA_AUTO_CALIBRATION = True
#
# XL40
#
XL40_AUTO_CALIBRATION = True
XL40GB_LOGBOOK = 'XL40-GB-Analysis'
XL40COLD_LOGBOOK = 'XL40-Cold-Analysis'
#
# DEFAULT GUI
#
DEFAULT_MICROSCOPE = 'Quattro'
DEFAULT_PROTOCOL_FOLDER = str(Path("C:\\Users\\elog-admin\\Documents\\src"))
DEFAULT_MIRRORING_FOLDER = str(Path('R:\\A226\\Results')) + '\\%s' % datetime.date.today().year
#
# PROTOCOL LIST
#
PROTOCOL_LIST_LOGBOOK = 'Microscopy-Protocol'
