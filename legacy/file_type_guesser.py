# -*- coding: utf-8 -*-
"""
Helper module to guess file types starting from filename and paths.

@author: Antonio Bulgheroni (antonio.bulgheroni@ec.europa.eu)

"""
# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2023. Antonio Bulgheroni.
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

import re
from enum import Enum
from pathlib import Path

import yaml

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'

yaml_file = Path(__file__).parent / Path('conf') / Path('type_guesser_regexp.yaml')


class RegexpRepository:

    class RegexpType(Enum):
        MATCH = 'MATCHING_PATTERNS'
        EXCLUDE = 'EXCLUDE_PATTERNS'

    def __init__(self):
        self.data = dict()

    @classmethod
    def from_yaml_file(cls, filename: str | Path) -> RegexpRepository:
        klass = cls()
        with open(filename, 'rt') as fp:
            klass.data = yaml.safe_load(fp)
        return klass

    def get(self, key: str, regexp_type: RegexpType, default=None):
        if key in self.data and regexp_type.value in self.data[key]:
            return self.data[key][regexp_type.value]
        else:
            return default

    def get_matching(self, key: str, default=None):
        return self.get(key, RegexpRepository.RegexpType.MATCH, default)

    def get_exclude(self, key: str, default=None):
        return self.get(key, RegexpRepository.RegexpType.EXCLUDE, default)

    def get_all(self, regexp_type: RegexpType) -> list | None:
        all_list = list()
        for key in self.data:
            new_list = self.get(key, regexp_type)
            if new_list is not None:
                all_list.extend(new_list)
        return all_list

    def get_all_matching(self):
        return self.get_all(RegexpRepository.RegexpType.MATCH)

    def get_all_exclude(self):
        return self.get_all(RegexpRepository.RegexpType.EXCLUDE)


# fill in the repository with all the data
regexp_repository = RegexpRepository.from_yaml_file(yaml_file)


class ElementTypeGuesser:
    """Helper class to guess the type of element starting from the filename."""

    def __init__(self, matching_patterns: str | re.Pattern | list[str],
                 exclude_patterns: str | re.Pattern | list[str] | None = None):
        """
        Build a ElementTypeGuesser.

        Parameters
        ----------
        matching_patterns : str, re.Pattern, list<str>
            A regular expression pattern for matching.
        exclude_patterns : str, re.Pattern, list<str>, None
            A regular expression pattern for exclusion.
            Set to None, to disable. The default is None.

        Returns
        -------
        None.

        """
        # check the input args
        if not isinstance(matching_patterns, (re.Pattern, str, list)):
            raise TypeError('matching_patterns must be a re.Pattern, a string or a list of string.')

        if exclude_patterns is not None:
            if not isinstance(exclude_patterns, (re.Pattern, str, list)):
                raise TypeError('exclude_patterns must be a re.Pattern, a string or a list of string.')

        # check the matching_patterns. this must be either a re.Pattern
        if not isinstance(matching_patterns, re.Pattern):
            if isinstance(matching_patterns, str):
                self.matching_patterns = re.compile(matching_patterns)
            if isinstance(matching_patterns, list):
                self.matching_patterns = re.compile(
                    '|'.join(matching_patterns))

        # check the exclude_patterns. this must be either a re.Pattern
        if exclude_patterns is not None:
            if not isinstance(exclude_patterns, re.Pattern):
                if isinstance(exclude_patterns, str):
                    self.exclude_patterns = re.compile(exclude_patterns)
                if isinstance(exclude_patterns, list):
                    self.exclude_patterns = re.compile(
                        '|'.join(exclude_patterns))
        else:
            self.exclude_patterns = None

    @classmethod
    def from_regexp_repository(cls, key: str) -> ElementTypeGuesser:
        return cls(regexp_repository.get_matching(key), regexp_repository.get_exclude(key))

    def _is_matching(self, element_path):

        if isinstance(element_path, Path):
            element_path = str(element_path)
        elif isinstance(element_path, str):
            element_path = element_path
        else:
            raise TypeError('element_path must be either str or Path')
        return self.matching_patterns.search(element_path)

    def _is_excluded(self, element_path):
        if self.exclude_patterns is None:
            return False
        if isinstance(element_path, Path):
            element_path = str(element_path)
        elif isinstance(element_path, str):
            element_path = element_path
        else:
            raise TypeError('element_path must be either str or Path')

        return self.exclude_patterns.search(element_path)

    def is_ok(self, element_path):
        """
        Check if the element_path is ok.

        A path is ok if it matches the matching pattern and if it is not
        excluded by the exclude pattern.

        Parameters
        ----------
        element_path : str | Path
            The path to be checked.

        Returns
        -------
        bool
            True if the element path is valid.

        """
        return self._is_matching(element_path) and not self._is_excluded(element_path)
