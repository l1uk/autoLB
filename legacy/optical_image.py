# -*- coding: utf-8 -*-
"""
Implementation of the optical image module and its factory.

Alongside microscope picture, another important element of the analysis protocol are the so-called optical images.
Those are either optical microscope images or more in general optical images describing the sample(s), the sample
setup or any other detail the user consider to be relevant.

While microscope picture are generally saved in TIFF format, optical images are in JPEG, with their metadata saved
using ExifTags.

This module defines a generic class for optical images and a series of subclasses specialized for different image types.

Inside the protocol, the optical images are stored inside a dedicated container (OpticalImageDict) at the protocol
level and also at the sample level.

An instance of a dedicated factory can be used to guess the subtype of an image and to create the corresponding object.
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

import logging
from pathlib import Path
from typing import Any

import piexif
from PIL import ExifTags, Image

from autologbook import autoconfig, autoerror
from autologbook.autotools import OpticalImageType, ResolutionUnit, pretty_print_dict
from autologbook.containers import ResettableDict
from autologbook.html_helpers import HTMLHelperMixin
from autologbook.object_factoy import ObjectFactory

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'

log = logging.getLogger('__main__')

orientation_value = {
    1: '0 degrees',
    2: '0 degrees, mirrored',
    3: '180 degrees',
    4: '180 degrees, mirrored',
    5: '90 degrees',
    6: '90 degrees, mirrored',
    7: '270 degrees',
    8: '270 degrees, mirrored'
}


class GenericOpticalImage(HTMLHelperMixin):
    """
    Generic optical image.

    Following the same concept of the Microscope Picture, this class represents the generic implementation of an optical
    image element. It includes the functionalities of the HTMLHelperMixin.

    All new subclasses need to implement / extend the retrieve metadata method and to define the jinja2 template file to
    be used for the HTML rendering.

    In the basic implementation the retrieve metadata is actually performing three actions:

    1.  Basic information that should always be present in the file irrespectively of the image format and of the way
    the image was generated,

    2.  Get the whole metadata from the exif fields and transfer it to the _raw_metadata attribute as a dictionary

    3.  Process the raw metadata, that means transferring all raw metadata in the param object using their
    official tag name as dictionary key and preparing some extended information for a simpler HTML render.

    """

    def __init__(self, path: str | Path):
        super().__init__()
        self.params = dict()
        self._raw_metadata = None
        self.params['path'] = Path(path)
        self.params['filename'] = self.params['path'].name
        self.params['url'] = self.convert_path_to_uri(path)
        self.params['key'] = str(path)
        self.params['thumb_rowspan'] = 1
        self.params['thumb_max_width'] = autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH
        self._type = OpticalImageType.GENERIC_OPTICAL_IMAGE
        self.retrieve_metadata()
        self.template = 'optical_image_base_template.yammy'

    @property
    def key(self) -> str:
        """The key property used for OpticalImageDict."""
        return self.params['key']

    @property
    def path(self) -> Path:
        """The path of the object"""
        return self.params['path']

    @path.setter
    def path(self, path: str | Path):
        self.params['path'] = Path(path)

    def get_parameter(self, param_key: str, default_value: Any = None) -> Any:
        """
        Get a parameter identified by the string param_key.

        All image parameters are stored in a dictionary and can be retrieved by their key using this method. In case
        a key is not found, a default_value can be specified.

        This method will not throw an exception if an entry with the specified key is not found.

        Parameters
        ----------
        param_key: str
            The key used to store the parameter value in the dictionary.
        default_value: Any | None
            It is returned in case an entry corresponding to the specified key is not found.

        Returns
        -------
        Any:
            The value of the requested parameter or the default value if not found.
            In case no default value is specified and the parameter is not found, None is returned.
        """
        if param_key in self.params:
            return self.params[param_key]
        else:
            return default_value

    def print_metadata(self):
        """Print the metadata dictionary."""
        pretty_print_dict(self.params)

    def retrieve_metadata(self):
        """
        Retrieve the metadata from the image.

        In the specific case, three private methods are invoked to:
            1. Retrieve basic information
            2. Retrieve the raw metadata
            3. Process the raw metadata.
        """
        with Image.open(self.path) as img:
            img.load()
            self._retrieve_basic_info(img)
            self._retrieve_raw_metadata(img)
            self._process_raw_metadata()

        img.close()

    def update(self):
        """
        Update the image.

        This method is called by the update call back of the autowatchdog. In this specific case, the method is
        collecting the metadata.
        """
        self.retrieve_metadata()

    def _retrieve_basic_info(self, img: Image):
        self.params['format'] = img.format
        self.params['x_pixel'], self.params['y_pixel'] = img.size

    def _retrieve_raw_metadata(self, img: Image):
        self._raw_metadata = dict(img.getexif())

    def _process_raw_metadata(self):
        for key, value in self._raw_metadata.items():
            self.params[ExifTags.TAGS.get(key, key)] = value
        self.params['Resolution'] = f"{self.params.get('XResolution', '0')} x {self.params.get('YResolution', '0')} " \
                                    f"{ResolutionUnit.inverse_resolution_unit(ResolutionUnit(self.params.get('ResolutionUnit', 1)))} "
        self.params['MP'] = float(self.params.get('x_pixel', 0)) * float(self.params.get('y_pixel', 0)) / 1000000
        self.params['Orientation_str'] = orientation_value.get(self.params.get('Orientation', 1), '0 degrees')


class DigitalCameraOpticalImage(GenericOpticalImage):
    """A digital camera subclass of the generic optical image."""

    def __init__(self, path: str | Path):
        super().__init__(path)
        self._type = OpticalImageType.DIGITAL_CAMERA_OPTICAL_IMAGE
        self.retrieve_metadata()
        self.params['thumb_rowspan'] = 2
        self.template = 'digital_camera_optical_image_template.yammy'


class KeyenceMicroscopeImage(GenericOpticalImage):
    """An image generated by the Keyence microscope."""

    def __init__(self, path: str | Path):
        super().__init__(path)
        self._type = OpticalImageType.KEYENCE_OPTICAL_IMAGE
        self.retrieve_metadata()
        self.params['thumb_rowspan'] = 2
        self.template = 'keyence_optical_image_template.yammy'


class DigitalCameraOpticalImageWithGPS(DigitalCameraOpticalImage):
    """A digital camera with GPS information."""

    def __init__(self, path: str | Path):
        super().__init__(path)
        self._type = OpticalImageType.DIGITAL_CAMERA_OPTICAL_IMAGE_WITH_GPS
        self.params['thumb_rowspan'] = 3
        self.template = 'digital_camera_optical_image_gps_template.yammy'

    def retrieve_metadata(self):
        """
        Retrieve the metadata.

        This method is the reimplementation of the generic class adding the capability to retrieve and decode the GPS
        information stored in the metadata.
        """
        with Image.open(self.path) as img:
            img.load()
            self._retrieve_basic_info(img)
            self._retrieve_raw_metadata(img)
            self._retrieve_gps_metadata(img)
            self._process_raw_metadata()

        img.close()

    def _retrieve_gps_metadata(self, img):
        exif_dict = piexif.load(img.info.get('exif'))
        gps_info = dict()

        gps_key = 'GPS'
        codec = 'UTF-8'
        for tag in exif_dict[gps_key]:
            try:
                element = exif_dict[gps_key][tag].decode(codec)
            except AttributeError:
                element = exif_dict[gps_key][tag]

            gps_info[piexif.TAGS[gps_key][tag]['name']] = element

        self.params['GPSINFO'] = gps_info
        self.params['GPSLatitude'] = self.decode_gps('latitude', gps_info)
        self.params['GPSLongitude'] = self.decode_gps('longitude', gps_info)
        self.params['GPSAltitude'] = self.decode_gps('altitude', gps_info)

    @staticmethod
    def decode_gps(what: str, gps_info: dict) -> str:
        """
        Static method to decode the GPS information.

        Parameters
        ----------
        what: str
            The name of the parameter to be decoded. Possible values are:
            Latitude, Longitude and Altitude.
        gps_info: dict
            The GPS dictionary as retrieved from the metadata.

        Returns
        -------
        A formatted string with the required value.
        """
        if what.lower() == 'latitude':
            ref_key = 'GPSLatitudeRef'
            val_key = 'GPSLatitude'
        elif what.lower() == 'longitude':
            ref_key = 'GPSLongitudeRef'
            val_key = 'GPSLongitude'
        elif what.lower() == 'altitude':
            ref_key = 'GPSAltitudeRef'
            val_key = 'GPSAltitude'
        else:
            ref_key = ''
            val_key = ''

        if ref_key not in gps_info and val_key not in gps_info:
            return 'Unknown'

        card = gps_info[ref_key]

        if what.lower() in ['latitude', 'longitude']:
            val = [n / d for n, d in gps_info[val_key]]
            return f'{card} {val[0]}° {val[1]}\' {val[2]}\"'
        else:
            val = gps_info[val_key][0] / gps_info[val_key][1]
            return f'{val} m'


class OpticalImageFactory(ObjectFactory):
    """
    Optical image factory.

    Subclass of the generic ObjectFactory.

    This class is responsible to generate optical images of the correct type.
    """

    def get_optical_image(self, path: str | Path, image_type: OpticalImageType = None) -> GenericOpticalImage:
        """
        Generate an optical image object.

        Parameters
        ----------
        path: str | Path
            The path to the optical image
        image_type: OpticalImageType | None
            The type of the optical image or None. If None is provided, then the guess type method of the factory is
            invoked.

        Returns
        -------
        A GenericOpticalImage or one of its subclasses.
        """
        if image_type is None:
            image_type = self.guess_type(path)
        if image_type == OpticalImageType.INVALID_OPTICAL_IMAGE:
            raise autoerror.InvalidOpticalImageError(path)
        return self._creators[image_type](path)

    @staticmethod
    def guess_format(path: str | Path) -> str:
        """
        Guess the format of the image.

        Instead of guessing from the file extension, the image is opened with Pillow and its format is then returned.

        Parameters
        ----------
        path: str | Path
            The path of the image

        Returns
        -------

        """
        with Image.open(path) as image:
            f = image.format
        image.close()
        return f

    @staticmethod
    def guess_type_of_jpeg(image: Image) -> OpticalImageType:
        """
        Guess image type specific for JPEG format.

        Parameters
        ----------
        image: Image

        Returns
        -------
        The guessed image type.
        """
        image_type = OpticalImageType.GENERIC_OPTICAL_IMAGE
        try:
            exif = piexif.load(image.info['exif'])
            if piexif.ExifIFD.MakerNote in exif['Exif'] and exif['Exif'][piexif.ExifIFD.MakerNote][
                    :7] == b'KmsFile':
                image_type = OpticalImageType.KEYENCE_OPTICAL_IMAGE
            elif 'GPS' in exif and exif['GPS'] != {} and piexif.ImageIFD.Make in exif['0th']:
                image_type = OpticalImageType.DIGITAL_CAMERA_OPTICAL_IMAGE_WITH_GPS
            elif piexif.ImageIFD.Make in exif['0th']:
                if exif['0th'][piexif.ImageIFD.Make] == b'TESCAN':
                    image_type = OpticalImageType.INVALID_OPTICAL_IMAGE
                else:
                    image_type = OpticalImageType.DIGITAL_CAMERA_OPTICAL_IMAGE
            else:
                image_type = OpticalImageType.GENERIC_OPTICAL_IMAGE
        except KeyError:
            # there are not exif info, but still we can get some info from the app.
            if any('VH' in str(v) for v in image.app.values()):
                image_type = OpticalImageType.KEYENCE_OPTICAL_IMAGE
            else:
                image_type = OpticalImageType.GENERIC_OPTICAL_IMAGE
        finally:
            return image_type

    @staticmethod
    def guess_type_of_png(image: Image) -> OpticalImageType:
        """
        Guess image type specific for png format.

        Parameters
        ----------
        image: Image

        Returns
        -------
        The optical image type.
        """
        return OpticalImageType.GENERIC_OPTICAL_IMAGE

    @staticmethod
    def guess_type(path: str | Path) -> OpticalImageType:
        """
        Guess the type of optical image.

        Parameters
        ----------
        path: str | Path
            The path of the image.

        Returns
        -------
        The optical image type.
        """
        with Image.open(path) as image:
            image.load()
            try:
                if image.format == 'JPEG':
                    typ = OpticalImageFactory.guess_type_of_jpeg(image)
                elif image.format == 'PNG':
                    typ = OpticalImageFactory.guess_type_of_png(image)
                else:
                    typ = OpticalImageType.GENERIC_OPTICAL_IMAGE

            except KeyError:
                typ = OpticalImageType.GENERIC_OPTICAL_IMAGE

        image.close()
        return typ


optical_image_factory = OpticalImageFactory()
optical_image_factory.register_type(OpticalImageType.GENERIC_OPTICAL_IMAGE, GenericOpticalImage)
optical_image_factory.register_type(OpticalImageType.DIGITAL_CAMERA_OPTICAL_IMAGE, DigitalCameraOpticalImage)
optical_image_factory.register_type(OpticalImageType.KEYENCE_OPTICAL_IMAGE, KeyenceMicroscopeImage)
optical_image_factory.register_type(OpticalImageType.DIGITAL_CAMERA_OPTICAL_IMAGE_WITH_GPS,
                                    DigitalCameraOpticalImageWithGPS)


class OpticalImageDict(ResettableDict):
    """A dictionary of optical images"""

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def add(self, optical_image: GenericOpticalImage | str | Path):
        """
        Add an optical image to the resettable dictionary.

        Parameters
        ----------
        optical_image: GenericOpticalImage
            The object to be added.
        """
        if not isinstance(optical_image, (GenericOpticalImage, str, Path)):
            raise TypeError('Optical Images type must be derived from AbstractOpticalImage, string or path-like')

        if isinstance(optical_image, (str, Path)):
            optical_image = optical_image_factory.get_optical_image(optical_image)

        if optical_image.key in self.data.keys():
            raise autoerror.DuplicatedKey('Attempt to add another optical image with the same key %s' %
                                          optical_image.key)
        else:
            self.data[optical_image.params['key']] = optical_image

    def remove(self, optical_image: GenericOpticalImage | str | Path) -> None:
        """
        Remove the object from the resettable dictionary.

        Parameters
        ----------
        optical_image: GenericOpticalImage
            The object being removed.
        """
        if not isinstance(optical_image, (GenericOpticalImage, str, Path)):
            raise TypeError('Optical image type must be derived from AbstractOpticalImage, string or path-like')

        if isinstance(optical_image, GenericOpticalImage):
            key = optical_image.key
        else:
            key = str(optical_image)

        if key in self.data:
            del self.data[key]
        else:
            log.warning('Attempt to remove %s from the optical image dictionary, but it was not there' % key)
