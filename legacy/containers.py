# -*- coding: utf-8 -*-
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


from collections import UserDict, UserList


class ResettableList(UserList):
    """
    A subclass of UserList to contain protocol items that could be reset.
    """

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def is_empty(self) -> bool:
        """
        Check if the list is empty.

        Returns
        -------
        bool:
            True if the list is empty.
        """
        return True if len(self.data) == 0 else False


class ResettableDict(UserDict):
    """A dictionary with a reset flag."""

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def is_empty(self) -> bool:
        """Check if the dictionary is empty."""
        return True if len(self.data) == 0 else False


class ContainerHelperMixin:

    def clear_resettable_content(self):
        """
        Reset the content of a protocol so that it can be reused.

        This method just empties the containers (samples and attachments), it does not remove other properties.

        Returns
        -------

        """
        for f in self.get_resettable_containers():
            f.clear()

    def is_empty(self, include_subsamples: bool = True) -> bool:
        """
        Check if a Sample is empty.

        A sample is considered empty when all its resettable containers are empty

        Returns
        -------
        bool
            True is the sample is empty.

        """

        empty = all([r.is_empty() for r in self.get_resettable_containers(include_subsamples)])
        return empty

    def get_resettable_containers(self, include_subsamples: bool = True) -> list[(ResettableDict | ResettableList)]:
        """
        Get all resettable containers.

        This method is returning a list of all resettable containers.

        Returns
        -------

        """
        res_list = []
        for resettable_element in dir(self):
            attribute = self.__getattribute__(resettable_element)
            if include_subsamples:
                if isinstance(attribute, (ResettableDict, ResettableList)):
                    res_list.append(attribute)
            else:
                if isinstance(attribute, (ResettableDict, ResettableList)):
                    if not resettable_element.startswith('subsamples'):
                        res_list.append(attribute)
        return res_list



