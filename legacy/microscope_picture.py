# -*- coding: utf-8 -*-
"""Microscope image models and metadata handlers for autologbook.

This module provides the picture abstraction used to ingest, identify, enrich,
and render microscope images generated during SEM sessions. It centralizes
image metadata extraction, picture-ID management, PNG preview generation,
and calibration helpers used by the protocol rendering pipeline.

Main exported classes:
    - ``MicroscopePicture``: generic base class for all microscope images.
    - ``VegaPicture`` and ``VegaJPEGPicture``: TESCAN VEGA-specific handlers.
    - ``XL40Picture`` family: Philips XL40 handlers, including multi-frame and
      stage-aware variants.
    - ``FEIPicture`` family: FEI-derived handlers.

Relevant dependencies:
    - ``Pillow`` for image IO, TIFF tags, XMP and frame handling.
    - ``numpy`` for 16-bit intensity normalization when generating PNG images.
    - ``piexif`` and ``pickle`` for VEGA JPEG custom EXIF metadata.
    - Project modules such as ``autoconfig``, ``autotools``, ``autoerror``,
      and ``HTMLHelperMixin``.
"""
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

import configparser
import logging
import math
import os.path
import pickle
import random
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import piexif
import piexif.helper
from PIL import Image, ImageSequence

from autologbook import autoconfig, autoerror, autotools
from autologbook.autotools import PictureType, ResolutionSource, ResolutionUnit, VegaMetadataParser
from autologbook.containers import ResettableDict
from autologbook.html_helpers import HTMLHelperMixin
from autologbook.object_factoy import ObjectFactory

