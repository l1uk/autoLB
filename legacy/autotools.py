# -*- coding: utf-8 -*-
"""Generic tools for the autologbook

Created on Tue Jun 28 11:06:58 2022

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

from __future__ import annotations

import argparse
import configparser
import logging
import math
import os
import re
from configparser import ConfigParser
from datetime import datetime, timezone
from enum import Enum, Flag, IntEnum, auto
from pathlib import Path

import elog
import piexif
import PIL.TiffImagePlugin
import yaml
from dateutil import tz
from PIL.TiffImagePlugin import ImageFileDirectory_v2
from PyQt5 import QtCore

from autologbook import autoconfig, autoerror
from autologbook.elog_interface import ELOGConnectionParameters, elog_handle_factory
from autologbook.protocol_editor_models import ElementType

log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


def init(config):
    """
    Initialize module wide global variables.

    Parameters
    ----------
    config : configparser object or string corresponding to a configuration file
        The configuration object

    Returns
    -------
    None.

    """
    _config = configparser.ConfigParser()
    if isinstance(config, configparser.ConfigParser):
        _config = config
    elif isinstance(config, str):
        if Path(config).exists() and Path(config).is_file():
            _config.read(config)
        else:
            raise ValueError('Unable to initialize the autowatch-gui module because '
                             + 'the provided configuration file (%s) doesn\'t exist' %
                             config)
    elif isinstance(config, Path):
        if config.exists() and config.is_file():
            _config.read(str(config))
        else:
            raise ValueError(
                'Unable to initialize the autowatch-gui module because the provided '
                + 'configuration file (%s) doesn\'t exist' % config)
    else:
        raise TypeError(
            'Unable to initialize the autowatch-gui module because of wrong config file')

    # ELOG section
    autoconfig.ELOG_USER = _config.get(
        'elog', 'elog_user', fallback=autoconfig.ELOG_USER)
    autoconfig.ELOG_PASSWORD = _config.get(
        'elog', 'elog_password', fallback=autoconfig.ELOG_PASSWORD)
    autoconfig.ELOG_HOSTNAME = _config.get(
        'elog', 'elog_hostname', fallback=autoconfig.ELOG_HOSTNAME)
    autoconfig.ELOG_PORT = _config.getint(
        'elog', 'elog_port', fallback=autoconfig.ELOG_PORT)
    autoconfig.USE_SSL = _config.getboolean(
        'elog', 'use_ssl', fallback=autoconfig.USE_SSL)
    autoconfig.MAX_AUTH_ERROR = _config.getint(
        'elog', 'max_auth_error', fallback=autoconfig.MAX_AUTH_ERROR)

    autoconfig.ELOG_TIMEOUT = _config.getfloat(
        'elog', 'elog_timeout', fallback=autoconfig.ELOG_TIMEOUT)
    autoconfig.ELOG_TIMEOUT_MAX_RETRY = _config.getint('elog', 'elog_timeout_max_retry',
                                                       fallback=autoconfig.ELOG_TIMEOUT_MAX_RETRY)
    autoconfig.ELOG_TIMEOUT_WAIT = _config.getfloat(
        'elog', 'elog_timeout_wait', fallback=autoconfig.ELOG_TIMEOUT_WAIT)

    autoconfig.PROTOCOL_LIST_LOGBOOK = _config.get('elog', 'microscopy_protocol_list',
                                                   fallback=autoconfig.PROTOCOL_LIST_LOGBOOK)

    # AUTOLOGBOOK WATCHDOG
    autoconfig.AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS = _config.getint('Autologbook watchdog', 'max_attempts',
                                                                  fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS)
    autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MIN = _config.getfloat('Autologbook watchdog', 'wait_min',
                                                                fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MIN)
    autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MAX = _config.getfloat('Autologbook watchdog', 'wait_max',
                                                                fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MAX)
    autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT = \
        _config.getfloat('Autologbook watchdog', 'wait_increment',
                         fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT)
    autoconfig.AUTOLOGBOOK_WATCHDOG_MIN_DELAY = \
        _config.getfloat('Autologbook watchdog', 'minimum delay between ELOG post',
                         fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_MIN_DELAY)
    autoconfig.AUTOLOGBOOK_WATCHDOG_TIMEOUT = _config.getfloat('Autologbook watchdog', 'observer_timeout',
                                                               fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_TIMEOUT)

    # MIRRORING WATCHDOG
    autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS = \
        _config.getint('Mirroring watchdog', 'max_attempts',
                       fallback=autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS)
    autoconfig.AUTOLOGBOOK_MIRRORING_WAIT = _config.getfloat(
        'Mirroring watchdog', 'wait', fallback=autoconfig.AUTOLOGBOOK_MIRRORING_WAIT)
    autoconfig.AUTOLOGBOOK_MIRRORING_TIMEOUT = _config.getfloat('Mirroring watchdog', 'observer_timeout',
                                                                fallback=autoconfig.AUTOLOGBOOK_MIRRORING_TIMEOUT)

    # IMAGE SERVER
    autoconfig.IMAGE_SERVER_BASE_PATH = _config.get(
        'Image_server', 'base_path', fallback=autoconfig.IMAGE_SERVER_BASE_PATH)
    autoconfig.IMAGE_SERVER_ROOT_URL = _config.get(
        'Image_server', 'server_root', fallback=autoconfig.IMAGE_SERVER_ROOT_URL)
    autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH = _config.getint(
        'Image_server', 'image_thumb_width', fallback=autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH)
    autoconfig.CUSTOMID_START = _config.getint(
        'Image_server', 'custom_id_start', fallback=autoconfig.CUSTOMID_START)
    autoconfig.CUSTOMID_TIFFCODE = _config.getint(
        'Image_server', 'tiff_tag_code', fallback=autoconfig.CUSTOMID_TIFFCODE)

    # FEI
    autoconfig.FEI_AUTO_CALIBRATION = _config.getboolean(
        'FEI', 'auto_calibration', fallback=autoconfig.FEI_AUTO_CALIBRATION)
    autoconfig.FEI_DATABAR_REMOVAL = _config.getboolean(
        'FEI', 'databar_removal', fallback=autoconfig.FEI_DATABAR_REMOVAL)

    # Quattro Specific
    autoconfig.IMAGE_NAVIGATION_MAX_WIDTH = _config.getint(
        'Quattro', 'image_navcam_width', fallback=autoconfig.IMAGE_NAVIGATION_MAX_WIDTH)
    autoconfig.QUATTRO_LOGBOOK = _config.get('Quattro', 'logbook', fallback=autoconfig.QUATTRO_LOGBOOK)

    # Versa Specific
    autoconfig.VERSA_LOGBOOK = _config.get('Versa', 'logbook', fallback=autoconfig.VERSA_LOGBOOK)

    # VEGA Specific
    autoconfig.VEGA_LOGBOOK = _config.get('Vega', 'logbook', fallback=autoconfig.VEGA_LOGBOOK)
    autoconfig.VEGA_AUTO_CALIBRATION = _config.getboolean('Vega', 'auto_calibration',
                                                          fallback=autoconfig.VEGA_AUTO_CALIBRATION)

    # XL40 specific
    autoconfig.XL40_AUTO_CALIBRATION = _config.get('XL40', 'auto_calibration',
                                                   fallback=autoconfig.XL40_AUTO_CALIBRATION)
    autoconfig.XL40GB_LOGBOOK = _config.get('XL40-GB', 'logbook', fallback=autoconfig.XL40GB_LOGBOOK)
    autoconfig.XL40COLD_LOGBOOK = _config.get('XL40-Cold', 'logbook', fallback=autoconfig.XL40COLD_LOGBOOK)

    # GUI defaults
    autoconfig.DEFAULT_MICROSCOPE = _config.get('GUI_DEFAULT', 'default_microscope',
                                                fallback=autoconfig.DEFAULT_MICROSCOPE)
    autoconfig.DEFAULT_PROTOCOL_FOLDER = _config.get('GUI_DEFAULT', 'default_protocol_folder',
                                                     fallback=autoconfig.DEFAULT_PROTOCOL_FOLDER)
    autoconfig.DEFAULT_MIRRORING_FOLDER = _config.get('GUI_DEFAULT', 'default_mirroring_folder',
                                                      fallback=autoconfig.DEFAULT_MIRRORING_FOLDER)

    elog_handle_factory.set_connection_parameters(ELOGConnectionParameters.from_config_module())


def generate_default_conf():
    """
    Generate a default configuration object.

    Returns
    -------
    None.

    """
    config = configparser.ConfigParser(allow_no_value=True)
    config.add_section('elog')
    config['elog'] = {
        'elog_user': 'log-robot',
        'elog_password': encrypt_pass('IchBinRoboter'),
        'elog_hostname': 'https://10.166.16.24',
        'elog_port': '8080',
        'use_ssl': True,
        'use_encrypt_pwd': True,
        'max_auth_error': 5,
        'elog_timeout': 10,
        'elog_timeout_max_retry': 5,
        'elog_timeout_wait': 5,
        'microscopy_protocol_list': 'Microscopy-Protocol'
    }

    config['Quattro'] = {
        'logbook': 'Quattro-Analysis',
        'image_navcam_width': '500'
    }
    config['Versa'] = {
        'logbook': 'Versa-Analysis'
    }

    config['Autologbook watchdog'] = {
        'max_attempts': '5',
        'wait_min': '1',
        'wait_max': '5',
        'wait_increment': '1',
        'minimum delay between ELOG post': '600',
        'observer_timeout': 0.5
    }
    config['Mirroring watchdog'] = {
        'max_attempts': '2',
        'wait': '0.5',
        'observer_timeout': 0.2
    }
    config['Image_server'] = {
        'base_path': 'R:\\A226\\Results',
        'server_root': 'https://10.166.16.24/micro',
        'image_thumb_width': 400,
        'custom_id_start': 1000,
        'tiff_tag_code': 37510
    }
    config['FEI'] = {
        'auto_calibration': True,
        'databar_removal': False
    }
    default_mirroring_folder = Path(f'R:\\A226\\Results\\{datetime.now():%Y}')
    config['GUI_DEFAULT'] = {
        'default_microscope': 'Quattro',
        'default_protocol_folder': str(Path("C:\\Users\\elog-admin\\Documents\\src")),
        'default_mirroring_folder': str(default_mirroring_folder),
    }
    config['Vega'] = {
        'logbook': 'Vega-Analysis',
        'auto_calibration': True
    }
    config['XL40'] = {
        'auto_calibration': True
    }
    config['XL40-GB'] = {
        'logbook': 'XL40-GB-Analysis',
    }
    config['XL40-Cold'] = {
        'logbook': 'XL40-Cold-Analysis',
    }

    return config


def safe_configread(conffile):
    """
    Read the configuration file in a safe manner.

    This function is very useful to read in configuration file checking that
    all the relevant sections and options are there.

    The configuration file is read with the standard configparser.read method
    and a configuration object with all default sections and options is
    generated.

    The two configuration objects are compared and if a section in the read
    file is missing, then it is taken from the default.

    If any addition (section or option) was requested than the integrated
    configuration file is saved to the input file so that the same issue should
    not happen anymore.

    Parameters
    ----------
    conffile : path-like or string
        The filename of the configuration file to be read.

    Returns
    -------
    config : configparser.ConfigParser
        A ConfigParser object containing all sections and options required.

    """
    config = configparser.ConfigParser()
    config.read(conffile)

    conffile_needs_updates = False

    if not config.has_section('elog'):
        # very likely this is not an auto configuration file
        raise autoerror.NotAValidConfigurationFile(
            f'File {conffile} is not a valid configuration file.')

    # check if it is an old configuration file with plain text password
    if not config.has_option('elog', 'use_encrypt_pwd'):
        if not config.has_option('elog', 'elog_password'):
            config.set('elog', 'elog_password', encrypt_pass(
                config.get('elog', 'elog_password', fallback=' ')))
        conffile_needs_updates = True

    # now we must check that we have everything
    default_config = generate_default_conf()
    for section in default_config.sections():
        if not config.has_section(section):
            config.add_section(section)
            conffile_needs_updates = True
            log.info('Section %s is missing from configuration file %s.'
                     ' The default values will be used and the file updated' %
                     (section, conffile))
        for option in default_config.options(section):
            if not config.has_option(section, option):
                config.set(section, option, default_config[section][option])
                conffile_needs_updates = True
                log.info('Option %s from section %s is missing. The default value will be used and the file update' %
                         (option, section))

    if not config.getboolean('elog', 'use_encrypt_pwd'):
        # it looks like the user changed manually the configuration file introducing a
        # plain text password.
        # we need to hash the password and update the configuration file
        config['elog']['use_encrypt_pwd'] = "True"
        config['elog']['elog_password'] = encrypt_pass(
            config['elog']['elog_password'])
        conffile_needs_updates = True

    if conffile_needs_updates:
        write_conffile(config, conffile)

    return config


def write_default_conffile(filename='autolog-conf.ini'):
    """
    Write the default configuration object to a file.

    Parameters
    ----------
    filename : path-like object, optional
        The filename for the configuration file.
        The default is 'autolog-conf.ini'.

    Returns
    -------
    None.

    """
    write_conffile(generate_default_conf(), filename)


def write_conffile(config_object, filename):
    """
    Write a configuration object to a file.

    Parameters
    ----------
    config_object : ConfigParser
        The configuration dictionary to be dumped into a file.
    filename : str or path-like
        The output file name

    Returns
    -------
    None.

    """
    if not isinstance(config_object, configparser.ConfigParser):
        raise TypeError('Invalid configuration object')

    message = ('###  AUTOLOGBOOK CONFIGURATION FILE.\n'
               f'# Generated on {datetime.now():%Y-%m-%d %H:%M:%S}\n'
               f'# Autologbook version v{autoconfig.VERSION}\n'
               '# \n'
               '## IMPORTANT NOTE ABOUT PASSWORDS:\n'
               '# \n'
               '# If you need to change the password in this configuration file, just\n'
               '# enter the plain text password in the password field and set use_encrypt_pwd to False.\n'
               '# The next time that autologook is executed the plain text password will be hashed \n'
               '# and this configuration file will be updated with the hashed value for your security.\n'
               '# \n\n')

    with open(filename, 'w') as configfile:
        configfile.write(message)
        config_object.write(configfile)


def parents_list(actual_path, base_path):
    """
    Generate the parents list of a given image.

    This tool is used to generate of a list of parents pairs.
    Let's assume you are adding a new image with the following path:
        actual_path = R:/A226/Results/2022/123 - proj - resp/SampleA/SubSampleB/SubSampleC/image.tiff
    and that the protocol folder is located at:
        base_path = R:/A226/Results/2022/123 - proj - resp/

    This function is returning the following list:
        ['SampleA', 'SampleA/SubSampleB', 'SampleA/SubSampleB/SubSampleC']

    It is to say a list of all parents.

    Parameters
    ----------
    actual_path : string or Path
        The full path (including the filename) of the pictures being considered.
    base_path : string or Path
        The path of the protocol.

    Returns
    -------
    p_list : list
        A list of parent. See the function description for more details.

    """
    if not isinstance(actual_path, Path):
        actual_path = Path(actual_path)

    if not isinstance(base_path, Path):
        base_path = Path(base_path)

    full_name = str(actual_path.relative_to(
        base_path).parent).replace('\\', '/')

    p_list = []
    if full_name == '.':
        return p_list

    for i in range(len(full_name.split('/'))):
        element = "/".join(full_name.split("/")[0:i])
        if element != '':
            p_list.append(element)

    p_list.append(full_name)

    return p_list


def decode_command_output(text):
    """
    Decode the output of a command started with Popen.

    Parameters
    ----------
    text : STRING
        The text produced by Popen and to be decoded.

    Returns
    -------
    STRING
        The decoded text.

    """
    return '\n'.join(text.decode('utf-8').splitlines())


def ctname():
    """
    Return the current QThread name.

    Returns
    -------
    STRING
        The name of the current QThread.

    """
    return QtCore.QThread.currentThread().objectName()


# noinspection PyPep8Naming
class literal_str(str):
    """Type definition for the YAML representer."""

    pass


def change_style(style, representer):
    """
    Change the YAML dumper style.

    Parameters
    ----------
    style : String
        A string to define new style.
    representer : SafeRepresenter
        The yaml representer of which the style should be changed

    Returns
    -------
    Callable
        The new representer with the changed style.

    """

    def new_representer(dumper, data):
        """
        Return the new representer.

        Parameters
        ----------
        dumper : TYPE
            DESCRIPTION.
        data : TYPE
            DESCRIPTION.

        Returns
        -------
        scalar : TYPE
            DESCRIPTION.

        """
        scalar = representer(dumper, data)
        scalar.style = style
        return scalar

    return new_representer


def my_excepthook(exc_type, exc_value, traceback, logger=log):
    """Define a customized exception hook.

    Instead of printing the output of an uncaught exception to the stderr,
    it is redirected to the logger. It is very practical because it will
    appear on the GUI

    Parameters
    ----------
    exc_type : TYPE
        The exception type.
    exc_value : TYPE
        The exception value.
    traceback : TYPE
        The whole traceback.
    logger : TYPE, optional
        The logger instance where the exception should be sent.
        The default is log.

    Returns
    -------
    None.

    """
    logger.error("Logging an uncaught exception",
                 exc_info=(exc_type, exc_value, traceback))


def encrypt_pass(plain_text_pwd):
    """
    Encrypt a plain text password.

    In order to avoid exposure of plain text password in the code, this
    helper function can be used to store hashed password directly usable for
    the elog connection.

    Parameters
    ----------
    plain_text_pwd : string
        The plain text password as introduced by the user to be encrypted.

    Returns
    -------
    string
        The hashed password to be used directly in the elog connect method.

    """
    return elog.logbook._handle_pswd(plain_text_pwd, True)


def dump_yaml_file(yaml_dict, yaml_filename):
    """
    Dump a yaml dictionary to a file.

    This helper function allows to save a yaml dictionary in a file using the
    right encoding.
    A line of comment is prepended to the file.

    Parameters
    ----------
    yaml_dict : dict
        The dictionary to be dumped on file.
    yaml_filename : str or path-like
        The output filename of the yaml dump..

    Returns
    -------
    None.

    """
    with open(yaml_filename, 'w', encoding='utf-8') as f:
        f.write(
            f'# YAML FILE Dumped at {datetime.now():%Y-%m-%d %H:%M:%S}\n\n')

        yaml_dict = remove_empty_slots(yaml_dict)
        if len(yaml_dict) != 0:
            yaml.dump(yaml_dict, f, allow_unicode=True)


def is_yaml_file_dumping_needed(yaml_dict: dict, yaml_file_name:str | Path):

    with open(yaml_file_name, 'r', encoding='utf-8') as file:
        stored = yaml.safe_load(file)
    for key in yaml_dict.keys():
        print(f'{key} current_dict = {yaml_dict[key]}, stored = {stored.get(key, "MISSING")}')

    print(f'The two dictionaries are identical {stored==yaml_dict}')

    return not yaml_dict == stored

def remove_empty_slots(yaml_dict: dict) -> dict:
    empty_keys = list()
    for key, value in yaml_dict.items():
        empty_values = [subvalues == '' for subvalues in value.values()]
        if all(empty_values):
            empty_keys.append(key)
    for key in empty_keys:
        del yaml_dict[key]

    return yaml_dict


class ResolutionUnit(IntEnum):
    """Resolution unit of a TIFF file."""

    NONE = 1
    INCH = 2
    CM = 3

    @staticmethod
    def inverse_resolution_unit(cls):
        """Return the inverse resolution unit."""
        if cls.name == 'NONE':
            return 'none'
        elif cls.name == 'INCH':
            return 'dpi'
        elif cls.name == 'CM':
            return 'dpcm'

    def __str__(self):
        """.Return the string value."""
        return self.name


class ResolutionSource(IntEnum):
    """Enumerator used to define from where the resolution information should be taken."""

    TIFF_TAG = auto()
    FEI_TAG = auto()


class PictureResolution:
    """
    Picture Resolution class.

    It contains the horizontal and vertical resolution of a microscope picture
    along with the unit of measurements

    """

    def __init__(self, xres, yres, ures):
        if xres <= 0 or yres <= 0:
            raise ValueError('Resolution must be positive')
        self.xres = float(xres)
        self.yres = float(yres)
        if isinstance(ures, ResolutionUnit):
            ures = ResolutionUnit(ures)
        if ures not in (ResolutionUnit.NONE, ResolutionUnit.INCH, ResolutionUnit.CM):
            raise autoerror.WrongResolutionUnit('Invalid resolution unit')
        self.ures = ures

    def __eq__(self, other):
        """
        Compare two Picture Resolution object.

        If the second object has the same unit of measurements of the first one,
        the comparison is made straight forward looking at the horizontal and
        vertical resolution.

        If the two have different unit of measurements, then the second is
        temporary converted and the two resolution values are then compared.

        For the comparison a rounding of 5 digits is used.

        Parameters
        ----------
        other : PictureResolution instance
            Another picture resolution instance

        Returns
        -------
        bool
            True if the two PictureResolution objects are identical or at
            least equivalent. False otherwise.

        """
        if self.ures == other.ures:
            return round(self.xres, 5) == round(other.xres, 5) and round(self.yres, 5) == round(other.yres, 5)
        else:
            old_ures = other.ures
            other.convert_to_unit(self.ures)
            is_equal = round(self.xres, 5) == round(other.xres, 5) and round(
                self.yres, 5) == round(other.yres, 5)
            other.convert_to_unit(old_ures)
            return is_equal

    def __str__(self):
        """Print out a Picture Resolution instance."""
        return (f'({self.xres:.5} {ResolutionUnit.inverse_resolution_unit[self.ures]} '
                f'x {self.yres:5} {ResolutionUnit.inverse_resolution_unit[self.ures]})')

    def __repr__(self):
        """Represent a Picture_resolution."""
        return f'{self.__class__.__name__}(self.xres, self.yres, self.ures)'

    def as_tuple(self):
        """Return the picture resolution as a tuple."""
        return self.xres, self.yres, self.ures

    def convert_to_unit(self, desired_um):
        """
        Convert the Picture Resolution to the desired unit of measurement.

        Parameters
        ----------
        desired_um : ResolutionUnit
            The target resolution unit

        Raises
        ------
        autoerror.WrongResolutionUnit
            If an invalid target resolution unit is passed.

        autoerror.ImpossibleToConvert
            If one of the two resolution has ResolutionUnit.NONE

        Returns
        -------
        None.

        """
        if self.ures == ResolutionUnit.NONE or desired_um == ResolutionUnit.NONE:
            raise autoerror.ImpossibleToConvert(
                'Impossible to convert, because resolution unit of measurement is none.')

        if self.ures == desired_um:
            conv_fact = 1
        else:
            if self.ures == ResolutionUnit.INCH:
                if desired_um == ResolutionUnit.CM:
                    conv_fact = 1 / 2.54
                else:
                    raise autoerror.WrongResolutionUnit(
                        'Invalid resolution unit of measurement')
            else:  # self.ures == ResolutionUnit.cm
                if desired_um == ResolutionUnit.INCH:
                    conv_fact = 2.54
                else:
                    raise autoerror.WrongResolutionUnit(
                        'Invalid resolution unit of measurement')

        self.ures = desired_um
        self.xres *= conv_fact
        self.yres *= conv_fact


def get_picture_resolution(tiffinfo: PIL.TiffImagePlugin.ImageFileDirectory_v2,
                           source: ResolutionSource = ResolutionSource.TIFF_TAG,
                           desired_um: ResolutionUnit = None) -> PictureResolution | None:
    """
    Get the Picture Resolution object from TIFF tags.

    All TIFF images must have the resolution information store in the TIFF tags.
    In the case of FEI images, the resolution information stored in the basic
    TIFF tags is incorrect while the correct one is saved in the custom FEI
    tags.

    Using this method, both resolution information can be retrieved using the
    ResolutionSource enumerator.

    Using the desired_um, the Picture Resolution can be converted to a convenient
    unit of measurements

    Parameters
    ----------
    tiffinfo : PIL.TiffImagePlugin.ImageFileDirectory_v2
        A dictionary containing all TIFF tags
    source : ResolutionSource, optional
        From where the resolution information should be taken from.
        Possible values are 'FEI_TAG' and 'TIFF_TAG'.
        The default is 'TIFF_TAG'.
    desired_um : ResolutionUnit, optional
        The resolution unit in which the Picture resolution should be returned.
        Use None to obtain the original one without conversion.
        The default is None.

    Returns
    -------
    PictureResolution :
        The picture resolution. None if it was not possible to calculate it.

    """
    if not isinstance(tiffinfo, ImageFileDirectory_v2):
        raise TypeError(
            'tiffinfo must be a PIL.TiffImagePlugin.ImageFileDirectory_v2')

    if isinstance(source, (ResolutionSource, str)):
        if isinstance(source, str):
            try:
                source = ResolutionSource(source)
            except ValueError as e:
                log.error('Unknown source of resolution')
                log.exception(e)
                raise e
    else:
        raise TypeError(
            'Wrong type for source. Please use ResolutionSource enumerator.')

    if desired_um not in (ResolutionUnit.NONE, ResolutionUnit.INCH, ResolutionUnit.CM):
        raise ValueError('Invalid value for the target unit of measurement')

    resolution = None

    if source == ResolutionSource.TIFF_TAG:
        xres_code = 282
        yres_code = 283
        ures_code = 296

        resolution = PictureResolution(tiffinfo.get(xres_code, 0), tiffinfo.get(yres_code, 0),
                                       ResolutionUnit(tiffinfo.get(ures_code, 0)))
        if desired_um is not None:
            resolution.convert_to_unit(desired_um)

    elif source == ResolutionSource.FEI_TAG:

        fei_tag_code = 34682
        fei_metadata = configparser.ConfigParser(allow_no_value=True, strict=False)
        fei_metadata.read_string(tiffinfo[fei_tag_code])

        pixel_width = fei_metadata.getfloat('Scan', 'PixelWidth')
        pixel_height = fei_metadata.getfloat('Scan', 'PixelHeight')

        xres = 1 / (pixel_width * 100)
        yres = 1 / (pixel_height * 100)
        ures = ResolutionUnit.CM

        resolution = PictureResolution(xres, yres, ures)
        if desired_um is not None:
            resolution.convert_to_unit(desired_um)

    return resolution


class OpticalImageType(Enum):
    GENERIC_OPTICAL_IMAGE = 'Generic'
    KEYENCE_OPTICAL_IMAGE = 'Keyence'
    DIGITAL_CAMERA_OPTICAL_IMAGE = 'DigitalCamera'
    DIGITAL_CAMERA_OPTICAL_IMAGE_WITH_GPS = 'DigitalCameraWithGPS'
    INVALID_OPTICAL_IMAGE = 'Invalid'

    def __str__(self):
        return self.value


class PictureType(Enum):
    """Enumerator to define the various microscope picture types."""

    GENERIC_MICROSCOPE_PICTURE = 'Generic'
    FEI_MICROSCOPE_PICTURE = 'FEI'
    QUATTRO_MICROSCOPE_PICTURE = 'FEI.Quattro'
    VERSA_MICROSCOPE_PICTURE = 'FEI.Versa'
    VEGA_MICROSCOPE_PICTURE = 'Vega'
    VEGA_JPEG_MICROSCOPE_PICTURE = 'Vega.JPEG'
    XL40_MICROSCOPE_PICTURE = 'XL40'
    XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE = 'XL40.Multiframe.WithStage'
    XL40_MULTIFRAME_MICROSCOPE_PICTURE = 'XL40.Multiframe'
    XL40_WITH_STAGE_MICROSCOPE_PICTURE = 'XL40.WithStage'

    def __str__(self):
        """
        Convert to string.

        Returns
        -------
        str
            the enumerator member value as a string

        """
        return self.value


class ReadOnlyDecision(IntEnum):
    """Enumerator defining the user choice in case of a read-only entry.

    When the user is attempting to write/edit/delete a read-only entry in the logbook
    he is asked to take a decision on what he would like to do.

    Overwrite: the edit-lock is switched off and the read-only entry is turned editable.

    Backup: the read-only entry is backed up in another entry with the same content but
        where the protocol number has been edited inserting a backup tag.

    Edit: the user has the possibility to modify the protocol number of the current entry
        hopefully not corresponding to another read-only entry.

    """

    Overwrite = auto()
    Backup = auto()
    Edit = auto()


class LoggerDecision(Enum):
    """Enumerator for the user decision about the newly added log level."""

    KEEP = 'keep'
    KEEP_WARN = 'keep-warn'
    OVERWRITE = 'overwrite'
    OVERWRITE_WARN = 'overwrite-warn'
    RAISE = 'raise'


class FEITagCodes(IntEnum):
    """Enumerator for the FEI specific TIFF tags."""

    FEI_SFEG = 34680
    FEI_HELIOS = 34682


def add_logging_level(level_name, level_num, method_name=None, if_exists=LoggerDecision.KEEP, *,  # noqa: C901
                      exc_info=False, stack_info=False):
    """Add a logging level."""

    def for_logger_class(self, message, *args, **kwargs):
        """
        No idea!

        Parameters
        ----------
        self
        message
        args
        kwargs
        """
        if self.isEnabledFor(level_num):
            kwargs.setdefault('exc_info', exc_info)
            kwargs.setdefault('stack_info', stack_info)
            self._log(level_num, message, args, **kwargs)

    def for_logging_module(*args, **kwargs):
        """
        No idea.

        Parameters
        ----------
        args
        kwargs
        """
        kwargs.setdefault('exc_info', exc_info)
        kwargs.setdefault('stack_info', stack_info)
        logging.log(level_num, *args, **kwargs)

    if not method_name:
        method_name = level_name.lower()

    items_found = 0
    items_conflict = 0

    logging._acquireLock()
    try:
        registered_num = logging.getLevelName(level_name)
        logger_class = logging.getLoggerClass()

        if registered_num != 'Level ' + level_name:
            items_found += 1
            if registered_num != level_num:
                if if_exists == LoggerDecision.RAISE:
                    # Technically this is not an attribute issue, but for
                    # consistency
                    raise AttributeError(
                        'Level {!r} already registered in logging '
                        'module'.format(level_name)
                    )
                items_conflict += 1

        if hasattr(logging, level_name):
            items_found += 1
            if getattr(logging, level_name) != level_num:
                if if_exists == LoggerDecision.RAISE:
                    raise AttributeError(
                        'Level {!r} already defined in logging '
                        'module'.format(level_name)
                    )
                items_conflict += 1

        if hasattr(logging, method_name):
            items_found += 1
            logging_method = getattr(logging, method_name)
            if not callable(logging_method) or \
                    getattr(logging_method, '_original_name', None) != \
                    for_logging_module.__name__:
                if if_exists == LoggerDecision.RAISE:
                    raise AttributeError(
                        'Function {!r} already defined in logging '
                        'module'.format(method_name)
                    )
                items_conflict += 1

        if hasattr(logger_class, method_name):
            items_found += 1
            logger_method = getattr(logger_class, method_name)
            if not callable(logger_method) or \
                    getattr(logger_method, '_original_name', None) != \
                    for_logger_class.__name__:
                if if_exists == LoggerDecision.RAISE:
                    raise AttributeError(
                        'Method {!r} already defined in logger '
                        'class'.format(method_name)
                    )
                items_conflict += 1

        if items_found > 0:
            # items_found >= items_conflict always
            if (items_conflict or items_found < 4) and \
                    if_exists in (LoggerDecision.KEEP_WARN, LoggerDecision.OVERWRITE_WARN):
                action = 'Keeping' if if_exists == LoggerDecision.KEEP_WARN else 'Overwriting'
                if items_conflict:
                    problem = 'has conflicting definition'
                    items = items_conflict
                else:
                    problem = 'is partially configured'
                    items = items_found
                log.warning(
                    'Logging level %s %s already (%s/4 items): %s' % (
                        repr(level_name), problem, items, action)
                )

            if if_exists in (LoggerDecision.KEEP, LoggerDecision.KEEP_WARN):
                return

        # Make sure the method names are set to sensible values, but
        # preserve the names of the old methods for future verification.
        for_logger_class._original_name = for_logger_class.__name__
        for_logger_class.__name__ = method_name
        for_logging_module._original_name = for_logging_module.__name__
        for_logging_module.__name__ = method_name

        # Actually add the new level
        logging.addLevelName(level_num, level_name)
        setattr(logging, level_name, level_num)
        setattr(logger_class, method_name, for_logger_class)
        setattr(logging, method_name, for_logging_module)
    finally:
        logging._releaseLock()


def pretty_fmt_sample_details(sample_details: list[(int, str, str)]) -> str:
    string_list = []
    for n, s, p in sample_details:
        if n == 1:
            string_list.append(f'{n} {s}')
        elif n > 1:
            string_list.append(f'{n} {p}')
    if len(string_list) == 0:
        return 'no elements'
    elif len(string_list) == 1:
        return string_list[0]
    elif len(string_list) == 2:
        return ' and '.join(string_list)
    else:
        return ', '.join(string_list[:-1]) + ' and ' + string_list[-1]


def pretty_fmt_filesize(size_bytes):
    """
    Return a nicely formatted string with the filesize with the proper unit.

    Parameters
    ----------
    size_bytes : int
        This is the file size in bytes. Typically this is what is returned
        by Path().stat().st_size.

    Returns
    -------
    size : str
        Nicely formatted string representing the file size with the most
        appropriate unit of measurement.

    """
    if size_bytes == 0:
        return '0 B'
    size_name = ('B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f'{s} {size_name[i]}'


def pretty_fmt_magnification(magnification: float) -> str:
    return pretty_fmt_physical_quantity(magnification, 'x')


def pretty_fmt_physical_quantity(quantity: float, base_unit_of_measurement: str) -> str:
    """
    Return a nicely formatted string with the best representation of a physical quantity.

    So for example 0.123 A will be returned as 123 mA.

    Parameters
    ----------
    quantity: float
       The value of the physical quantity. The function expect this to be in the base unit,
       so if it is a current, this value should be in ampere and not one of its (sub-)multiples.

    base_unit_of_measurement: str
        This is the unit of measurement.

    Returns
    -------
    str
        The nicely formatted physical quantity. See description for an example.
    """
    if quantity == 0:
        return f'0 {base_unit_of_measurement}'

    multiply_divider = 1000
    multiple_unit = {-8: 'y', -7: 'z', -6: 'a', -5: 'f', -4: 'p', -3: 'n', -2: 'u', -1: 'm',
                     0: '', 1: 'k', 2: 'M', 3: 'G', 4: 'T', 5: 'P', 6: 'E', 7: 'Z', 8: 'Y'}
    multiple_unit_key = int(math.floor(math.log(math.fabs(quantity), multiply_divider)))
    multiple_quantity = math.pow(multiply_divider, multiple_unit_key)
    rounded_quantity = round(quantity / multiple_quantity, 3)
    return f'{rounded_quantity} {multiple_unit[multiple_unit_key]}{base_unit_of_measurement}'


class DateType(IntEnum):
    """Enumerator for selecting the type of date saved in the file."""

    ATIME = auto()
    MTIME = auto()
    CTIME = auto()


def get_date_from_file(file_stat: os.stat, date_type: DateType) -> datetime:
    """
    Return a datetime object with the file date.

    In the file_stat (as generated by Path.stat()) contains three different date
    information.

      - DateType.ATIME: last access time
      - DateType.MTIME: last modification time
      - DateType.CTIME: creation time

    The date information are stored as timestamp. This function is converting
    the timestamp in a datetime object in the local_path timezone.

    Parameters
    ----------
    file_stat : os.stat
        The os.stat information of the file under investigation.
    date_type : DateType
        A enumerator to select the type of date

    Returns
    -------
    local_datetime : datetime
        The date information as a datetime object in the local_path timezone.

    """
    if date_type == date_type.ATIME:
        ts = file_stat.st_atime
    elif date_type == date_type.MTIME:
        ts = file_stat.st_mtime
    elif date_type == date_type.CTIME:
        ts = file_stat.st_ctime
    else:  # should not happen
        ts = 0
    ts = datetime.fromtimestamp(ts, tz=timezone.utc)
    from_zone = tz.tzutc()
    to_zone = tz.tzlocal()

    utc = ts.replace(tzinfo=from_zone)
    cet = utc.astimezone(to_zone)

    return cet


def convert_to_string(dictionary: dict) -> dict:
    new_dict = dict()
    for key, value in dictionary.items():
        try:
            new_dict[key] = str(value)
        except ValueError:
            log.debug('Failed to convert %s to string', type(value))
    return new_dict


def reglob(path: str | Path, matching_regexes: str | list[str] | None, ignore_regexes: str | list[str] | None,
           recursive: bool = True) -> list[str]:
    """
    Emulates the glob.glob using regular expressions.

    Parameters
    ----------
    path: str | Path
        The root path from where the glob should be started.
    matching_regexes: str | list[str] | None
        One or several regular expressions to be used as matching patterns.
        Use None to get the equivalent of a '*' wildcard.
    ignore_regexes: str | list[str] | None
        One or several regular expressions to be used as excluding patterns.
        Use None to disable the exclusion mechanism.
    recursive: bool
        True if the search should be performed through all subdirectories.

    Returns
    -------
    list[str]:
        A list of all elements matching the regular expressions and not excluded.

    """
    if matching_regexes is None:
        matching_regexes = [r'.*']
    elif isinstance(matching_regexes, str):
        matching_regexes = [matching_regexes]

    if ignore_regexes is None:
        ignore_regexes = []
    elif isinstance(ignore_regexes, str):
        ignore_regexes = [ignore_regexes]

    if isinstance(path, str):
        path = Path(path)

    matching_regexes = [re.compile(r) for r in matching_regexes]
    ignore_regexes = [re.compile(r) for r in ignore_regexes]

    file_list = []
    if recursive:
        glob_list = path.rglob('*')
    else:
        glob_list = path.glob('*')

    for file in glob_list:
        if any(r.match(str(file)) for r in ignore_regexes):
            pass
        elif any(r.match(str(file)) for r in matching_regexes):
            file_list.append(str(file))

    return file_list


def strip_path(absolute_path: Path | str, relative_path: Path | str) -> Path:
    if isinstance(absolute_path, Path):
        absolute_path = str(absolute_path)

    if isinstance(relative_path, Path):
        relative_path = str(relative_path)

    if relative_path and absolute_path.endswith(relative_path):
        return Path(absolute_path[:-len(relative_path)])

    return Path(absolute_path)


def pretty_print_dict(dictionary: dict):
    for key, value in dictionary.items():
        print(f'{key=} --> {value=}')


class YAMLRecycler:
    """
    Helper class for the recycling of YAML customization items.

    When a protocol item is renamed or moved to another sample, it is important that the original customization fields
    are preserved and moved with the item.

    The class has a public method (recycle) that is actually doing all the job by dispatching the task to specific
    methods depending on the type of item.
    """

    def recycle(self, yaml_dict: dict, element_type: ElementType, old_key: str, new_key: str) -> None:
        """
        Recycle the custom fields.

        This work as a dispatch function redirecting the task to a specialized method depending of the ElementType.

        Parameters
        ----------
        yaml_dict: dict
            The dictionary containing the customization items.
        element_type: ElementType
            The type of element for which the recycling is requested.
        old_key: str
            The old key of the dictionary to be recycled.
        new_key: str
            The new key for the recycling.
        """
        # self.pre_recycle_debug(yaml_dict)
        self.for_each_type(yaml_dict, element_type, old_key, new_key)
        {
            ElementType.NAVIGATION_PIC: self.for_navigation_picture,
            ElementType.ATTACHMENT_FILE: self.for_attachment_file,
            ElementType.SAMPLE: self.for_sample,
            ElementType.MICROSCOPE_PIC: self.for_microscope_picture,
            ElementType.VIDEO_FILE: self.for_video_file,
            ElementType.OPTICAL_PIC: self.for_optical_image,
        }[element_type](yaml_dict, old_key, new_key)
        # self.post_recycle_debug(yaml_dict)

    def pre_recycle_debug(self, yaml_dict: dict):
        """
        Debug method.

        REMOVE ME LATER

        Parameters
        ----------
        yaml_dict

        Returns
        -------

        """
        print('Before recycling')
        print('Dictionary size ={len(yaml_dict)}')
        pretty_print_dict(yaml_dict)

    def post_recycle_debug(self, yaml_dict: dict):
        """
        Debug method.

        REMOVE ME LATER

        Parameters
        ----------
        yaml_dict

        Returns
        -------

        """
        print('After recycling')
        pretty_print_dict(yaml_dict)

    def for_each_type(self, yaml_dict: dict, element_type: ElementType, old_key: str, new_key: str) -> None:
        # log.vipdebug('Executing recycling of %s: from %s to %s' % (element_type, old_key, new_key))
        pass

    def for_navigation_picture(self, yaml_dict: dict, old_key: str, new_key: str) -> None:
        # the navigation picture is a single element its key is the whole path, so it is very easily a key swap
        self._rename_key(yaml_dict, old_key, new_key)

    def for_attachment_file(self, yaml_dict: dict, old_key: str, new_key: str) -> None:
        # the attachment is a single element and its key is the whole path, so just rename the key
        self._rename_key(yaml_dict, old_key, new_key)

    def for_optical_image(self, yaml_dict: dict, old_key: str, new_key: str) -> None:
        # the optical image is a single element and its key is the whole path, so just rename the key
        self._rename_key(yaml_dict, old_key, new_key)

    def for_sample(self, yaml_dict: dict, old_key: str, new_key: str) -> None:
        # the sample or subsample is a folder. we need to recycle all sample and subsamples containing the old_key,
        # plus all elements having the old_key in the path.
        # old_key is in the form of sample1/ssample2

        list_of_samples = []
        # we cannot modify the dictionary while scanning it.
        # we prepare a list of items to be modified and then we do the recycling.
        for key in yaml_dict.keys():
            if str(key).startswith(old_key):
                list_of_samples.append(key)

        for old_sample in list_of_samples:
            new_sample = old_sample.replace(old_key, new_key)
            yaml_dict[new_sample] = yaml_dict.get(old_sample)
            del yaml_dict[old_sample]

        # now we have to search of sample files that were in the old sample and change their key (path) to point to the
        # new sample.
        # the yaml key is the path converted as string, that means that we need to change the '/' into a '\\'
        # (the second \ is an escape)
        old_key = old_key.replace('/', '\\\\')
        new_key = new_key.replace('/', '\\\\')
        list_of_items = []
        for key in yaml_dict.keys():
            if re.search(old_key, str(key)):
                list_of_items.append(key)

        for old_item in list_of_items:
            new_item = re.sub(old_key, new_key, old_item)
            yaml_dict[new_item] = yaml_dict.get(old_item)
            del yaml_dict[old_item]

    def for_microscope_picture(self, yaml_dict: dict, old_key: str, new_key: str) -> None:
        # the microscope picture is a single element and its key is the whole path. so just rename the key.
        self._rename_key(yaml_dict, old_key, new_key)

    def for_video_file(self, yaml_dict: dict, old_key: str, new_key: str) -> None:
        # the video file is a single element and its key it the whole path, so just rename the key
        self._rename_key(yaml_dict, old_key, new_key)

    def _rename_key(self, yaml_dict: dict, old_key: str, new_key) -> None:
        # rename the old key, only if it exists.
        if old_key in yaml_dict:
            # copy the old element with the new key
            yaml_dict[new_key] = yaml_dict.get(old_key)
            # delete the old element
            del yaml_dict[old_key]


def main_parser() -> argparse.ArgumentParser:
    """
    Define the main argument parser.

    Returns
    -------
    parser : ArgumentParser
        The main parser.

    """
    parser = argparse.ArgumentParser(description='''
                                     GUI of the automatic
                                     logbook generation tool for microscopy
                                     ''')
    # Define here all configuration related arguments
    # configuration file, experiment file
    confgroup = parser.add_argument_group('Configuration',
                                          '''
                                          The following options allow the user to specify
                                          a configuration file different from the default one
                                          or an experiment file to be loaded.
                                          ''')
    confgroup.add_argument('-c', '--conf-file', type=Path, dest='conffile',
                           default=(Path.cwd() / Path('autolog-conf.ini')),
                           help='Specify a configuration file to be loaded.')
    confgroup.add_argument('-e', '--exp-file', type=Path, dest='expfile',
                           help='Specify an experiment file to be loaded')
    confgroup.add_argument('-x', '--auto-exec', dest='autoexec', action='store_true',
                           help='When used in conjunction with -e, if the start watchdog is '
                                'enabled, the watchdog will be started right away')

    # Define here all user interface options
    uigroup = parser.add_argument_group('User interface', '''
                                        Instead of executing the full graphical user interface,
                                        the user may opt for a simplify command line interface
                                        using the options below.\n\n
                                        ** NOTE ** The CLI is still very experimental.
                                        ''')
    uigroup.add_argument('-t', '--cli', dest='cli', action='store_true',
                         help='When set, a simplified command line interface will '
                              'be started. It implies the -x option and it requires '
                              'an experiment file to be specified with -e.\n'
                              'A valid combination is -txe <experiment_file>')

    uigroup.add_argument('--no-qapp', dest='noapp', action='store_true', default=False,
                         help='When set, no QApplication will be created or started. To be used only when launched '
                              'from the wizard.')

    uigroup.add_argument('-l', '--log', dest='loglevel',
                         type=str.lower,
                         choices=('debug', 'vipdebug', 'info', 'warning',
                                  'error', 'critical'),
                         default='info',
                         help='''
                        The verbosity of the logging messages.
                        ''')

    # Define here all authentication options
    authgroup = parser.add_argument_group('Authentication', '''
                                          Override the username and password settings in the
                                          configuration file. If the user provides only a username
                                          the password in the configuration will not be used.
                                          If no password is given with option -p, a dialog window
                                          will ask for the user credentials when need it.
                                          The user must enter his/her password as plain text from
                                          the command line.\n
                                          '''
                                                            '''
                                          **NOTE**
                                          Credentials stored in experiment files are not overridden!
                                          ''')
    authgroup.add_argument('-u', '--user', type=str, dest='username',
                           help='Specify the username to be used for the connection to the ELOG. '
                                + 'When this flag is used, the user must provide a password either via '
                                + 'the -p flag or via the GUI when prompted.')
    authgroup.add_argument('-p', '--password', type=str, dest='password',
                           help='Specify the password to be used for the connection to the ELOG. '
                                + 'If a username is not provided via the -u flag, the username in the '
                                + 'configuration file will be used.')

    return parser


class ImageType(Enum):
    """Enumerator to select the type of image file"""
    TIFF = 'tiff'
    PNG = 'png'
    THUMBNAIL = 'thumbnail'


class VisibilityFlag(Flag):
    pass


class CustomEditVisibilityFlag(VisibilityFlag):
    CAPTION = auto()
    DESCRIPTION = auto()
    EXTRA = auto()

    ALWAYS = CAPTION | DESCRIPTION | EXTRA
    NEVER = ~ALWAYS

    MARKDOWN = DESCRIPTION | EXTRA


class MetadataVisibilityFlag(VisibilityFlag):
    WITHOUT_ITEM = auto()
    WITH_ITEM = auto()

    ALWAYS = WITH_ITEM | WITHOUT_ITEM
    NEVER = ~ALWAYS


class LogMessageBoxVisibilityFlag(VisibilityFlag):
    NO_SELECTION = auto()
    SELECTION = auto()

    ALWAYS = NO_SELECTION | SELECTION
    NEVER = ~ALWAYS


class ElementTypeVisitiliyFlag(VisibilityFlag):
    NO_ITEM = auto()
    SECTION = auto()
    SAMPLE = auto()
    NAVIGATION_PIC = auto()
    MICROSCOPE_PIC = auto()
    OPTICAL_PIC = auto()
    VIDEO_FILE = auto()
    ATTACHMENT_FILE = auto()

    IMAGE_ITEM = NAVIGATION_PIC | MICROSCOPE_PIC | OPTICAL_PIC
    RENAMEBABLE_ITEM = SAMPLE | NAVIGATION_PIC | MICROSCOPE_PIC | VIDEO_FILE | ATTACHMENT_FILE | OPTICAL_PIC
    DELETABLE_ITEM = RENAMEBABLE_ITEM
    RECYCLABLE_ITEM = MICROSCOPE_PIC | VIDEO_FILE | ATTACHMENT_FILE | OPTICAL_PIC
    PROTOCOL_ITEM = RENAMEBABLE_ITEM
    RECOVARABLE_ITEM = SAMPLE | MICROSCOPE_PIC | VIDEO_FILE | SECTION | ATTACHMENT_FILE | OPTICAL_PIC
    MOVABLE_ITEM = SAMPLE | MICROSCOPE_PIC | VIDEO_FILE | ATTACHMENT_FILE | OPTICAL_PIC
    CUSTOMIZABLE_ITEM = SECTION | SAMPLE | NAVIGATION_PIC | MICROSCOPE_PIC | VIDEO_FILE | ATTACHMENT_FILE | OPTICAL_PIC
    ANCHORABLE_ITEM = SECTION | SAMPLE | NAVIGATION_PIC | MICROSCOPE_PIC | VIDEO_FILE | ATTACHMENT_FILE | OPTICAL_PIC
    ALWAYS = NO_ITEM | SECTION | SAMPLE | NAVIGATION_PIC | MICROSCOPE_PIC | VIDEO_FILE | ATTACHMENT_FILE | OPTICAL_PIC
    NEVER = ~ALWAYS


def get_visibility_from_item_type(type: ElementType) -> ElementTypeVisitiliyFlag:
    if type == ElementType.SECTION:
        return ElementTypeVisitiliyFlag.SECTION
    elif type == ElementType.SAMPLE:
        return ElementTypeVisitiliyFlag.SAMPLE
    elif type == ElementType.NAVIGATION_PIC:
        return ElementTypeVisitiliyFlag.NAVIGATION_PIC
    elif type == ElementType.MICROSCOPE_PIC:
        return ElementTypeVisitiliyFlag.MICROSCOPE_PIC
    elif type == ElementType.VIDEO_FILE:
        return ElementTypeVisitiliyFlag.VIDEO_FILE
    elif type == ElementType.ATTACHMENT_FILE:
        return ElementTypeVisitiliyFlag.ATTACHMENT_FILE
    elif type == ElementType.OPTICAL_PIC:
        return ElementTypeVisitiliyFlag.OPTICAL_PIC
    else:
        return ElementTypeVisitiliyFlag.NEVER


class VegaMetadataParser():
    class MetadataDecoder():
        def __init__(self, pattern, typ):
            self.pattern = pattern
            self.typ = typ

    pattern_dict = dict()
    pattern_dict['microscope'] = MetadataDecoder(rb'(TS5130LS)', str)
    pattern_dict['protocol'] = MetadataDecoder(rb'Sign=(.*)\r\n', str)
    pattern_dict['note'] = MetadataDecoder(rb'Note=(.*)\r\n', str)
    pattern_dict['magnification'] = MetadataDecoder(rb'Magnification=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['pixel_size_x'] = MetadataDecoder(rb'PixelSizeX=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['pixel_size_y'] = MetadataDecoder(rb'PixelSizeY=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['vacuum'] = MetadataDecoder(rb'ChamberPressure=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['detector'] = MetadataDecoder(rb'Detector=(.*)\r\n', str)
    pattern_dict['dwell_time'] = MetadataDecoder(rb'DwellTime=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['scan_mode'] = MetadataDecoder(rb'ScanMode=(.*)\r\n', str)
    pattern_dict['scan_rotation'] = MetadataDecoder(rb'ScanRotation=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['scan_speed'] = MetadataDecoder(rb'ScanSpeed=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['emission_current'] = MetadataDecoder(rb'EmissionCurrent=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['HV'] = MetadataDecoder(rb'HV=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['specimen_current'] = MetadataDecoder(rb'SpecimenCurrent=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['spot_size'] = MetadataDecoder(rb'SpotSize=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['stage_r'] = MetadataDecoder(rb'StageRotation=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['stage_t'] = MetadataDecoder(rb'StageTilt=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['stage_x'] = MetadataDecoder(rb'StageX=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['stage_y'] = MetadataDecoder(rb'StageY=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['stage_z'] = MetadataDecoder(rb'StageZ=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)
    pattern_dict['WD'] = MetadataDecoder(rb'WD=(-?\d+\.?\d*[e|E]?[\-|\+]?\d*)\r\n', float)

    def __init__(self):
        self.messy_metadata = None

    @classmethod
    def from_bytes(cls, metadata: bytes) -> VegaMetadataParser:
        parser = cls()
        parser.messy_metadata = metadata
        return parser

    @classmethod
    def from_tag_dictionary(cls, tag_directory: PIL.TiffImagePlugin.ImageFileDirectory_v2) -> VegaMetadataParser:
        parser = cls()
        parser.messy_metadata = tag_directory.get(autoconfig.VEGA_TIFFCODE, None)

        return parser

    def parse_all(self):
        if self.messy_metadata is None:
            raise autoerror.InvalidMetadata
        parsed_metadata = dict()
        for key, value in self.pattern_dict.items():
            match = re.search(value.pattern, self.messy_metadata)
            if match:
                if value.typ == str:
                    parsed_metadata[key] = match.group(1).decode('utf-8').strip()
                else:
                    parsed_metadata[key] = value.typ(match.group(1))
        return parsed_metadata

    def parse_single_metadata(self, key):
        if key not in self.pattern_dict:
            return None

        if self.messy_metadata is None:
            raise autoerror.InvalidMetadata

        decoder = self.pattern_dict[key]
        match = re.search(decoder.pattern, self.messy_metadata)
        if match:
            if decoder.typ == str:
                return match.group(1).decode('utf-8').strip()
            else:
                return decoder.typ(match.group(1))


def pretty_print_exif_dict(exif_dict: dict):
    for main_key in [k for k in exif_dict.keys() if k != 'thumbnail']:
        for key in piexif.TAGS[main_key]:
            if key in exif_dict[main_key]:
                print(f'{piexif.TAGS[main_key][key]["name"]} = {exif_dict[main_key][key]}')


def decode_bytes(input_data: bytes) -> str:
    """
    Decode the byte lists using a list of possible codec candidates.

    Parameters
    ----------
    input_data: bytes
        A list of bytes

    Returns
    -------
    str:
        A string with the decoded content

    Raises
    ------
    autoerror.DecodeError:
        If the decoding fails with all possible candidates.
    """
    possible_codec = ['utf-8', 'iso-8859-1']
    output = None
    for codec in possible_codec:
        try:
            output = input_data.decode(codec)
        except UnicodeDecodeError:
            # wrong codec, try next
            pass
        else:
            break

    if output is None:
        raise autoerror.DecodeError('Impossible to decode bytes %s' % input_data)

    return output
