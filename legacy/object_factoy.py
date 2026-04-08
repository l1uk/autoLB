# -*- coding: utf-8 -*-
"""
A generic object factory design template to minimize code duplication.
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

import logging
from enum import Enum
from typing import TypeVar

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'

log = logging.getLogger('__main__')


class ObjectFactory:
    """ A generic object factory """

    T = TypeVar('T', bound=Enum | str | int)
    C = TypeVar('C', bound=object)

    def __init__(self):
        self._creators = dict()

    def register_type(self, object_type: T, object_class: type[C]):
        """
        Register a new type.

        Parameters
        ----------
        object_type: T
            The object type
        object_class: C
            A class corresponding to the object type
        """
        self._creators[object_type] = object_class

    def remove_type(self, object_type: T):
        """
        Remove a registered type.

        Parameters
        ----------
        object_type: T
            The object type to be removed.
        """
        if object_type in self._creators:
            del self._creators[object_type]
        else:
            log.warning('%s does not include support for %s' % (self.__name__, object_type))

    def edit_type(self, object_type: T, new_class: type[C]):
        """
        Edit a specific creator replacing its class with the new one.

        Parameters
        ----------
        object_type:
            The object type to be modified.
        new_class:
            The new class to be assigned to the object type.
        """
        if object_type in self._creators:
            self._creators[object_type] = new_class
        else:
            self.register_type(object_type, new_class)

    def get_registered_types(self) -> list[T]:
        """
        Get a list of the registered types.

        Returns
        -------
        list[T]:
            List of registered types.
        """
        return list(self._creators.keys())
