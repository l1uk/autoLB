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
from __future__ import annotations
from typing import Any
import logging
from pathlib import Path
from autologbook.html_helpers import HTMLHelperMixin
from autologbook.containers import ResettableDict
from autologbook import autoerror

log = logging.getLogger('__main__')


class Video(HTMLHelperMixin):
    """
    The basic class for a video clip.

    Video clips are rather common in microscopy analysis because they are very simple image sequence to show
    how a sample developed. For example in the case of a lamella preparation or of a pillar crashing.
    """

    def __init__(self, path: str | Path):
        """Generate a new Video with path"""
        # like for the MicrosocpePicture we use a dictionary to store all videos parameters.
        self.params = {}
        if isinstance(path, Path):
            self.params['key'] = str(path)
            self.params['path'] = path
        else:
            self.params['key'] = path
            self.params['path'] = Path(path)

        self.params['filename'] = self.get('path').name
        self.params['url'] = self.convert_path_to_uri(self.get('path'))
        self.params['ext'] = self.get('path').suffix
        self.get_video_info()

        self.template = 'video_base_template.yammy'

    def get(self, param: str) -> Any:
        """
        Return the value of a parameter.

        Parameters
        ----------
        param : str
            The name of the parameter to return

        Returns
        -------
        The value of the parameter or None if the parameter is not found.
        """
        return self.params.get(param, None)

    def set(self, param: str, value: Any):
        """
        Set the value of a parameter.

        Parameters
        ----------
        param : str
            The name of the parameter.
        value : Any
            The value of the parameter.
        """
        self.params[param] = value

    def get_video_info(self):
        """
        Retrieve video information from the file
        """
        if self.params['path'].exists():
            # get the information
            log.debug('Feature not completely implemented yet. For the moment it is not possible to get video '
                      'specific metadata')
            self.params['stat'] = self.get('path').stat()
            self.params['size'] = self.get('stat').st_size

    @property
    def key(self) -> str:
        """
        Get the video key to be used for the dictionary.

        Returns
        -------
        key: str
            The video key to be used for the dictionary
        """
        return self.get('key')

    @key.setter
    def key(self, value: Any):
        self.set('key', value)

    def update(self):
        """Update element after a file modification."""
        log.info('Updating video %s' % self.get('filename'))
        self.get_video_info()


class VideoDict(ResettableDict):
    """A dictionary of videos."""

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def add(self, video: str | Path | Video):
        """
        Add a video to the dictionary

        Parameters
        ----------
        video : str | Path | Video

        Raises
        ------
        TypeError: if video is not one of the accepted types.
        autoerror.DuplicatedKey: if adding another video with already used key

        Returns
        -------
        None
        """
        if not isinstance(video, (str | Path | Video)):
            raise TypeError('Video type must be Video, string or path-like')

        if not isinstance(video, Video):
            video = Video(video)

        if video.key in self.data.keys():
            raise autoerror.DuplicatedKey('Attempt to add another video with the same key %s' % video.key)
        else:
            self.data[video.key] = video

    def remove(self, video: Video | str | Path) -> None:
        """
        Remove a video from the dictionary

        Parameters
        ----------
        video : Video | str | Path
            The video to be removed.

        Raises
        ------
        TypeError: if video is not one of the acceptable types.

        Returns
        -------
        None.
        """
        if not isinstance(video, (Video, str, Path)):
            raise TypeError('Video type must be Video, string or path-like')

        if isinstance(video, Video):
            key = video.key
        else:
            key = str(video)

        if key in self.data:
            del self.data[key]
        else:
            log.warning('Attempt to remove %s from the video dictionary, but it was not there'
                        % key)
