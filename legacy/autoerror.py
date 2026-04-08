# -*- coding: utf-8 -*-
"""
Created on Wed Aug 31 08:13:29 2022

@author: elog-admin
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


class AutologError(Exception):
    """Base class for autologbook exception."""

    pass


class SampleError(AutologError):
    """Base Sample Error."""


class NotAValidConfigurationFile(AutologError):
    """Invalid configuration file."""


class ParentSampleError(SampleError):
    """
    Error with the sample parent.

    Raised when an error with the parent genealogy occurs.
    """

    pass


class SampleNameAlreadyExisting(SampleError):
    """
    Error with the Sample name.

    A top level sample must have an unique name.

    Raised when a sample with the same name of another sample is added.
    """

    pass


class ProtocolError(AutologError):
    """Base Protocol Error."""

    pass


class MissingProtocolInformation(ProtocolError):
    """
    Missing protocol information.

    Raised when attempting to build a protocol without providing all
    needed information.
    """

    pass


class ElogError(AutologError):
    """Base ELOG Error."""

    pass


class MissingELOGPageParameter(ElogError):
    pass


class InvalidConnectionParameters(ElogError):
    pass


class ReadOnlyEntry(ElogError):
    """
    Read only entry.

    Raised when an attempt is made to write or delete a read-only elog
    entry.
    """

    pass


class MissingWorkerParameter(AutologError):
    """
    Missing worker parameter.

    Raised when attempting to update a worker parameters without providing
    a needed parameter.
    """
    pass


class MicroscopePictureError(AutologError):
    """Generic error associated with a Microscope picture."""
    pass


class UnableToOpenMicroscopePicture(MicroscopePictureError):
    """Error associated with a failure to open a microscope picture"""
    pass


class WrongResolutionUnit(MicroscopePictureError):
    """
    Wrong resolution unit.

    Raised when an attempt to use an invalide unit of measurements for the
    picture resolution is made.
    """
    pass


class ImpossibleToConvert(MicroscopePictureError):
    """Impossible to convert image resolution w/o unit of measurements."""
    pass


class NotFEIMicroscopePicture(MicroscopePictureError):
    """
    Not a FEI microscope picture.

    Raised when an attempt is made to constructur a FEIPicture with a TIFF
    picture not generated from a FEI microscope
    """

    pass


class InvalidMetadata(MicroscopePictureError):
    pass


class DuplicatedKey(AutologError):
    pass


class OpticalImageError(AutologError):
    pass


class InvalidOpticalImageError(OpticalImageError):
    pass


class WatchdogError(AutologError):
    pass


class MirrorHandlerError(WatchdogError):
    pass


class ForceRemirroring(MirrorHandlerError):
    pass


class MirroredFileDifferFromOriginal(MirrorHandlerError):
    pass


class ELOGPostSplitterError(AutologError):
    pass


class DuplicatePage(ELOGPostSplitterError):
    pass


class InvalidNumberOfPages(ELOGPostSplitterError):
    pass


class InvalidParent(ElogError):
    pass


class InvalidHierarchy(ElogError):
    pass


class ProtocolListError(ElogError):
    pass


class DecodeError(AutologError):
    pass