log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class MicroscopePicture(HTMLHelperMixin):
    """Base microscope image model.

    Subclass of ``HTMLHelperMixin`` that provides common storage and utility
    behavior for all microscope image types used by autologbook.

    Attributes:
        params (dict): Dynamic parameter store with image metadata and runtime
            fields used by HTML templates.
        template (str): Template name used to render the picture in protocols.
        _used_ids (list[int]): Class-level registry of IDs already assigned.
        _next_to_use_id (int): Next auto-generated ID candidate.

    Example:
        >>> pic = MicroscopePicture(path="/data/image.tif")
        >>> pic.get_type().name
        'GENERIC_MICROSCOPE_PICTURE'
    """

    # a class level list of all used ids
    _used_ids = list()

    # the next custom id to be used
    _next_to_use_id = autoconfig.CUSTOMID_START

    def __init__(self, path: Path | str = None, pic_type: PictureType = None, png_generation: bool = True,
                 *args, **kwargs):
        """Initialize a microscope picture instance.

        Args:
            path (Path | str | None): Source image path.
            pic_type (PictureType | None): Microscope/image type.
            png_generation (bool): If ``True``, generate PNG and thumbnail
                derivatives on construction.
            *args: Forwarded positional arguments.
            **kwargs: Forwarded keyword arguments.

        Raises:
            FileNotFoundError: If ``path`` is provided but does not exist.

        Example:
            >>> pic = MicroscopePicture("/tmp/001.tif", png_generation=False)
            >>> isinstance(pic.get_parameters(), dict)
            True
        """
        # initialize all the parameters dictionary
        self.params = dict()

        self.template = 'microscope_picture_base_template.yammy'

        if pic_type is None:
            self.params['pic_type'] = PictureType.GENERIC_MICROSCOPE_PICTURE
        else:
            self.params['pic_type'] = pic_type
        if path is not None:
            if os.path.exists(path):
                # TODO: replace all those paths with path-objects.
                self.params['path'] = path
                self.params['key'] = str(self.params.get('path'))
                self.params['fileName'] = os.path.split(path)[-1]
                self.params['fileExt'] = os.path.splitext(os.path.split(path)[-1])[1]
                self.params['id'] = ''
                self.params['tiffurl'] = self.convert_path_to_uri(path)
                log.info('Created a new MicroscopePicture (%s)' % self.params['fileName'])
                if png_generation:
                    self.params['thumbfile'] = self.generate_png(autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH, 'thumb-png',
                                                                 force_regen=False)
                    self.params['pngfile'] = self.generate_png(0, 'png', force_regen=False)
            else:
                raise FileNotFoundError(f'{path} not found')
        else:
            log.warning('Created a new MicroscopePicture without path')

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Static method to support the type guessing of the microscope picture factory.

        All subclasses need to reimplement this method in order to properly identify the image.

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """
        return True

    @staticmethod
    def _reset_ids():
        """
        Reset the used ids list (static method).

        Returns
        -------
        None.

        """
        MicroscopePicture._used_ids = []
        MicroscopePicture._next_to_use_id = autoconfig.CUSTOMID_START

    def __repr__(self) -> str:
        """
        Return the representation of a MicroscopePicture.

        Returns
        -------
        msg, str
            The representation of a MicroscopePicture.

        """
        return f'{self.__class__.__name__}(path=\"{self.params["path"]}\",pic_type={self.params["pic_type"]})'

    def __str__(self) -> str:
        """
        Print out the most relevant info of a MicroscopePicture.

        Returns
        -------
        msg : str
            The representation of a MicroscopePicture.

        """
        msg = 'Microscope Image with the following parameters\n'
        for key in self.params:
            msg += f'  - {key}: {self.params[key]}\n'
        return msg

    @staticmethod
    def _is_id_taken(pic_id: int) -> bool:
        """
        Check if an ID has been used already.

        Parameters
        ----------
        pic_id : int
            Identification number to be checked.

        Returns
        -------
        bool
            Return True if it is already used or
            False if the ID is good to be used.

        """
        if pic_id in MicroscopePicture._used_ids:
            return True
        return False

    def _get_id(self, pattern: str, tifftagcode: int | None = None):
        """
        Get a valid and unique MicroscopePicture ID.

        This method is retrieving a unique MicroscopePicture ID for the newly
        added image.

        It is getting an ID from the filename using a regular expression with
        the provided pattern and compare it with the ID stored in the TIFF file
        with the TIFF tag pointed by tifftagcode.

        Four different scenarios can happen:
            1. No valid ID is available in neither the filename nor in the TIFF
               tag. Then a valid one is internally generated and saved in the
               TIFF Tag for further use
            2. The ID from the filename is valid while the one from the TIFF tag
               is either empty or invalid. The one from the filename is accepted
               and saved to the TIFF tag for further use.
            3. The ID from the TIFF tag is good, but not the one from the
               filename. Just keep on using the one from TIFF tag.
            4. Both IDs are good. Then we take the one from the TIFF tag.

        Parameters
        ----------
        pattern : string
            Regular expression patter to identify the ID.
            See _get_id_from_filename for more details.
        tifftagcode : int, optional
            The code of the TIFF tag where the ID is located.
            If none, then the default value stored in autoconfig.CUSTOMID_TIFFCODE
            is used. The default is None.

        Returns
        -------
        None.

        """
        filename_id = self._get_id_from_filename(pattern)
        tifftag_id = self._get_id_from_tifftag(tifftagcode)
        need_file_flashing = False

        # Case 1
        if filename_id is None and tifftag_id is None:
            # it was not possible to get the ID neither from the filename
            # nor from the tifftag.
            # we need a fresh unique one

            good_id = self._get_unique_ID()
            need_file_flashing = True

        # Case 2
        elif filename_id is not None and tifftag_id is None:
            # we got an id from the filename but none from the tifftag.
            # for the sake of clarity write it to the file

            good_id = filename_id
            need_file_flashing = True

        # Case 3
        elif filename_id is None and tifftag_id is not None:
            # we got an id from the tifftag, but none from the filename
            # we can only take the one from the tifftag
            good_id = tifftag_id

        # Case 4
        else:  # if filename_id is not None and tifftag_id is not None:
            # we got id from both sources.
            # we will ignore the filename_id and consider the tifftag_id
            # valid
            good_id = tifftag_id

        self.params['id'] = good_id
        MicroscopePicture._used_ids.append(good_id)
        if need_file_flashing:
            self._write_id_in_file(ID=good_id, tifftagcode=tifftagcode)

    def _get_id_from_filename(self, pattern: str):
        r"""
        Try to get the ID from the filename using regular expression.

        This method must be always called by _get_id and will try to get a valid
        ID from the filename. To do so, it uses a regular expression pattern with
        a group named ID.

        For example this is a valid pattern: '^(?P<ID>[0-9]+)[\\w\\W]*$'.

        If a valid unique ID is found, it is returned for further use.
        None is returned if the pattern matching could not find any ID or
        if the matched ID is already in use.

        Parameters
        ----------
        pattern : str
            Regular expression pattern with a group named ID.
            An example is '^(?P<ID>[0-9]+)[\\w\\W]*$'

        Returns
        -------
        int or None
            The ID retrieved from the filename.
            If no ID is found or if it is already in use, None is returned

        """
        match = re.search(pattern, self.params['fileName'])
        if match:
            if MicroscopePicture._is_id_taken(int(match.group('ID'))):
                log.debug('ID %s taken from filename but already in use' %
                          match.group('ID'))
                return None
            else:
                return int(match.group('ID'))

    def _get_id_from_tifftag(self, tifftagcode: int = None):
        """
        Try to get the ID from the TIFF tag in the file.

        This method will try to get the picture ID from a TIFF tag stored in
        the TIFF file at position tifftagcode.

        If there is an ID at the indicated position and this is unique, then
        it is returned. Otherwise, None is returned.

        Parameters
        ----------
        tifftagcode : int, optional
            The code of the TIFF Tag where the ID is stored.
            If None, then the system level constant autoconfig.CUSTOMID_TIFFCODE
            is used.
            The default is None.

        Returns
        -------
        int or None
            The ID retrieved from the TIFF Tag.
            If no ID is found or if it is already in use, None is returned

        """
        if tifftagcode is None:
            tifftagcode = autoconfig.CUSTOMID_TIFFCODE
        with Image.open(self.get_parameter('path')) as img:
            if img.format.lower() != 'tiff':
                return None
            tiffinfo = img.tag_v2
            if tifftagcode in tiffinfo:
                try:
                    if MicroscopePicture._is_id_taken(int(tiffinfo[tifftagcode])):
                        log.warning('ID %s taken from TIFF tag already in use.'
                                    % int(tiffinfo[tifftagcode]))
                        log.warning('Removing TIFF tag from MicroscopePicture %s because of conflicts'
                                    % self.params['fileName'])
                        self._write_id_in_file(reset=True)
                        log.warning(
                            'Possible wrong assignments of HTML customization in the protocol')
                        return None
                    else:
                        return int(tiffinfo[tifftagcode])
                except ValueError:
                    log.warning(
                        'The content of the TIFF tag cannot be converted in a valid ID.')
                    log.warning('Resetting the TIFF tag')
                    self._write_id_in_file(reset=True)
                    return None
            else:
                return None

    @staticmethod
    def _get_unique_ID() -> int:
        """
        Obtain an internally generated unique ID.

        This is the last chance for the ID generation. If all other attempts
        are failing, then an internally generated ID is assigned.

        Returns
        -------
        Int
            A valid ID for the MicroscopePicture

        """
        while MicroscopePicture._is_id_taken(MicroscopePicture._next_to_use_id):
            MicroscopePicture._next_to_use_id += 1
        return MicroscopePicture._next_to_use_id

    # noinspection PyPep8Naming
    def _write_id_in_file(self, ID: int = None, tifftagcode: int = None, reset: bool = False):
        """
        Write/Update/Reset the ID in the TIFF Tag code with picture ID.

        This is the swiss army knife of the TIFF Tag picture ID.
        Using the PIL package it is opening the TIFF file, retrieving the
        tiffinfo dictionary with all the tags and writing/updating or
        resetting its value.
        The modified tiffinfo is saved to the original file.

        Parameters
        ----------
        ID : int, optional
            The id to be written to the TIFF file.
            If it is None, then the id stored in the MicroscopePicture is used.
            The default is None.
        tifftagcode : int, optional
            The code of the TIFF tag where the id has to be written.
            If None, then the system default autoconfig.CUSTOMID_TIFFCODE is used.
            The default is None.
        reset : bool, optional
            A boolean control to force the reset of the TIFF Tag.
            When True, instead of writing the id, an empty string is stored into
            the file.
            The default is False.

        Raises
        ------
        OSError
            Raised if the MicroscopePicture has no path defined. In this way
            the TIFF file cannot be opened.
        AttributeError
            Raised if id is None and the id in the MicroscopePicture parameter
            dictionary is not set.

        Returns
        -------
        None.

        """
        if self.params['path'] is None:
            raise OSError('Picture path not provided')

        if reset:
            write_id = ''
        else:
            if ID is None:
                if self.params['id'] is None:
                    raise AttributeError('Something went wrong with picture ID assignment')
                else:
                    write_id = self.params['id']
            else:
                write_id = ID

        if tifftagcode is None:
            tifftagcode = autoconfig.CUSTOMID_TIFFCODE

        if isinstance(self.params['path'], Path):
            img_path = self.params['path']
        else:
            img_path = Path(self.params['path'])

        with Image.open(img_path) as img:
            if img.format.lower() != 'tiff':
                return
            tiffinfo = img.tag_v2
            # this tag should not be existing, but check just in case
            if tifftagcode in tiffinfo:
                # this is unexpected
                # inform the user that the tag will be overwritten and lost
                log.warning('Microscope picture %s has already ID tag (%s).'
                            % (self.params['fileName'], tiffinfo[tifftagcode]))
                log.warning('It will be overwritten!')

            # add or modify with the id number
            tiffinfo[tifftagcode] = str(write_id)
            img.save(img_path, tiffinfo=tiffinfo)
        log.debug('ID stored in the TIFF tag for further use')

    # noinspection PyPep8Naming
    def getID(self) -> int:
        """
        Return the ID of the Microscope Picture.

        Returns
        -------
        ID
            The microscope picture ID.

        """
        return self.params['id']

    def get_type(self) -> PictureType:
        """
        Return the picture type.

        Returns
        -------
        pic_type : PictureType
            The type of picture.

        """
        return self.params['pic_type']

    def get_parameters(self) -> dict[Any]:
        """
        Return the picture parameter dictionary.

        Returns
        -------
        The whole parameter dictionary

        """
        return self.params

    def get_parameter(self, par_name: str) -> Any:
        """
        Return a specific parameter from the dictionary if it exists, None if it is not existing.

        Parameters
        ----------
        par_name : String
            Parameter Name.

        Returns
        -------
        The value of the parameter or None if it is not existing

        """
        return self.params.get(par_name, None)

    def generate_png(self, max_width: int = 400, subfolder: str = 'png-thumb', force_regen: bool = False) -> str:
        """
        Generate a PNG version of a Microscope Picture.

        Parameters
        ----------
        max_width : int, optional
            The horizontal size of the png image.
            Set to 0 to disable the scaling.
            The default is 400.
        subfolder : str, optional
            A relative directory to the sample where the generated PNG should be stored.
            The default is 'png-thumb'.
        force_regen : bool, optional
            Force the regeneration of a PNG image even if it exists already.
            The default is False.

        Returns
        -------
        thumbfile : str
            The URI of the generated PNG file.

        """
        # save the file in a subfolder defined by subfolder
        # make the folder if it doesn't exist
        thumbpath = os.path.join(os.path.split(self.params['path'])[0], subfolder)
        if not os.path.exists(thumbpath):
            os.mkdir(thumbpath)
        thumbfilename = os.path.splitext(os.path.split(self.params['path'])[-1])[0] + '-{}.png'.format(subfolder)
        thumbfile = os.path.join(thumbpath, thumbfilename)

        # TODO: having these parameters set here is a bit confusing. Since the function is returning the path
        #       of the newly generated png file, we should assign the filename and the url outside the call.
        #       Have a look at all calls to this method and see if we can simply return a tuple (path, uri) and
        #       assign it outside.
        if max_width == 0:
            self.params['pngfilename'] = thumbfile
            self.params['pngurl'] = self.convert_path_to_uri(thumbfile)
        else:
            self.params['thumbfilename'] = thumbfile
            self.params['thumburl'] = self.convert_path_to_uri(thumbfile)
            self.params['thumb_max_width'] = max_width

        if not force_regen and os.path.exists(thumbfile):
            log.debug('Skipping the generation of PNG for %s because already existing' %
                      self.params['fileName'])

        else:
            if max_width == 0:
                log.debug('Converting image %s in PNG format' %
                          self.params['fileName'])
            else:
                log.debug('Generating thumbnail of %s with max_width %s' % (
                    self.params['fileName'], max_width))
            try:
                with Image.open(self.params['path'], 'r') as image:
                    w, h = image.size
                    log.debug('Image size %s x %s' % (w, h))
                    if image.format == 'TIFF' and image.mode == 'I;16':
                        log.debug('Handling of 16bit image')
                        array = np.array(image)
                        normalized = (array.astype(np.uint16) - array.min()) * 255.0 / (array.max() - array.min())
                        image = Image.fromarray(normalized.astype(np.uint8))
                    image = image.convert('RGB')
                    if max_width > 0:
                        image.thumbnail(
                            (round(max_width), round(max_width * h / w)))
                    image.save(thumbfile, format='PNG')
            except Exception as e:
                log.exception(e)
                raise autoerror.UnableToOpenMicroscopePicture

        thumbfile = self.convert_path_to_uri(thumbfile)
        thumbfile = thumbfile.replace('\\', '/')

        return thumbfile

    @property
    def key(self) -> str | None:
        """Key property to be used in the dictionary"""
        return self.params.get('key', None)

    @key.setter
    def key(self, value) -> None:
        self.params['key'] = value

    def update(self):
        """
        Update Microscope Picture information.

        This method is invoked by the autowatchdog when a modification event for a microscope picture is processed.

        For the base class, this corresponds to regenerate the png files.
        """
        log.info('Updating microscope picture %s' % self.params['fileName'])
        self.params['pngfile'] = self.generate_png(0, 'png', force_regen=True)
        self.params['thumbfile'] = self.generate_png(autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH, 'thumb-png',
                                                     force_regen=True)

    def calibrate(self):
        """Abstract method to be reimplemented by subclass"""
        pass


class FakePicture(MicroscopePicture):

    def __init__(self):
        # initialize all the parameters dictionary
        self.params = dict()
        self.params['pic_type'] = PictureType.GENERIC_MICROSCOPE_PICTURE
        self.params['path'] = f'{datetime.now():%Y%m%d%H%M%S%f}_{random.randint(0, 100)}'
        self.params['fileName'] = self.params['path']


class VegaPicture(MicroscopePicture):
    """
    The microscope picture from VEGA microscope.

    This class is used only for TIFF version, JPEG images will have to use VEGAJPEGPicture.
    """

    filename_pattern = '(?P<ID>[0-9]+)[\\w\\W]*$'
    microscope_name = 'TS5130LS'

    def __init__(self, path: str | Path, pic_type: PictureType = PictureType.VEGA_MICROSCOPE_PICTURE,
                 png_generation: bool = True, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        self.template = 'vega_microscope_picture_base_template.yammy'
        if not isinstance(path, Path):
            path = Path(path)
        self.retrieve_metadata()

        picture_folder = path.parent
        picture_name_wo_extension = path.stem
        hdr_filename = picture_name_wo_extension + '-' + path.suffix.lstrip('.') + '.hdr'
        self.params['hdr_file_path'] = picture_folder / Path(hdr_filename)
        self.params['thumb_rowspan'] = 4
        self._get_id(self.filename_pattern)

        if autoconfig.VEGA_AUTO_CALIBRATION:
            self.calibrate()

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Implementation of the proper identification of VegaPicture.

        To identify a VegaPicture, a VegaMetadataParser is created using the metadata
        in the file. If the microscope model contained in the metadata is equal to the
        bound microscope_name attribute, then it can be confirmed that this picture is
        from Vega.

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """

        try:
            parser = VegaMetadataParser.from_tag_dictionary(image.tag_v2)
            microscope = parser.parse_single_metadata('microscope')
            return microscope == VegaPicture.microscope_name
        except autoerror.InvalidMetadata:
            return False

    def retrieve_metadata(self):
        """
        Collect metadata from the file.

        This method is opening the file using PIL and the TIFF metadata are used to initialize a VegaMetadataParser.
        This parser will collect all the relevant information from there and store them in the parameter dictionary.
        """

        with Image.open(self.params['path']) as tif:
            x, y = tif.size
            self.params['pixel_x'] = x
            self.params['pixel_y'] = y

            parser = VegaMetadataParser.from_tag_dictionary(tif.tag_v2)
            parsed = parser.parse_all()

            for key, value in parsed.items():
                self.params[key] = value

        tif.close()

    def calibrate(self):
        """
        Perform spatial calibration on Vega picture.

        It uses the horizontal and vertical pixel size.
        """

        # I'm not sure why I have written this line here
        if self.get_type() != PictureType.VEGA_MICROSCOPE_PICTURE:
            return

        required_params = ['pixel_size_x', 'pixel_size_y']
        if not all([param in self.params.keys() for param in required_params]):
            log.debug('Missing parameters to calibrate %s' % self.params['fileName'])
            return

        with Image.open(self.params['path']) as img:
            xres = 0.01 / self.params['pixel_size_x']
            yres = 0.01 / self.params['pixel_size_y']
            ures = ResolutionUnit.CM
            # pic_res = autotools.PictureResolution(xres, yres, ures)
            if img.format == 'TIFF':
                tiff_tags = img.tag_v2
                img.save(self.params['path'], resolution_unit=ures, x_resolution=xres, y_resolution=yres,
                         tiffinfo=tiff_tags)
            elif img.format == 'JPEG':
                log.warning('It is not possible to calibrate JPEG images. Please use TIFF')
            else:
                log.warning('Only TIFF files can be calibrated')

    def update(self):
        """Reimplement the update method for Vega pictures."""
        super().update()
        if autoconfig.VEGA_AUTO_CALIBRATION:
            self.calibrate()


