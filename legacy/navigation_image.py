# -*- coding: utf-8 -*-
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
import logging
from pathlib import Path
from autologbook.containers import ResettableList

log = logging.getLogger('__main__')


class NavigationImagesList(ResettableList):
    """
    A subclass of resettable list to hold navigation images.

    The only difference between this subclass and a normal ResettableList
    is that we do a type check on append.

    Object added to the list must be either Path or string pointing to the navigation image path.
    When adding a Path, this is internally converted to a string.
    """

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def append(self, image: Path | str) -> None:
        """
        Append an item.

        Parameters
        ----------
        image: Path | str
        """
        if not isinstance(image, (Path, str)):
            raise TypeError('image must be Path or string')

        if isinstance(image, Path):
            image = str(image)
        else:
            image = image

        if image in self.data:
            log.warning('A navigation image with path %s already exists in the list' % image)
        else:
            super().append(image)

    def remove(self, image: Path | str) -> None:
        """
        Remove an image.

        Parameters
        ----------
        image: Path | str

        Returns
        -------

        """
        if not isinstance(image, (Path, str)):
            raise TypeError('image must be Path or string')

        if isinstance(image, Path):
            image = str(image)

        super().remove(image)
