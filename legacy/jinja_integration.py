# -*- coding: utf-8 -*-
"""


@author: Antonio Bulgheroni (antonio.bulgheroni@ec.europa.eu)
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
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import jinja2
import markdown
from yammy.jinja2_loaders import YammyPackageLoader

from autologbook import autoconfig
from autologbook.autotools import (
    DateType,
    get_date_from_file,
    pretty_fmt_filesize,
    pretty_fmt_magnification,
    pretty_fmt_physical_quantity,
    pretty_fmt_sample_details,
)

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


jinja_env = jinja2.Environment(loader=YammyPackageLoader('autologbook', 'templates'),
                               trim_blocks=True,
                               lstrip_blocks=True)


def add_filter_to_enviroment(env: jinja2.Environment, f: Callable[..., str], filter_name: str = None):
    if filter_name is None:
        filter_name = f.__name__
    env.filters[filter_name] = f


def fmt_physical(value, unit):
    return pretty_fmt_physical_quantity(value, unit)


def fmt_magnification(value):
    return pretty_fmt_magnification(value)


def from_markdown(markdown_str):
    return markdown.markdown(markdown_str)


def remove_from_list(input_list: list, element_to_remove):
    return [i for i in input_list if i != element_to_remove]


def fmt_file_creation_date(stat):
    return f'{get_date_from_file(stat, DateType.CTIME):%Y%m%d-%H:%M:%S}'


def fmt_file_size(size):
    return pretty_fmt_filesize(size)


def fmt_sample_details(sample_details: list[(int, str, str)]) -> str:
    return pretty_fmt_sample_details(sample_details)


def get_filename_from_path(path: str | Path) -> str:
    if isinstance(path, str):
        path = Path(path)
    return str(path.name)


def convert_path_to_uri(path: str | Path) -> str:
    if isinstance(path, Path):
        path = str(path)

    return path.replace(str(autoconfig.IMAGE_SERVER_BASE_PATH),
                        str(autoconfig.IMAGE_SERVER_ROOT_URL)).replace('\\', '/')


def to_string(value: Any) -> str:
    return str(value)


custom_filter = [fmt_physical,
                 from_markdown,
                 fmt_magnification,
                 remove_from_list,
                 fmt_file_creation_date,
                 fmt_file_size,
                 fmt_sample_details,
                 convert_path_to_uri,
                 get_filename_from_path,
                 to_string]

for filter in custom_filter:
    add_filter_to_enviroment(jinja_env, filter)


def path_exists(path: str | Path) -> bool:
    return Path(path).exists()


jinja_env.globals.update(zip=zip, type=type, path_exists=path_exists)
jinja_env.add_extension('jinja2.ext.do')
