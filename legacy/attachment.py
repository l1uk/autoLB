# -*- coding: utf-8 -*-
"""
A module defining the attachment items
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
from enum import Enum
from pathlib import Path
from typing import Any

from autologbook import autoerror
from autologbook.containers import ResettableDict
from autologbook.file_type_guesser import ElementTypeGuesser, regexp_repository
from autologbook.object_factoy import ObjectFactory

log = logging.getLogger('__main__')


class Attachment:
    """The class to hold the attachment information."""

    def __init__(self, path: str | Path = None):
        """
        Generate instance of an attachment.

        Parameters
        ----------
        path : str | path-like, optional
            The full path to the attachment.
            The default is None.

        Returns
        -------
        None.

        """
        # prepare the empty dictionary
        self.params = {}

        if path is None:
            log.warning('Generating an attachment without path')
            return

        if not isinstance(path, (str, Path)):
            msg = f'Wrong type for {path} in attachment creation'
            log.error(msg)
            raise TypeError(msg)
        elif isinstance(path, str):
            path = Path(path)

        # before continuing we need to check if the file exists.
        if path.exists() and path.is_file():
            self.params['stat'] = path.stat()
            self.params['size'] = path.stat().st_size
            self.params['path'] = path
            self.params['key'] = str(path)
            self.params['filename'] = path.name
            self.params['extension'] = path.suffix
        else:
            if not path.exists():
                msg = f'{path} not found'
                raise FileNotFoundError(msg)
            if not path.is_file():
                msg = f'{path} not a valid file'
                raise IsADirectoryError(msg)

        self.params['type'] = AttachmentType.GenericAttachmentType
        self.template = 'attachment_base_template.yammy'

    def __repr__(self) -> str:
        """Represent an Attachment."""
        return f'{__class__.__name__}(path=\'{self.params.get("path", None)}\')'

    def __str__(self) -> str:
        """Represent an attachment as a string."""
        s = f"Attachment {self.params['filename']} has the following parameters:\n"
        for key, value in self.params.items():
            s += f'  {key:<12}: {value}\n'
        return s

    def __eq__(self, other: Attachment) -> bool:
        """
        Equality operator.

        Parameters
        ----------
        other : Attachment
            Another attachment

        Returns
        -------
        bool
            True if both attachments have the same key set and their values
            are all the same.
            False otherwise.

        """
        my_keys = set(self.params.keys())
        other_keys = set(other.params.keys())

        if my_keys.intersection(other_keys) != my_keys:
            return False

        overall_eq = True
        for mkey, mvalue in self.params.items():
            overall_eq = overall_eq and (mvalue == other.params[mkey])

        return overall_eq

    def update(self):
        """
        Update the file stat and size.

        It is possible that during the analysis these parameters were changed.

        Returns
        -------
        None
        """
        self.params['stat'] = self.params['path'].stat()
        self.params['size'] = self.params['path'].stat().st_size

    def is_empty(self) -> bool:
        """
        Check if an attachment is empty.

        Empty means that the file has 0 size.

        Returns
        -------
        bool
            True if the attachment file is empty.
            False otherwise

        """
        self.update()
        return int(self.params.get('size', 0)) == 0

    @property
    def key(self) -> str | None:
        """Attachment key."""
        return self.params.get('key', None)

    @key.setter
    def key(self, value: Any):
        """Attachment key setter."""
        self.params['key'] = value

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


class UploadAttachment(Attachment):
    """
    A special attachment object to be uploaded.

    Only a few attachment files are really uploaded to the ELOG entry. All other attachments are just mirrored and
    made available via the image server.
    """

    def __init__(self, path: str | Path = None):
        super().__init__(path)
        self.params['type'] = AttachmentType.UploadAttachmentType


class AttachmentDict(ResettableDict):
    """A dictionary of attachments."""

    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def add(self, attachment: Attachment | str | Path):
        """
        Add an attachment to the dictionary.

        Parameters
        ----------
        attachment : Attachment or str or path-like
            The attachment that must be added.

        Raises
        ------
        TypeError: if attachment is not one of the accepted types.
        KeyError: if adding another attachment with an existing key.

        Returns
        -------
        None.

        """
        if not isinstance(attachment, (Attachment, str, Path)):
            raise TypeError(
                'Attachment type must be Attachment, string or path-like')

        if isinstance(attachment, (str, Path)):
            attachment = Attachment(attachment)

        if attachment.key in self.data.keys():
            raise autoerror.DuplicatedKey('Attempt to add another attachment with the same key %s' % attachment.key)
        else:
            self.data[attachment.params['key']] = attachment

    def remove(self, attachment: Attachment | str | Path) -> None:
        """Remove an attachment from the list.

        Parameters
        ----------
        attachment : Attachment or str or path-like
            The attachment that must be removed.

        Raises
        ------
        TypeError: if attachment is not one of the acceptable types.

        Returns
        -------
        None.

        """
        if not isinstance(attachment, (Attachment, str, Path)):
            raise TypeError(
                'Attachment type must be Attachment, string or path-like')

        if isinstance(attachment, Attachment):
            key = attachment.key
        else:
            key = str(attachment)

        if key in self.data:
            del self.data[key]
        else:
            log.warning('Attempt to remove %s from the attachments dictionary, but it was not there' % key)

    def get_upload_attachments(self) -> list[str]:
        """
        Returns a list of attachments to be uploaded.

        Returns
        -------
        A list of attachments.
        """
        return [attach.key for attach in self.data.values() if isinstance(attach, UploadAttachment)]


class AttachmentType(Enum):
    """Enumerator class to define the different attachment types."""
    GenericAttachmentType = 'Generic'
    UploadAttachmentType = 'Upload'


class AttachmentFactory(ObjectFactory):
    """
    The attachment factory class

    Based on the generic Object Factory, it is used to generate attachment objects. At the moment there are two
    different type of attachments. Generic attachments are copied to the image server and made available via a link
    but not posted to the ELOG. On the contrary Upload attachments are also physically attached to the ELOG post.
    """

    def __init__(self):
        super().__init__()
        self.upload_attachment_guesser = ElementTypeGuesser(regexp_repository.get_matching('UPLOAD_ATTACHMENT'),
                                                            regexp_repository.get_exclude('UPLOAD_ATTACHMENT'))

    def guess_type(self, path: str | Path) -> AttachmentType:
        """
        Guess the type of attachment.

        This method is guessing the type of attachment starting from its absolute path. The discrimination is
        based on the file extension, and it is performed by a dedicated ElementTypeGuesser.

        Parameters
        ----------
        path: str | Path
            The attachment path

        Returns
        -------
        AttachmentType. The Attachmnet type.

        """
        if self.upload_attachment_guesser.is_ok(path):
            return AttachmentType.UploadAttachmentType
        else:
            return AttachmentType.GenericAttachmentType

    def create_object(self, path: str | Path, object_type: AttachmentType = None) -> Attachment:
        """
        Generate an attachment object base on the specified object_type.

        If object_type is None, then it is guessed via the guess_type method.

        Parameters
        ----------
        path: str | Path
            The attachment path

        object_type: AttachmentType
            The attachment type. If None, then it is guessed by the guess_type method.

        Returns
        -------
        Attachment
            The attachment object.
        """
        if object_type is None:
            object_type = self.guess_type(path)
        if object_type in self._creators:
            return self._creators[object_type](path)
        else:
            log.warning('%s is not supported by the factory. Returning the generic object')
            return Attachment(path)


# The attachment factory to be used in the rest of the package.
attachment_factory = AttachmentFactory()
attachment_factory.register_type(AttachmentType.GenericAttachmentType, Attachment)
attachment_factory.register_type(AttachmentType.UploadAttachmentType, UploadAttachment)
