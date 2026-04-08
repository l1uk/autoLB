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
from __future__ import annotations

import logging
from pathlib import Path

from autologbook import autoerror
from autologbook.attachment import Attachment, AttachmentDict
from autologbook.containers import ContainerHelperMixin, ResettableDict, ResettableList
from autologbook.microscope_picture import MicroscopePicDict, MicroscopePicture
from autologbook.optical_image import GenericOpticalImage, OpticalImageDict, optical_image_factory
from autologbook.protocol_editor_models import ElementType
from autologbook.qt_signal_dispatcher import SignalDispatcher
from autologbook.video import Video, VideoDict

log = logging.getLogger('__main__')


class Sample(ContainerHelperMixin):
    """
    The basic class for sample analysis.

    It contains a list of MicroscopePictures

    """

    def __init__(self, full_name: str):
        # This is the full name, meaning that the whole hierarchy up to the top
        # level is listed.
        #
        # Something like Sample1/SubSample1.2/ThisSubSample
        self.full_name = full_name

        # For sake of simplicity
        self.last_name = self.full_name.split('/')[-1]

        # The full_name contains the whole hierarchy, so actually the parent is
        # already know.
        #
        # According to the full_name, the parent should be
        # '/'.join(self.full_name.split('/')[:-1])
        self.parent = '/'.join(self.full_name.split('/')[:-1])
        if self.parent == '':
            self.parent = None

        # signal dispatcher
        self.signal_dispatcher = SignalDispatcher()

        # a list of subsamples
        # please use full_names!
        self.subsamples = ResettableList()

        # self.images is a dictionary
        self.images = MicroscopePicDict()

        # self.videos is a VideoDict
        self.videos = VideoDict()

        # self.attachments is an AttachmentDict
        self.attachments = AttachmentDict()

        # self.optical_images is an OpticalImageDict
        self.optical_images = OpticalImageDict()

        log.info('Created a new sample named %s' % self.full_name)

    def __repr__(self) -> str:
        """
        Return the canonical representation of a Sample.

        Returns
        -------
        str
            Canonical representation of a Sample.

        """
        return f'{self.__class__.__name__}("{self.full_name}")'

    def __str__(self) -> str:
        """
        Represent the Sample class.

        Returns
        -------
        msg : string
            The Sample class representation.

        """
        msg = (f'Sample {self.last_name} with parent {self.parent} contains \n'
               f'  + {len(self.subsamples)} subsample(s) \n')
        return msg

    def emit_added(self, element_type: ElementType, element_name: str, parent_name: str):
        """
        Cause the signal dispatcher to emit an added_element signal.

        Parameters
        ----------
        element_type : autotools.ElementType
            This enumerator contains all possible element types
        element_name : str
            In the case of MicroPic the element_name must be the
            full path of the added element.
        parent_name : str
            In the case of MicroPic, the parent_name is the sample full name.

        Returns
        -------
        None.

        """
        self.signal_dispatcher.added_element.emit(element_type, element_name, parent_name)

    def emit_removed(self, element_type: ElementType, element_name: str, parent_name: str):
        """
        Cause the signal dispatcher to emit a removed_element signal.

        Parameters
        ----------
        element_type : autotools.ElementType
            This enumerator contains all possible element types
        element_name : str
            In the case of MicroPic the element_name must be the
            full path of the removed element.
        parent_name : str
            In the case of MicroPic, the parent_name is the sample name.

        Returns
        -------
        None.

        """
        self.signal_dispatcher.removed_element.emit(element_type, element_name, parent_name)

    def add_microscope_picture(self, micro_pic: MicroscopePicture):
        """
        Add a microscope picture to the sample.

        The sample has a dictionary to store all the microscope pictures.
        The picture path is used as a key for the dictionary.

        Parameters
        ----------
        micro_pic : autoprotocol.MicroscopePicture
            The microscope picture to be added to the sample..

        Returns
        -------
        None.

        """
        try:
            self.images.add(micro_pic)
            micro_pic.params['anchor'] = f'{self.full_name}/{micro_pic.params["fileName"]}'
            self.emit_added(ElementType.MICROSCOPE_PIC, str(micro_pic.params['path']), self.full_name)
            log.info('Adding microscope picture (%s) to %s' % (micro_pic.params['fileName'], self.full_name))
            log.debug('At the moment there are %s pictures in the sample %s' % (len(self.images), self.full_name))
        except autoerror.DuplicatedKey as e:
            log.warning(e)

    def remove_microscope_picture_path(self, path: str | Path):
        """
        Remove a microscope picture using its path.

        Parameters
        ----------
        path : Path | string
            The full path of the microscope picture to be removed.

        Returns
        -------
        None.

        """
        if isinstance(path, Path):
            path = str(path)
        try:
            self.remove_microscope_picture(self.images[path])
        except KeyError:
            log.error('Could not find an image with the following path %s' % path)

    def remove_all_microscope_pictures(self):

        pic_list = [pic for pic in self.images.values()]
        for pic in pic_list:
            self.remove_microscope_picture(pic)

    def remove_microscope_picture(self, micro_pic: MicroscopePicture):
        """
        Remove a microscope picture from the sample.

        Parameters
        ----------
        micro_pic : autoprotocol.MicroscopePicture
            The microscope picture to be removed to the sample..

        Returns
        -------
        None.

        """
        if micro_pic.key in self.images:
            if micro_pic.getID() in MicroscopePicture._used_ids:
                MicroscopePicture._used_ids.remove(micro_pic.getID())
            else:
                log.warning('%s was not in the used_ids list.' % micro_pic.getID())
            log.info('Removed %s from sample %s' % (micro_pic.params['fileName'], self.full_name))
            log.debug('At the moment there are %s pictures in the sample %s' % (len(self.images), self.full_name))

            self._remove_file(micro_pic.params.get('pngfilename', None))
            self._remove_file(micro_pic.params.get('thumbfilename', None))
            self._remove_file(micro_pic.params.get('cropped_path', None))
            for file in micro_pic.params.get('pngfilename_list', []):
                self._remove_file(file)
            for file in micro_pic.params.get('thumbfilename_list', []):
                self._remove_file(file)

            self.emit_removed(ElementType.MICROSCOPE_PIC, str(micro_pic.params['path']), self.full_name)
            self.images.remove(micro_pic)
        else:
            log.warning('Attempt to remove %s from sample %s, but it was not there' % (
                micro_pic.params['fileName'], self.full_name))

    @staticmethod
    def _remove_file(path: str | Path | None):
        if path is None:
            return
        if isinstance(path, str):
            path = Path(path)

        if path.exists() and path.is_file():
            try:
                path.unlink()
            except IOError:
                log.warning('Not critical error removing auxiliary file %s' % path.name)

    def add_attachment(self, attachment: Attachment | str | Path):

        try:
            if not isinstance(attachment, Attachment):
                attachment = Attachment(attachment)
            self.attachments.add(attachment)
            attachment.params['anchor'] = f"{self.full_name}/{attachment.get('filename')}"
            self.emit_added(ElementType.ATTACHMENT_FILE, attachment.key, self.full_name)
            log.info('Adding attachment %s to the sample %s' % (attachment.get('filename'), self.full_name))
        except autoerror.DuplicatedKey as e:
            log.warning(e)

    def remove_all_attachments(self):
        elements = [element for element in self.attachments.values()]
        for element in elements:
            self.remove_attachment(element)

    def remove_attachment(self, attachment: Attachment | str | Path):
        if isinstance(attachment, Attachment):
            filename = attachment.get('filename')
            attachment = attachment.key
        elif isinstance(attachment, str):
            filename = Path(attachment).name
        elif isinstance(attachment, Path):
            filename = attachment.name
            attachment = str(attachment)

        self.attachments.remove(attachment)
        log.info('Removed %s from sample %s' % (filename, self.full_name))
        self.emit_removed(ElementType.ATTACHMENT_FILE, attachment, self.full_name)

    def add_video(self, video: Video | str | Path):
        """
        Add a video to the sample.

        The sample as a VideoDict to store all videos.

        Parameters
        ----------
        video: Video | str | Path
            The video to be added.

        Returns
        -------
        None
        """
        try:
            if not isinstance(video, Video):
                video = Video(video)
            self.videos.add(video)
            video.params['anchor'] = f'{self.full_name}/{video.get("filename")}'
            self.emit_added(ElementType.VIDEO_FILE, video.key, self.full_name)
            log.info('Adding video %s in the sample %s' % (video.get('filename'), self.full_name))
        except autoerror.DuplicatedKey as e:
            log.warning(e)

    def remove_all_videos(self):
        video_list = [video for video in self.videos.values()]
        for video in video_list:
            self.remove_video(video)

    def remove_video(self, video: Video | str | Path):
        """
        Remove a video from the sample

        Parameters
        ----------
        video: Video | str | Path
            The video to be removed.
        """
        if isinstance(video, Video):
            filename = video.get('filename')
            video = video.key
        elif isinstance(video, str):
            filename = Path(video).name
        elif isinstance(video, Path):
            filename = video.name
            video = str(video)

        self.videos.remove(video)
        log.info('Removed %s from sample %s' % (filename, self.full_name))
        self.emit_removed(ElementType.VIDEO_FILE, video, self.full_name)

    def add_optical_image(self, optical_image: GenericOpticalImage | str | Path):

        try:
            if not isinstance(optical_image, GenericOpticalImage):
                optical_image = optical_image_factory.get_optical_image(optical_image)
            self.optical_images.add(optical_image)
            optical_image.params['anchor'] = f"{self.full_name}/{optical_image.path.name}"
            self.emit_added(ElementType.OPTICAL_PIC, optical_image.key, self.full_name)
            log.info('Adding optical image %s to the sample %s' % (optical_image.path.name, self.full_name))
        except autoerror.DuplicatedKey as e:
            log.warning(e)

    def remove_all_optical_images(self):
        elements = [element for element in self.optical_images.values()]
        for element in elements:
            self.remove_optical_image(element)

    def remove_optical_image(self, optical_image: GenericOpticalImage | str | Path):
        if isinstance(optical_image, GenericOpticalImage):
            filename = optical_image.path.name
            optical_image = optical_image.key
        elif isinstance(optical_image, str):
            filename = Path(optical_image).name
        elif isinstance(optical_image, Path):
            filename = optical_image.name
            optical_image = str(optical_image)

        self.optical_images.remove(optical_image)
        log.info('Removed %s from sample %s' % (filename, self.full_name))
        self.emit_removed(ElementType.OPTICAL_PIC, optical_image, self.full_name)

    def add_subsample(self, child_sample_name: str | Sample):
        """
        Add a subsample reference to this sample.

        Parameters
        ----------
        child_sample_name: str | Sample
            This is the full name of the child sample.
            Instead of a string, one can provide also the sample itself.

        Raises
        ------
        autoerror.ParentSampleError:
            if the child full name is not matching the parent name.
        """
        if isinstance(child_sample_name, Sample):
            child_sample_name = child_sample_name.full_name

        # verify that the subsample full name is compatible with the
        # current sample full name.
        this_sample_full_name = '/'.join(child_sample_name.split('/')[0:-1])
        if this_sample_full_name != self.full_name:
            raise autoerror.ParentSampleError(
                'The subsample full not is not matching the parent name')

        if child_sample_name not in self.subsamples:
            self.subsamples.append(child_sample_name)

    def remove_subsample(self, child_sample: str | Sample):
        """Remove a subsample from the subsample list."""
        if isinstance(child_sample, Sample):
            child_sample = child_sample.full_name

        if child_sample in self.subsamples:
            self.subsamples.remove(child_sample)


class SampleDict(ResettableDict):
    """A dictionary of samples"""

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def add(self, sample: Sample | str):
        """
        Add a sample to the Sample dictionary.

        Parameters
        ----------
        sample : Sample | str
            The sample to be added.

        Returns
        -------

        """
        if not isinstance(sample, (Sample, str)):
            raise TypeError('Sample type must be Sample or string')

        if isinstance(sample, str):
            # if it is a str, just make a sample out of it.
            sample = Sample(sample)

        if sample.full_name in self.data:
            raise autoerror.SampleNameAlreadyExisting(
                f'Attempt to add another sample with the same key ({sample.full_name})')

        self.data[sample.full_name] = sample

    def remove(self, sample: Sample | str) -> None:
        """
        Remove a sample from the dictionary.

        Parameters
        ----------
        sample : Sample | str
            The sample that must be removed.

        Returns
        -------

        """
        if not isinstance(sample, (Sample, str)):
            raise TypeError('Sample type must be Sample or string')

        if isinstance(sample, Sample):
            key = sample.full_name
        else:
            key = sample

        if key in self.data:
            del self.data[key]
        else:
            log.warning('Attempt to remove %s from the sample dictionary, but it was not there' % key)