class VegaJPEGPicture(MicroscopePicture):
    """
    Implementation of the MicroscopePicture for the JPEG version of the Vega pictures.

    This picture class is not automatically identified the guessing function of the microscope picture factory.
    """
    filename_pattern = '(?P<ID>[0-9]+)[\\w\\W]*$'

    def __init__(self, path: str | Path, pic_type: PictureType = PictureType.VEGA_JPEG_MICROSCOPE_PICTURE,
                 png_generation: bool = True, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        log.warning('The use of JPEG images for analytical purposes is highly discourage. Use TIFF, please')
        if not isinstance(path, Path):
            path = Path(path)

        # there is no other way that getting metadata from the header file
        picture_folder = path.parent
        picture_name_wo_extension = path.stem
        hdr_filename = picture_name_wo_extension + '-' + path.suffix.lstrip('.') + '.hdr'
        self.params['hdr_file_path'] = picture_folder / Path(hdr_filename)
        self.params['thumb_max_width'] = autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH
        self.has_metadata = False
        self._get_id(self.filename_pattern, autoconfig.VEGA_JPEG_ID_CODE)
        self.retrieve_metatada()
        if self.has_metadata:
            self.template = 'vega_microscope_picture_jpeg_full_template.yammy'
            self.params['thumb_rowspan'] = 4
        else:
            self.template = 'vega_microscope_picture_jpeg_simple_template.yammy'
            self.params['thumb_rowspan'] = 1

    def retrieve_metatada(self):
        """
        Collect metadata from the file.

        To retrieve the metadata from the JPEG file, the piexif module is used.
        The custom metadata are stored in the MakerNote.

        """
        with Image.open(self.params['path']) as img:
            x, y = img.size
            self.params['pixel_x'] = x
            self.params['pixel_y'] = y
        img.close()

        exif_dict = piexif.load(str(self.params['path']))
        self.has_metadata = False
        if 'Exif' in exif_dict:
            if piexif.ExifIFD.MakerNote in exif_dict['Exif']:
                my_metadata = pickle.loads(exif_dict['Exif'][piexif.ExifIFD.MakerNote])
                if 'metadata_version' not in my_metadata:
                    return

                if 'MAIN' in my_metadata.keys():
                    self.params['protocol'] = str(my_metadata['MAIN'].get('Sign', ''))
                    self.params['note'] = str(my_metadata['MAIN'].get('Note', ''))
                    self.params['magnification'] = float(my_metadata['MAIN'].get('Magnification', 0))
                    self.params['pixel_size_x'] = float(my_metadata['MAIN'].get('PixelSizeX', 0))
                    self.params['pixel_size_y'] = float(my_metadata['MAIN'].get('PixelSizeY', 0))

                if 'SEM' in my_metadata.keys():
                    self.params['vacuum'] = float(my_metadata['SEM'].get('ChamberPressure', 0))
                    self.params['detector'] = str(my_metadata['SEM'].get('Detector', ''))
                    self.params['dwell_time'] = float(my_metadata['SEM'].get('DwellTime', 0))
                    self.params['scan_mode'] = str(my_metadata['SEM'].get('ScanMode', ''))
                    self.params['scan_rotation'] = float(my_metadata['SEM'].get('ScanRotation', 0))
                    self.params['scan_speed'] = float(my_metadata['SEM'].get('ScanSpeed', 0))
                    self.params['emission_current'] = float(my_metadata['SEM'].get('EmissionCurrent', 0))
                    self.params['HV'] = float(my_metadata['SEM'].get('HV', 0))
                    self.params['specimen_current'] = float(my_metadata['SEM'].get('SpecimenCurrent', 0))
                    self.params['spot_size'] = float(my_metadata['SEM'].get('SpotSize', 0))
                    self.params['stage_r'] = float(my_metadata['SEM'].get('StageRotation', 0))
                    self.params['stage_t'] = float(my_metadata['SEM'].get('StageTilt', 0))
                    self.params['stage_x'] = float(my_metadata['SEM'].get('StageX', 0))
                    self.params['stage_y'] = float(my_metadata['SEM'].get('StageY', 0))
                    self.params['stage_z'] = float(my_metadata['SEM'].get('StageZ', 0))
                    self.params['WD'] = float(my_metadata['SEM'].get('WD', 0))

                self.has_metadata = True

    def _get_id_from_tifftag(self, tifftagcode: int = None):
        """
        Try to get the ID from the TIFF tag in the file.

        This method will try to get the picture ID from a TIFF tag stored in
        the TIFF file at position tifftagcode.

        If there is an ID at the indicated position and this is unique, then
        it is returned. Otherwise, None is returned.

        Parameters
        ----------
        tifftagcode : int, optional
            The code of the TIFF Tag where the ID is stored.
            If None, then the system level constant autoconfig.CUSTOMID_TIFFCODE
            is used.
            The default is None.

        Returns
        -------
        int or None
            The ID retrieved from the TIFF Tag.
            If no ID is found or if it is already in use, None is returned

        """
        if tifftagcode is None:
            tifftagcode = autoconfig.VEGA_JPEG_ID_CODE

        exif_dict = piexif.load(self.params['path'])
        if tifftagcode not in exif_dict['Exif']:
            return None
        try:
            return int(piexif.helper.UserComment.load(exif_dict['Exif'][tifftagcode]).encode('utf-8'))
        except ValueError:
            return None

    def _write_id_in_file(self, ID: int = None, tifftagcode: int = None, reset: bool = False):

        # TODO: Check why this part of the code was disabled.

        # if self.params['path'] is None:
        #     raise OSError('Picture path not provided')
        #
        # if reset:
        #     write_id = ''
        # else:
        #     if ID is None:
        #         if self.params['id'] is None:
        #             raise AttributeError('Something went wrong with picture ID assignment')
        #         else:
        #             write_id = self.params['id']
        #     else:
        #         write_id = ID
        #
        # if tifftagcode is None:
        #     tifftagcode = autoconfig.VEGA_JPEG_ID_CODE
        #
        # exif_dict = dict()
        # exif_dict['Exif'] = dict()
        # exif_dict['Exif'][tifftagcode] = piexif.helper.UserComment.dump(str(write_id))
        # piexif.insert(piexif.dump(exif_dict), str(self.params['path']))

        return

    def update(self):
        """Reimplement the update method for VEGA JPEG Picture."""
        super().update()
        self.retrieve_metatada()
        if self.has_metadata:
            self.template = 'vega_microscope_picture_jpeg_full_template.yammy'
            self.params['thumb_rowspan'] = 4
        else:
            self.template = 'vega_microscope_picture_jpeg_simple_template.yammy'
            self.params['thumb_rowspan'] = 1


class XMPMixin:
    """Mixin class to implement some xmp related functions."""

    @staticmethod
    def find_xmp_element(xmp_data: dict, element_name: str) -> dict | None:
        """
        Search the xmp metadata dictionary for a specific key named element_name. If found, it is returned.

        Parameters
        ----------
        xmp_data: dict
            The xmp metadata structure to be parsed.
        element_name: str
            The name of the element to be searched in the xmp dictionary.

        Returns
        -------
        A dictionary with the part of the original xmp_data containing the researched element or None if the element is
        not found in the dictionary.
        """
        requested_element = None
        try:
            for xmp_dict in xmp_data['xmpmeta']['RDF']['Description']:
                if element_name in xmp_dict:
                    requested_element = xmp_dict
                    break
        except (KeyError, IndexError):
            log.warning('Unexpected XMP structure')
        finally:
            return requested_element


class XL40Picture(XMPMixin, MicroscopePicture):
    """The microscope picture generated from the Philips XL40 microscope"""

    # typical file name '123456.tif'
    filename_pattern = r'(?P<ID>[0-9]+)\.[Tt][Ii][Ff]+$'
    tiff_tag_software_pattern = '|'.join([r'Digital Image Processing System [\d+\.]*',
                                          r'point electronic DISS [\d+\.]*'])

    def __init__(self, path: str | Path, pic_type: PictureType = PictureType.XL40_MICROSCOPE_PICTURE,
                 png_generation: bool = False, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        self._get_id(self.filename_pattern)
        try:
            self.update()
        except:  # noqa: E722
            # for some obscure reasons, the opening of XL40 images is sometime problematic.
            # in case it fails, a solution is to recopy the original file.
            # just raise a ForceRemirroring exception
            raise autoerror.ForceRemirroring

        self.template = 'xl40_microscope_picture_single_template.yammy'

        if autoconfig.XL40_AUTO_CALIBRATION:
            self.calibrate()

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Implementation of the proper identification of XL40Picture.

        To identify a XL40Picture, the following checks are performed:
        - The name of software stored in the TIFF Tags has to match the expected pattern.
        - Check if the TIFF file contains XMP metadata
        - Check if minimal information (pixel sizes) are available in the XMP data structure

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """

        try:
            software_ok = re.match(XL40Picture.tiff_tag_software_pattern, image.tag_v2[305])
            xmp = image.getxmp()
            if xmp:
                return all([software_ok, XL40Picture._has_minimal_info(image)])
        except KeyError:
            return False

    @staticmethod
    def _is_multiframe(image: Image) -> bool:
        """
        Check if the image has multiple frames.

        Parameters
        ----------
        image: PIL.Image
            The image object being checked.

        Returns
        -------
        bool:
            True if more than one frame is saved in the TIFF file.
        """
        return image.n_frames > 1

    @staticmethod
    def _has_stage_info(image: Image) -> bool:
        """
        Check if the image has stage information in the XMP metadata.

        Parameters
        ----------
        image: PIL.Image
            The image object being checked.

        Returns
        -------
        bool:
            True if the image metadata contain stage information.
        """
        xmp = image.getxmp()
        if xmp:
            return bool(XL40Picture.find_xmp_element(xmp, 'X'))
        else:
            return False

    @staticmethod
    def _has_minimal_info(image: Image) -> bool:
        """
        Check if the image has minimal information in the XMP metadata

        Parameters
        ----------
        image: PIL.Image
            The image object being checked.

        Returns
        -------
        bool:
            True if the image contains minimal information.
        """
        return bool(XL40Picture.find_xmp_element(image.getxmp(), 'PixelSizeX'))

    def _get_id(self, pattern: str, tifftagcode: int | None = None):
        filename_id = self._get_id_from_filename(pattern)

        if filename_id is None:
            good_id = self._get_unique_ID()
        else:
            good_id = filename_id

        self.params['id'] = good_id
        MicroscopePicture._used_ids.append(good_id)

    def update(self):
        """
        Reimplement the update method for the XL40Picture
        """
        self.retrieve_metadata()
        self.generate_png(autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH, 'thumb-png', force_regen=False)
        self.generate_png(0, 'png', force_regen=False)

    def retrieve_metadata(self):
        """Collect the metadata from XMP structure stored in the file."""
        with Image.open(self.params['path']) as tif:
            x, y = tif.size
            self.params['pixel_x'] = x
            self.params['pixel_y'] = y

            # XL40 images can be multiframe
            self.params['n_frames'] = tif.n_frames

            # sometimes the XL40 is saving stage information.
            # but not this time. checking for it costs time, so we assume that the factory guess was correct
            self.params['has_stage_info'] = False

            # we take the information from the first frame
            tif.seek(0)
            xmp = tif.getxmp()
            if 'xmpmeta' not in xmp.keys():
                return

            image_element = self.find_xmp_element(xmp, 'PixelSizeX')
            if image_element:
                self.params['pixel_size_x'] = image_element['PixelSizeX']
                self.params['pixel_size_y'] = image_element['PixelSizeY']
                # there are cases in which the scan name is not there. Just ignore.
                self.params['scan_name'] = image_element.get('ScanName', 'Unknown')

                signal_sources = list()
                signal_sources.append(image_element['Images']['Seq']['li'].get('SignalName', 'Unknown'))
                self.params['signal_sources'] = signal_sources

            sem_element = self.find_xmp_element(xmp, 'WD')
            if sem_element:
                self.params['WD_value'] = sem_element['WD']['value']
                self.params['WD_um'] = sem_element['WD']['Unit']
                hv_alternatives = ['HV', 'GunHV']
                for hv in hv_alternatives:
                    if hv in sem_element:
                        self.params['HV_value'] = sem_element[hv]['value']
                        self.params['HV_um'] = sem_element[hv]['Unit']
                        break
                self.params['magnification'] = sem_element['Mag']

            description_element = self.find_xmp_element(xmp, 'description')
            if description_element:
                self.params['user_text'] = description_element['description']['Alt']['li'][0]['text']

            if 'user_text' not in self.params.keys():
                self.params['user_text'] = ''

        tif.close()
        self.params['thumb_rowspan'] = 2

    def get_stage_information(self, xmp: dict):
        """
        Get the stage information from the xmp dictionary and store it in the param object.

        Parameters
        ----------
        xmp: dict
            xmp metadata from where the stage information are recovered.
        """
        stage_element = self.find_xmp_element(xmp, 'X')

        for coord in ['X', 'Y', 'Z', 'S', 'Tilt', 'Rotation']:
            self.params[f'stage_{coord.lower()}'] = stage_element[coord]['value']
            if coord == 'Tilt':  # there is a bug in the metadata!
                self.params[f'stage_{coord.lower()}_um'] = '°'
            else:
                self.params[f'stage_{coord.lower()}_um'] = stage_element[coord]['Unit']
        self.params['has_stage_info'] = True

    def generate_png(self, max_width: int = 400, subfolder: str = 'png-thumb', force_regen: bool = False) -> str:
        """
        Reimplement the generation of PNG thumbnails for XL40

        The specificity here is the capability to generate more than PNG file for multiframe input.

        Parameters
        ----------
        max_width : int, optional
            The horizontal size of the png image.
            Set to 0 to disable the scaling.
            The default is 400.
        subfolder : str, optional
            A relative directory to the sample where the generated PNG should be stored.
            The default is 'png-thumb'.
        force_regen : bool, optional
            Force the regeneration of a PNG image even if it exists already.
            The default is False.

        Returns
        -------
        thumbfile : str
            The URI of the generated PNG file.
        """
        paths = list()
        urls = list()
        if self.params['n_frames'] == 1:
            super(XL40Picture, self).generate_png(max_width, subfolder, force_regen)
            if max_width == 0:
                self.params['pngfilename_list'] = [self.params['pngfilename'], ]
                self.params['pngurl_list'] = [self.params['pngurl'], ]
            else:
                self.params['thumbfilename_list'] = self.params['thumbfilename']
                self.params['thumburl_list'] = self.params['thumburl']
        else:
            with Image.open(self.params['path'], 'r') as image:

                dest_path = Path(self.params['path']).parent / Path(subfolder)
                dest_path.mkdir(parents=True, exist_ok=True)
                for iframe, frame in enumerate(ImageSequence.Iterator(image)):

                    dest_file = dest_path / Path(
                        Path(self.params['path']).stem + '-' + self.params['signal_sources'][iframe]
                        + '-' + subfolder + '.png')

                    if not force_regen and dest_file.exists():
                        log.debug(
                            'Skipping the generation of PNG for %s because already existing' % self.params['fileName'])
                    else:
                        if max_width == 0:
                            log.debug('Converting image %s in PNG format' % self.params['fileName'])
                        else:
                            log.debug(
                                'Generating thumbnail of %s with max_width %s' % (self.params['fileName'], max_width))

                        frame.seek(iframe)
                        w, h = image.size
                        log.debug('Image size %s x %s' % (w, h))
                        if frame.format == 'TIFF' and frame.mode == 'I;16':
                            log.debug('Handling of 16bit image')
                            array = np.array(frame)
                            normalized = (array.astype(np.uint16) - array.min()) * 255.0 / (array.max() - array.min())
                            frame = Image.fromarray(normalized.astype(np.uint8))
                        converted_image = frame.convert('RGB')
                        if max_width > 0:
                            converted_image.thumbnail((round(max_width), round(max_width * h / w)))
                        converted_image.save(dest_file, format='PNG')

                    paths.append(str(dest_file))
                    urls.append(self.convert_path_to_uri(dest_file))
            image.close()

            if max_width == 0:
                self.params['pngfilename_list'] = paths
                self.params['pngurl_list'] = urls
                self.params['pngfilename'] = paths[0]
                self.params['pngurl'] = urls[0]
            else:
                self.params['thumbfilename_list'] = paths
                self.params['thumburl_list'] = urls
                self.params['thumbfilename'] = paths[0]
                self.params['thumburl'] = urls[0]
                self.params['thumb_max_width'] = max_width

    def calibrate(self):
        """Reimplement the calibrate method for XL40 Pictures."""
        # if the pixel size information are missing. just leave now
        if not all([key in self.params.keys() for key in ['pixel_size_x', 'pixel_size_y']]):
            return

        frame_list = list()
        xres = 0.01 / float(self.params['pixel_size_x'])
        yres = 0.01 / float(self.params['pixel_size_y'])
        ures = ResolutionUnit.CM

        # it's complicated
        #
        # 1. we need to split the original image frames in single images.
        #    for this, we use temporary files.
        with Image.open(self.params['path']) as img:
            for i, frame in enumerate(ImageSequence.Iterator(img)):
                tiffinfo = frame.tag_v2
                output_file = tempfile.TemporaryFile()
                frame.save(output_file, format='TIFF', x_resolution=xres, y_resolution=yres, resolution_unit=ures,
                           tiffinfo=tiffinfo)
                frame_list.append(output_file)
        img.close()

        # 2. prepare a list of items to be closed
        image_list = list()

        # 3. we open the first layer
        with Image.open(frame_list[0]) as img:
            for i, file in enumerate(frame_list):
                if i != 0:
                    # the first one is already open
                    with Image.open(file) as image:
                        image.load()
                        image_list.append(image)

            tiffinfo = img.tag_v2
            img.save(self.params['path'], format='TIFF', save_all=True, append_images=image_list, x_resolution=xres,
                     y_resolution=yres, resolution_unit=ures, tiffinfo=tiffinfo)

        # 4. close all open images
        for image in image_list:
            image.close()

        # 5. close also the first one
        img.close()

        # 6. close (and delete) the temporary files
        for file in frame_list:
            file.close()


class XL40MultiFramePicture(XL40Picture):
    """Subclass of XL40Picture with multiple frames."""

    def __init__(self, path: str | Path, pic_type: PictureType = PictureType.XL40_MULTIFRAME_MICROSCOPE_PICTURE,
                 png_generation: bool = False, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        self.template = 'xl40_microscope_picture_multi_template.yammy'

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Reimplement the guessing helper function for XL40MultiFramePicture

        In order to be identified as XL40MultiFramePicture, this should be first of all an XL40Picture and it must have
        multiple layers.

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True if the image is recognized as XL40MultiFramePicture
        """
        return super(XL40MultiFramePicture, XL40MultiFramePicture)._am_i_right(path, image) and \
            super(XL40MultiFramePicture, XL40MultiFramePicture)._is_multiframe(image)

    def retrieve_metadata(self):
        """Reimplement the retrieve metadata in order to add multi layer properties."""
        super().retrieve_metadata()
        with Image.open(self.params['path']) as tif:
            # we scan all frames and get the source signal for all of them
            signal_sources = list()
            for frame in range(self.params['n_frames']):
                tif.seek(frame)
                image_element = self.find_xmp_element(tif.getxmp(), 'PixelSizeX')
                signal_sources.append(image_element['Images']['Seq']['li']['SignalName'])
            self.params['signal_sources'] = signal_sources
            self.params['thumb_rowspan'] = 2
        tif.close()


class XL40MultiFrameWithStageInfoPicture(XL40MultiFramePicture):
    """Subclass of XL40MultiFramePicture to include stage information."""

    def __init__(self, path: str | Path,
                 pic_type: PictureType = PictureType.XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE,
                 png_generation: bool = False, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Reimplement the guessing helper function for XL40MultiFrameWithStageInfoPicture

        In order to be identified as XL40MultiFrameWithStagePicture, this should be first of all an XL40Picture,
        it must have multiple layers and includes stage information.

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True if the image is recognized as XL40MultiFrameWithStageInfoPicture
        """
        return all(
            [XL40Picture._am_i_right(path, image),
             XL40Picture._is_multiframe(image),
             XL40Picture._has_stage_info(image)]
        )

    def retrieve_metadata(self):
        """Reimplement the retrieve metadata in order to add stage information."""
        super().retrieve_metadata()
        with Image.open(self.params['path']) as tif:
            self.params['thumb_rowspan'] = 4
            xmp = tif.getxmp()
            # now get the stage information
            self.get_stage_information(xmp)
        tif.close()


class XL40WithStageInfoPicture(XL40Picture):
    """Subclass of XL40Picture to include stage information"""

    def __init__(self, path: str | Path,
                 pic_type: PictureType = PictureType.XL40_WITH_STAGE_MICROSCOPE_PICTURE,
                 png_generation: bool = False, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Implementation of the proper identification of XL40WithStageInfoPicture.

        In order to be identified as XL40MultiFrameWithStagePicture, this should be first of all an XL40Picture and
        includes stage information.

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """
        return all(
            [XL40Picture._am_i_right(path, image),
             XL40Picture._has_stage_info(image)]
        )

    def retrieve_metadata(self):
        """Retrieve the metadata including the stage information."""
        super().retrieve_metadata()
        with Image.open(self.params['path']) as tif:
            self.params['thumb_rowspan'] = 3
            xmp = tif.getxmp()
            # now get the stage information
            self.get_stage_information(xmp)
        tif.close()


class FEIPicture(MicroscopePicture):
    """
    The basic FEI pictures.

    All relevant parameters for the logbook are taken from the tiff tags and
    inserted in the parameter dictionary.

    """

    def __init__(self, path: str | Path | None = None, pic_type: PictureType = PictureType.FEI_MICROSCOPE_PICTURE,
                 png_generation: bool = True, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        if path is not None:
            try:
                self.get_tiff_file_tags()
                self.template = 'fei_microscope_picture_template.yammy'
                self.params['thumb_rowspan'] = 4
                if autoconfig.FEI_AUTO_CALIBRATION:
                    self.calibrate()
                if autoconfig.FEI_DATABAR_REMOVAL:
                    self.crop_databar()
            except autoerror.NotFEIMicroscopePicture:
                log.warning('Expected FEI Image, but could not find FEI metadata.')
                log.warning('Was the TIFF file copied before being patched by the XT software?')
                self.params['pic_type'] = PictureType.GENERIC_MICROSCOPE_PICTURE
                self.template = 'microscope_picture_base_template.yammy'

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Implementation of the proper identification of FEIPicture.

        To identify a FEIPicture, the following checks are performed:
        - At least one custom field from FEI should be included.

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """
        try:
            tiff_tags = image.tag_v2
        except AttributeError:
            return False

        good_fei_tag_code = None
        for fei_tag_code in autotools.FEITagCodes:
            if fei_tag_code in tiff_tags:
                good_fei_tag_code = fei_tag_code
                break

        return bool(good_fei_tag_code)

    def calibrate(self):
        """
        Calibrate the FEI image.

        Resolution information stored in standard TIFF tags of FEI images are
        wrong. In order to have a direct calibration of the image while being
        open with ImageJ for example, the information provided in the FEI
        specific tag must be used.

        This method getting the picture resolution from the standard tags and
        comparing it with the one obtained with the FEI tags. If the two are
        different, then it means that this image was never calibrated before.
        Calibration information from FEI tags are moved to the standard tags.
        The picture file is updated and saved.

        If the two sets of resolution are the same, then there is no need to
        perform any calibration.

        Returns
        -------
        None.

        """
        if self.get_type() not in [
            PictureType.FEI_MICROSCOPE_PICTURE,
            PictureType.VERSA_MICROSCOPE_PICTURE,
            PictureType.QUATTRO_MICROSCOPE_PICTURE
        ]:
            return

        log.debug('Calibrating %s' % self.params['fileName'])
        with Image.open(self.params['path']) as tif:
            missing_tiff_res = False
            missing_fei_res = False

            tiff_tags = tif.tag_v2
            try:
                tif_res = autotools.get_picture_resolution(tiff_tags, ResolutionSource.TIFF_TAG, ResolutionUnit.CM)
            except ValueError:
                log.warning('Unable to read the resolution from the TIFF tags')
                missing_tiff_res = True

            try:
                fei_res = autotools.get_picture_resolution(tiff_tags, ResolutionSource.FEI_TAG, ResolutionUnit.CM)
            except ValueError:
                log.warning('Unable to read the resolution from the FEI tags')
                missing_fei_res = True

            if missing_fei_res:
                log.warning('Unable to perform the calibration, leaving file unchanged.')
                return

            if not missing_tiff_res:
                if tif_res == fei_res:
                    # both resolution information are present and are equal. So we just leave the file unchanged.
                    return
                else:
                    # the two are different, then we take the fei_res and we write it to the file
                    xres, yres, ures = fei_res.as_tuple()
                    tif.save(self.params['path'], resolution_unit=ures, x_resolution=xres, y_resolution=yres,
                             tiffinfo=tiff_tags)
            else:
                # the tiff_res is missing, but the fei_res is there.
                # so we just take the fei_res and we write it to the file.
                xres, yres, ures = fei_res.as_tuple()
                tif.save(self.params['path'], resolution_unit=ures, x_resolution=xres, y_resolution=yres,
                         tiffinfo=tiff_tags)

    def crop_databar(self, force_regen: bool = False):
        """
        Remove the databar from a FEI picture.

        FEI microscopes are saving a databar on the bottom part of the image
        containing user selected information.

        While this databar is generally very useful, it is not nice to see when
        the image is published on a scientific journal.

        This method allows to remove the databar saving the cropped image in
        a separated file in order to keep also the original.

        The cropped file is saved in the picture parameter:
            params['cropped_path'] with the full path including the filename
            params['cropped_url'] URL of the cropped image as it appears on the
                image server.

        Parameters
        ----------
        force_regen : bool, optional
            Force the regeneration of the cropped image even if it exists already.
            The default is False.

        Returns
        -------
        None.

        """
        if self.get_type() not in [
            PictureType.FEI_MICROSCOPE_PICTURE,
            PictureType.VERSA_MICROSCOPE_PICTURE,
            PictureType.QUATTRO_MICROSCOPE_PICTURE
        ]:
            return

        # Check if the cropped file already exists.
        orig_path = Path(self.params['path'])
        crop_img_path = orig_path.parent / \
            Path('crop') / Path(str(orig_path.stem) + '_crop' + str(orig_path.suffix))
        self.params['cropped_path'] = crop_img_path
        self.params['cropped_url'] = self.convert_path_to_uri(crop_img_path)
        if not crop_img_path.parent.exists():
            crop_img_path.parent.mkdir(parents=True, exist_ok=True)

        if not force_regen and crop_img_path.exists():
            log.debug(
                'Skipping generation of cropped image because it already exists')
            return

        log.debug('Generating a copy of %s with cropped databar' %
                  self.params['fileName'])
        self._remove_databar(orig_path, crop_img_path)

    def _remove_databar(self, input_file, output_file):

        with Image.open(input_file) as full_img:
            tiffinfo = full_img.tag_v2
            image_xsize, image_ysize = full_img.size

            fei_metadata = configparser.ConfigParser(allow_no_value=True, strict=False)
            fei_metadata.read_string(tiffinfo[self.params['fei_tag_code']])

            scan_width = fei_metadata.getint('Image', 'ResolutionX')
            scan_height = fei_metadata.getint('Image', 'ResolutionY')

            if (image_xsize, image_ysize) != (scan_width, scan_height):
                crop_img = full_img.crop((0, 0, scan_width, scan_height))
                xside_code = 256
                yside_code = 257
                tiffinfo[xside_code] = scan_width
                tiffinfo[yside_code] = scan_height

                crop_img.save(output_file, tiffinfo=tiffinfo)

    def get_tiff_file_tags(self):
        """
        Get the TIFF file tags.

        Open the tiff file corresponding to the FEI picture using the PIL
        and get the fei_metadata dictionary.

        Relevant information for the logbook are transferred from the fei_metadata
        to the internal dictionary.

        The magnification is calculated starting from the display width and the
        horizontal field of view.

        Raises
        ------
        TypeError
            If the TIFF file is not a FEI image.

        Returns
        -------
        None.

        """
        path = self.params['path']

        with Image.open(path) as tif:

            tiff_tags = tif.tag_v2
            good_fei_tag_code = None
            for fei_tag_code in autotools.FEITagCodes:
                if fei_tag_code in tiff_tags:
                    good_fei_tag_code = fei_tag_code
                    break
            if good_fei_tag_code is None:
                raise autoerror.NotFEIMicroscopePicture
            else:
                self.params['fei_tag_code'] = good_fei_tag_code

            fei_metadata = configparser.ConfigParser(allow_no_value=True, strict=False)
            fei_metadata.read_string(tiff_tags[good_fei_tag_code])

            # for HV add kV if > 1000
            self.params['hv'] = (
                fei_metadata.get('Beam', 'HV') + 'V',
                str(round(fei_metadata.getfloat('Beam', 'HV') / 1000)) + 'kV'
            )[fei_metadata.getfloat('Beam', 'HV') > 1000]

            self.params['beam'] = fei_metadata.get('Beam', 'Beam')
            self.params['hfw'] = fei_metadata.getfloat(self.params['beam'], 'HFW')
            self.params['magnificationmode'] = fei_metadata.getint('Image', 'Magnificationmode', fallback='2')
            self.params['screenmagnificationmode'] = fei_metadata.getint('Image', 'Screenmagnificationmode',
                                                                         fallback='2')
            self.params['magcanvasrealwidth'] = fei_metadata.getfloat('Image', 'magcanvasrealwidth', fallback='0.41440')
            self.params['screenmagcanvasrealwidth'] = fei_metadata.getfloat('Image', 'screenmagcanvasrealwidth',
                                                                            fallback='0.41440')
            if self.params['magnificationmode'] == 3:
                self.params['magdivider'] = 2.
            else:
                self.params['magdivider'] = 1.
            try:
                self.params['dispwidth'] = fei_metadata.getfloat('System', 'DisplayWidth')
                # for magnification there is a mystery 1.25 scale factor
                self.params['magnification'] = autotools.pretty_fmt_magnification(
                    float(self.params['dispwidth']) / float(self.params['hfw']) / 1.25 / self.params['magdivider']
                )

            except ValueError:
                self.params['dispwidth'] = 'Unknown'
                self.params['magnification'] = 'Unknown'

            self.params['spotsize'] = fei_metadata.getfloat('Beam', 'Spot')
            try:
                self.params['beamcurrent'] = fei_metadata.getfloat(
                    self.params['beam'], 'beamcurrent')
            except ValueError:
                # in case of an image taken with switched off beam the current is an empty string.
                # causing the getfloat to fail.
                self.params['beamcurrent'] = 0
            self.params['detector'] = f"{fei_metadata.get('Detectors', 'Mode')}.{fei_metadata.get('Detectors', 'Name')}"
            self.params['vacuum'] = fei_metadata.get('Vacuum', 'UserMode')
            self.params['userText'] = fei_metadata.get('User', 'UserText')
            self.params['width'] = fei_metadata.getfloat('Image', 'ResolutionX')
            self.params['height'] = fei_metadata.getfloat('Image', 'ResolutionY')
            self.params['resolution'] = (fei_metadata.getfloat('Image', 'ResolutionX'),
                                         fei_metadata.getfloat('Image', 'ResolutionY'))
            self.params['resolutionPrint'] = \
                f"({fei_metadata['Image']['ResolutionX']} x {fei_metadata['Image']['ResolutionY']})"
            self.params['stage_x'] = fei_metadata.getfloat('Stage', 'StageX')
            self.params['stage_y'] = fei_metadata.getfloat('Stage', 'StageY')
            self.params['stage_z'] = fei_metadata.getfloat('Stage', 'StageZ')
            self.params['stage_r'] = math.degrees(fei_metadata.getfloat('Stage', 'StageR'))
            self.params['stage_t'] = math.degrees(fei_metadata.getfloat('Stage', 'StageT'))
            self.params['working_distance'] = fei_metadata.getfloat('Stage', 'WorkingDistance')
            self.params['scan'] = fei_metadata.get('Beam', 'Scan')
            self.params['dwell_time'] = fei_metadata.getfloat(self.params['scan'], 'Dwell')
            self.params['frame_time'] = fei_metadata.getfloat(self.params['scan'], 'FrameTime')
            self.params['frame_average'] = fei_metadata.getint('Scan', 'Average')
            self.params['frame_integration'] = fei_metadata.getint('Scan', 'Integrate')
            self.params['line_integration'] = fei_metadata.getint(self.params["scan"], 'LineIntegration')
            self.params['scan_interlacing'] = fei_metadata.getint(self.params["scan"], 'ScanInterlacing')

        for key in self.params:
            log.debug('%s  --> %s' % (key, self.params[key]))

    @staticmethod
    def _get_system_type(image: Image) -> str | None:
        """Get the system name from the image metadata."""
        tiff_tags = image.tag_v2
        good_fei_tag_code = None
        for fei_tag_code in autotools.FEITagCodes:
            if fei_tag_code in tiff_tags:
                good_fei_tag_code = fei_tag_code
                break
        if good_fei_tag_code is None:
            return None

        fei_metadata = configparser.ConfigParser(allow_no_value=True, strict=False)
        fei_metadata.read_string(tiff_tags[good_fei_tag_code])

        return fei_metadata.get('System', 'SystemType', fallback=None)

    def update(self):
        """
        Update the parameters of an FEI Microscope picture.

        This method is calling its super method and then update the tiff tags, calibration and databar removal.

        """
        super().update()
        try:
            self.get_tiff_file_tags()
            if autoconfig.FEI_AUTO_CALIBRATION:
                self.calibrate()
            if autoconfig.FEI_DATABAR_REMOVAL:
                self.crop_databar()
        except autoerror.NotFEIMicroscopePicture:
            log.error('Expected FEI Image, but could not find FEI metadata. Please double check saving format.')
            self.params['pic_type'] = PictureType.GENERIC_MICROSCOPE_PICTURE


class QuattroFEIPicture(FEIPicture):
    """
    Quattro Pictures, a subclass of FEI.

    Quattro images should be named according to this convention:

        id-samplename-someproperties.tif

    The name file is parsed against a regular expression and the picture id is stored
    in the parameters' dictionary.

    """

    filename_pattern = '^(?P<ID>[0-9]+)[\\w\\W]*$'
    system_type = 'Quattro S'

    def __init__(self, path: str | Path | None = None, pic_type: PictureType = PictureType.QUATTRO_MICROSCOPE_PICTURE,
                 png_generation: bool = True, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        if path is not None:
            self._get_id(self.filename_pattern)

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Implementation of the proper identification of FEIPicture.

        To identify a FEIPicture, the following checks are performed:
        - At least one custom field from FEI should be included.
        - The System tag should match 'Quattro S'

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """
        return super(QuattroFEIPicture, QuattroFEIPicture)._am_i_right(path, image) and \
            super(QuattroFEIPicture, QuattroFEIPicture)._get_system_type(image) == QuattroFEIPicture.system_type


class VersaFEIPicture(FEIPicture):
    """
    Versa Pictures, a subclass of FEI.

    Quattro images should be named according to this convention:

        samplename-someproperties_id.tif

    The name file is parsed against a regular expression and the picture id is stored
    in the parameters' dictionary.

    """

    # (?P<name>...)
    # sometext-000.tif
    # sometext_000.tif
    filename_pattern = '^[\\w\\W]*[-_](?P<ID>[0-9]+).[\\w\\W]*$'
    system_type = 'Versa 3D'

    def __init__(self, path: str | Path | None = None, pic_type: PictureType = PictureType.VERSA_MICROSCOPE_PICTURE,
                 png_generation: bool = True, *args, **kwargs):
        super().__init__(path, pic_type, png_generation, *args, **kwargs)
        if path is not None:
            self._get_id(VersaFEIPicture.filename_pattern)

    @staticmethod
    def _am_i_right(path: str | Path, image: Image) -> bool:
        """
        Implementation of the proper identification of FEIPicture.

        To identify a FEIPicture, the following checks are performed:
        - At least one custom field from FEI should be included.
        - The System tag should match 'Versa 3D'

        Parameters
        ----------
        path: str | Path
            Path of the picture, it is provided here in the case the decision on the type
            requires to see the image path.

        image: PIL.Image
            An image object. It is provided to avoid opening and closing the file
            multiple times.

        Returns
        -------
        bool:
            True, if from the information recovered from the file confirm that this
            microscope picture is of the right type.
        """
        return super(VersaFEIPicture, VersaFEIPicture)._am_i_right(path, image) and \
            super(VersaFEIPicture, VersaFEIPicture)._get_system_type(image) == VersaFEIPicture.system_type


class MicroscopePicDict(ResettableDict):
    """A subclass of resettable dictionary specialized for microscope images."""

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def add(self, image: MicroscopePicture):
        """
        Add a MicroscopePicture to the dictionary.

        Parameters
        ----------
        image: MicroscopePicture
            Element to be added.

        """
        if not isinstance(image, MicroscopePicture):
            raise TypeError('Only microscope pictures can be added to the image dictionary.')
        if image.key is None:
            # it is a picture without a path.
            # it cannot be added to the dictionary
            raise KeyError('Impossible to add a picture without path')
        if image.key in self.data.keys():
            # log.warning('Attempt to add another image with the same key (%s) to the dictionary.' % image.key)
            raise autoerror.DuplicatedKey(
                'Attempt to add another image with the same key (%s) to the dictionary.' % image.key)
        else:
            self.data[image.key] = image

    def remove(self, image: MicroscopePicture | str) -> None:
        """
        Remove a MicroscopePicture from the dictionary.

        Parameters
        ----------
        image: MicroscopePicture | str
            The element to be removed, it can either be the element itself, or its key.
        """
        if isinstance(image, MicroscopePicture):
            key = image.key
        elif isinstance(image, str):
            key = image
        else:
            raise TypeError(
                'image can only be a MicroscopePicture or a string')
        if key not in self.data.keys():
            log.warning(
                'Attempt to remove an image (%s) not found in the dictionary' % key)
        else:
            del self.data[key]


class MicroscopePictureFactory(ObjectFactory):
    """ The microscope picture factory"""

    def guess_type(self, path: str | Path) -> PictureType:
        """
        Guess the type of microscope picture.

        The image is opened using PIL, and it is passed to the _am_i_right method of all registered creators. Only the
        first matching type is returned. For this reason, the other in which the creators are added is extremely
        important. If, for example, the generic picture would be added as first, all pictures will be associated to
        the generic picture because its _am_i_right method is returning always True.

        Parameters
        ----------
        path: str | Path
            The path of the picture the type of which is being guessed.

        Returns
        -------
        PictureType:
            The type of the image.
        """
        with Image.open(path) as image:
            good_type = PictureType.GENERIC_MICROSCOPE_PICTURE
            for type_, class_ in self._creators.items():
                if class_._am_i_right(path, image):
                    good_type = type_
                    break
        image.close()
        return good_type

    def create_object(self, path: str | Path, object_type: PictureType = None, *args, **kwargs) -> MicroscopePicture:
        """
        Create a microscope picture from path.

        In order to create the proper microscope picture implementation, the user can provide the picture type or let
        the factory guess it. All other positional and keyword arguments are directly passed to the microscope
        picture initialize method.

        Parameters
        ----------
        path: str | Path
            The path of the microscope picture being created.
        object_type: PictureType | None
            The type of MicroscopePicture. If None, the factory will guess the type

        Other Parameters
        ----------------
        args, kwargs
            Passed directly to the microscope picture constructor.

        Returns
        -------
        MicroscopePicture:
            A microscope picture of the correct type.
        """
        if object_type is None:
            object_type = self.guess_type(path)
        if object_type in self._creators:
            return self._creators[object_type](path, *args, **kwargs)
        else:
            log.warning('%s is not supported by the factory. Returning the generic object')
            return MicroscopePicture(path)


microscope_picture_factory = MicroscopePictureFactory()

# the order is very important, always start from the most specialized to the least
microscope_picture_factory.register_type(PictureType.QUATTRO_MICROSCOPE_PICTURE, QuattroFEIPicture)
microscope_picture_factory.register_type(PictureType.VERSA_MICROSCOPE_PICTURE, VersaFEIPicture)
microscope_picture_factory.register_type(PictureType.FEI_MICROSCOPE_PICTURE, FEIPicture)
microscope_picture_factory.register_type(PictureType.XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE,
                                         XL40MultiFrameWithStageInfoPicture)
microscope_picture_factory.register_type(PictureType.XL40_MULTIFRAME_MICROSCOPE_PICTURE,
                                         XL40MultiFramePicture)
microscope_picture_factory.register_type(PictureType.XL40_WITH_STAGE_MICROSCOPE_PICTURE,
                                         XL40WithStageInfoPicture)
microscope_picture_factory.register_type(PictureType.XL40_MICROSCOPE_PICTURE, XL40Picture)
microscope_picture_factory.register_type(PictureType.VEGA_MICROSCOPE_PICTURE, VegaPicture)
microscope_picture_factory.register_type(PictureType.GENERIC_MICROSCOPE_PICTURE, MicroscopePicture)
