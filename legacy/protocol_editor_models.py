# -*- coding: utf-8 -*-
"""Module containing the item models required for the protocol editors."""
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
import logging
from enum import Enum, IntEnum, auto
from pathlib import Path
from typing import Any

from PyQt5 import QtCore
from PyQt5.Qt import QBrush, QColor, QFont, QIcon, QLinearGradient, QStandardItem
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from autologbook.html_helpers import HTMLHelperMixin

log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class ElementType(Enum):
    """Enumerator to define the various type of items."""

    TEXT = 'Text'
    SECTION = 'Section'
    SAMPLE = 'Sample'
    NAVIGATION_PIC = 'NavPic'
    MICROSCOPE_PIC = 'MicroPic'
    ATTACHMENT_FILE = 'AttachmentFile'
    YAML_FILE = 'YAMLFile'
    VIDEO_FILE = 'VIDEOFile'
    HEADER_FILE = 'HeaderFile'
    OPTICAL_PIC = 'OpticalPic'


class UserRole(IntEnum):
    """Enumerator to define user role for the data model.

    The actual value of each role is irrelevant, it is only important that each
    element stays constant during on single execution and that their value is
    greater than QtCore.Qt.UserRole + 1.

    It is a perfect application case for an IntEnum with auto() values and
    overloaded _generate_next_value_.


    """

    # noinspection PyProtectedMember
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> int:
        """
        Generate the next value.

        This function is called every time a new element with auto() is added.
        The user role must be at least QtCore.Qt.UserRole + 1.

        Parameters
        ----------
        name : string
            The name of the enum element.
        start : int
            The value of the first enumerator. It is always 1.
        count : int
            The number of enumerator values so far.
        last_values : iterable
            A list of all already used values.

        Returns
        -------
        int
            The next value starting from QtCore.Qt.UserRole+1

        """
        return IntEnum._generate_next_value_(name, QtCore.Qt.UserRole + 1, count, last_values)

    ITEM_TYPE = auto()
    DESCRIPTION = auto()
    EXTRA = auto()
    IMAGE = auto()
    PIC_ID = auto()
    CAPTION = auto()
    SAMPLE_FULL_NAME = auto()
    SAMPLE_LAST_NAME = auto()
    ATTACHMENT_PATH = auto()
    ATTACHMENT_FILE = auto()
    VIDEO_KEY = auto()
    VIDEO_PATH = auto()
    VIDEO_URL = auto()
    ELEMENT_FULL_PATH = auto()
    OPTICAL_IMAGE_PATH = auto()
    OPTICAL_IMAGE_KEY = auto()
    OPTICAL_IMAGE_URL = auto()


class ProtocolItem(QStandardItem):
    """Text item derived from QStandardItem."""

    def __init__(self, txt=''):
        """
        Construct a new ProtocolItem.

        The item_type role is set to Text.

        Parameters
        ----------
        txt : str, optional
            This is the text used as a display role. The default is ''.

        Returns
        -------
        None.
        """
        super().__init__()
        self.setText(txt)
        self.setData(ElementType.TEXT, UserRole.ITEM_TYPE)
        self.key = self.text()

    def set_custom_data(self, custom_dict):
        key_role_list = [
            ('Caption', UserRole.CAPTION),
            ('Description', UserRole.DESCRIPTION),
            ('Extra', UserRole.EXTRA)
        ]
        for key, role in key_role_list:
            if key in custom_dict and custom_dict[key]:
                self.setData(custom_dict[key], role)

    def get_dictionary_from_yaml(self, yaml_dict):
        if self.key in yaml_dict.keys():
            return yaml_dict[self.key]
        else:
            return {}

    def get_data_from_yaml(self, yaml_dict) -> None:
        self.set_custom_data(self.get_dictionary_from_yaml(yaml_dict))


class SectionItem(ProtocolItem):
    """
    Section item derived from ProtocolItem.

    This item is used to store section information.

    """

    def __init__(self, txt=''):
        """
        Construct a new SectionItem.

        The item_type role is set to Section.

        Parameters
        ----------
        txt : str, optional
            This is the text used as a display role. The default is ''.

        Returns
        -------
        None.

        """
        super().__init__(txt=txt)
        self.setData(ElementType.SECTION, UserRole.ITEM_TYPE)
        self.key = self.text()


class AttachmentItem(ProtocolItem):
    """
    Attachment item derived from QStandardItem.

    This item is used to store attachments.
    The display name is the attachment filename.

    The attachment key is stored in the data with attachment_path.
    The attachment filename is stored in data the with attachment_file.

    The attachment icon is set using the DecorationRole.

    """

    def __init__(self, attachment_path):
        super().__init__()
        attachment_filename = Path(attachment_path).name
        self.setText(attachment_filename)
        self.setData(ElementType.ATTACHMENT_FILE, UserRole.ITEM_TYPE)
        self.setData(attachment_path, UserRole.ATTACHMENT_PATH)
        self.setData(attachment_filename, UserRole.ATTACHMENT_FILE)
        self.setData(QIcon(':/resources/icons8-attach-48.png'), Qt.DecorationRole)
        self.key = self.data(UserRole.ATTACHMENT_PATH)


class SampleItem(ProtocolItem):
    """
    Sample item derived from QStandardItem.

    This item is used to store samples.

    The Display name is the sample_last_name.

    The sample_full_name is stored in the data with the UserRole.SAMPLE_FULL_NAME
    The sample_last_name is stored in the data with the UserRole.SAMPLE_LAST_NAME

    The FontRole is set to the current font but bold.
    The DecorationRole is set to an icon.
    The BackgroundRole is set to a gradient.

    """

    def __init__(self, sample_full_name):
        """
        Generate a new Sample Item.

        Remember that this object needs the **full name**.

        The display text (what will appear on the Protocol Editor) is the last
        name, but the constructor needs the full name.

        Parameters
        ----------
        sample_full_name : str
            Full name (complete hierarchy) of the sample.

        Returns
        -------
        None.

        """
        super().__init__()
        sample_last_name = sample_full_name.split('/')[-1]
        self.setText(sample_last_name)
        self.setData(ElementType.SAMPLE, UserRole.ITEM_TYPE)
        self.setData(sample_full_name, UserRole.SAMPLE_FULL_NAME)
        self.setData(sample_last_name, UserRole.SAMPLE_LAST_NAME)
        self.setData(QIcon(':/resources/icons8-ice-48.png'), Qt.DecorationRole)
        self.setData(QFont('MS Shell Dlg 2', 8, QFont.Bold), Qt.FontRole)
        gradient = QLinearGradient(00, 00, 60, 100)
        gradient.setColorAt(0, QColor.fromCmyk(5, 0, 0, 20))
        gradient.setColorAt(1, Qt.white)
        self.setData(QBrush(gradient), Qt.BackgroundRole)
        self.key = self.data(UserRole.SAMPLE_FULL_NAME)


class NavPicItem(ProtocolItem):
    """
    Navigation Picture Item.

    This type is used to store navigation images.
    """

    def __init__(self, txt='', img_link=''):
        """
        Constructor an instance of NaPicItem.

        The type of this item is set to NavPic.

        The DecorationRole is set to an icon.

        Parameters
        ----------
        txt : str, optional
            The name of the picture used as display_role. The default is ''.
        img_link : str, optional
            The URL where the thumbnail of the image. The default is ''.

        Returns
        -------
        None.

        """
        super().__init__(txt=txt)
        self.setData(ElementType.NAVIGATION_PIC, UserRole.ITEM_TYPE)
        self.setData(img_link, UserRole.IMAGE)
        self.setData(QIcon(':/resources/icons8-map-marker-48.png'), Qt.DecorationRole)
        self.key = self.text()


class OpticalImageItem(HTMLHelperMixin, ProtocolItem):
    def __init__(self, path: str | Path):
        if isinstance(path, Path):
            name = path.name
            key = str(path)
        elif isinstance(path, str):
            key = path
            path = Path(path)
            name = path.name
        else:
            raise TypeError('Path must be str or Path')

        super().__init__(name)
        self.setData(ElementType.OPTICAL_PIC, UserRole.ITEM_TYPE)
        self.setData(key, UserRole.IMAGE)
        self.setData(key, UserRole.OPTICAL_IMAGE_KEY)
        self.setData(path, UserRole.OPTICAL_IMAGE_PATH)
        url = self.convert_path_to_uri(path)
        self.setData(url, UserRole.OPTICAL_IMAGE_URL)
        self.setData(QIcon(':/resources/icons8-compact-camera-32.png'), Qt.DecorationRole)
        self.key = self.data(UserRole.OPTICAL_IMAGE_KEY)


class MicroPicItem(ProtocolItem):
    """
    Microscope Picture Item.

    This type is used to store microscope pictures.
    """

    def __init__(self, txt: str = '', img_id: str = '', img_link: str = ''):
        """
        Constructor an instance of MicroPicItem.

        The type of this item is set to MicroPic.

        The DecorationRole is set to an icon.

        Parameters
        ----------
        img_id : str
            The key of the microscope image.

        img_link : str, optional
            The URL where the thumbnail of the image. The default is ''.

        Returns
        -------
        None.

        """
        super().__init__(txt=txt)
        self.setData(ElementType.MICROSCOPE_PIC, UserRole.ITEM_TYPE)
        self.setData(img_id, UserRole.PIC_ID)
        self.setData(img_link, UserRole.IMAGE)
        self.setData(QIcon(':/resources/icons8-optical-microscope-64.png'), Qt.DecorationRole)
        self.key = self.data(UserRole.PIC_ID)


class VideoItem(ProtocolItem):
    """
    Video Item.

    This item type is used to store video.
    """

    def __init__(self, txt: str = '', key: str = '', url: str = '', path: str | Path = ''):
        """
        Build an instance of the VideoItem.

        The DecorationRole is set to an icon.

        Parameters
        ----------
        txt: str
            Set the display role for the item (DisplayRole)
        key: str
            The video key used for retrieving the element from the VideoDict. (UserRole.VIDEO_KEY)
        url: str
            The video url for playback. (UserRole.VIDEO_URL)
        path: str | Path
            The video path (UserRole.VIDEO_PATH)
        """
        super().__init__(txt=txt)
        self.setData(ElementType.VIDEO_FILE, UserRole.ITEM_TYPE)
        self.setData(key, UserRole.VIDEO_KEY)
        self.setData(path, UserRole.VIDEO_PATH)
        self.setData(url, UserRole.VIDEO_URL)
        self.setData(QIcon(':/resources/icons8-video-clip-48.png'), Qt.DecorationRole)
        self.key = self.data(UserRole.VIDEO_KEY)


class TreeViewerProxyModel(QSortFilterProxyModel):
    """
    A subclass of the QSortFilterProxyModel adapted to the autolog tree browser.

    This class is reimplementing the filtering and sorting methods.
    """

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """
        Select which model row should be accepted when filtering.

        The proxy model has to have the recursive filtering property set to True because we want to have the
        filtering applied to recursively for each level in the hierarchical model.

        The selection is made using a FixedString regular expression.
        The following data fields are tested for matching:
        1. item name (Qt.DisplayRole)
        2. Caption (UserRole.CAPTION)
        3. Description (UserRole.DESCRIPTION)
        4. Extra (UserRole.EXTRA)

        Parameters
        ----------
        source_row: int
            The row being analyzed for filtering.
        source_parent: QModelIndex
            The parent index of the source_row

        Returns
        -------
        bool:
            True if the row has to be accepted.
        """
        proxy_index = self.sourceModel().index(source_row, 0, source_parent)
        item_name = self.sourceModel().data(proxy_index)
        interesting_fields = [
            item_name,
            self.sourceModel().data(proxy_index, UserRole.CAPTION),
            self.sourceModel().data(proxy_index, UserRole.DESCRIPTION),
            self.sourceModel().data(proxy_index, UserRole.EXTRA)
        ]
        test_results = list()
        for element in interesting_fields:
            if self.filterRegExp().indexIn(element) < 0:
                test_results.append(False)
            else:
                test_results.append(True)
        return any(test_results)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """
        Implement the sorting method for the proxy model.

        The hierarchical model is sorted level by level.

        The top level is made only by SectionItem, those are generated sorted at the model generation and should never
        be moved, but in any case we can rearrange them according to the original order.

        For sections not having children (as Navigation images and Attachments), their items are alphabetically sorted
        based on their names.

        For the Samples sections, it may contain three different type of items: SAMPLE, MICROSCOPE_PIC, VIDEO_FILE.
        The method will sort them in this order:
            1. images in alphabetical order,
            2. videos in alphabetical order,
            3. subsamples in alphabetical order.

        Parameters
        ----------
        left: QModelIndex
            The left model index in the comparison
        right: QModelIndex
            The right model index in the comparison

        Returns
        -------
        bool:
            True if left is less than right.
        """
        # Introduction, Navigation images, Samples, Conclusions, Attachments
        section_dict = {'Introduction': 0, 'Navigation images': 10, 'Optical images': 15,
                        'Samples': 20, 'Conclusion': 30, 'Attachments': 40}
        left_type = self.sourceModel().data(left, UserRole.ITEM_TYPE)
        left_name = self.sourceModel().data(left)
        right_type = self.sourceModel().data(right, UserRole.ITEM_TYPE)
        right_name = self.sourceModel().data(right)

        # sorting the top level made of section items.
        # we keep the original order described in the section_dict
        if left_type == ElementType.SECTION:
            if right_type == ElementType.SECTION:
                return section_dict[left_name] < section_dict[right_name]
            else:
                return True  # the section is always coming before than other types

        # sorting inside of single level sections like navigation and attachments
        elif left_type in [ElementType.NAVIGATION_PIC]:
            # the right type should be of the same type.
            return left_name < right_name

        # sorting inside the samples.
        # 1. images in alphabetical order,
        # 2. videos in alphabetical order,
        # 3. optical images in alphabetical order,
        # 4. attachments in alphabetical order,
        # 5. subsamples in alphabetical order.
        elif left_type == ElementType.MICROSCOPE_PIC:
            if right_type in [ElementType.VIDEO_FILE, ElementType.OPTICAL_PIC, ElementType.ATTACHMENT_FILE,
                              ElementType.SAMPLE]:
                return True
            else:  # right type == ElementType.MICROSCOPE_PIC
                return left_name < right_name
        elif left_type == ElementType.VIDEO_FILE:
            if right_type == ElementType.MICROSCOPE_PIC:
                return False
            elif right_type in [ElementType.OPTICAL_PIC, ElementType.ATTACHMENT_FILE, ElementType.SAMPLE]:
                return True
            else:  # right type == ElementType.VIDEO_FILE
                return left_name < right_name
        elif left_type == ElementType.OPTICAL_PIC:
            if right_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
                return False
            elif right_type in [ElementType.ATTACHMENT_FILE, ElementType.SAMPLE]:
                return True
            else:  # right type == ElementType.OPTICAL_PIC
                return left_name < right_name

        elif left_type == ElementType.ATTACHMENT_FILE:
            if right_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE, ElementType.OPTICAL_PIC]:
                return False
            elif right_type == ElementType.SAMPLE:
                return True
            else:
                return left_name < right_name
        elif left_type == ElementType.SAMPLE:
            if right_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE, ElementType.OPTICAL_PIC,
                              ElementType.ATTACHMENT_FILE]:
                return False
            else:  # right type == ElementType.SAMPLE
                return left_name < right_name


class MetadataModel(QAbstractTableModel):
    """
    Derived model to contain metadata from protocol items.
    """

    def __init__(self, metadata: dict | list = None):
        """
        Initialize the model.

        If provided, the metadata dictionary or list is assigned to the model.

        Parameters
        ----------
        metadata: dict | list (optional)
            A dictionary or a list of elements to be assigned to the model.

        """
        super().__init__()
        self.metadata = list()
        if metadata is not None:
            self.set_metadata(metadata)

    def set_metadata(self, metadata: dict | list = None):
        """
        Set the model data.

        The metadata dictionary or list contains all data to be transferred to the model.

        Parameters
        ----------
        metadata: dict | list
            A list of 2-uple or a dictionary of metadata to be assigned to the model.

        Returns
        -------

        """
        self.beginResetModel()
        if isinstance(metadata, list):
            self.metadata = metadata
        elif isinstance(metadata, dict):
            self.metadata = [(key, value) for key, value in metadata.items()]
        else:
            log.error('Only metadata list or dictionaries are accepted.')
        self.endResetModel()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
        """
        Set the header data.

        Parameters
        ----------
        section: int
            Column number
        orientation: Qt.Orientation
            Horizontal or vertical headers
        role:
            Qt.DisplayRole
        Returns
        -------
        str:
            The name of the header section.

        """
        if role != Qt.DisplayRole:
            return
        if orientation == Qt.Orientation.Horizontal:
            if section == 0:
                return 'Property'
            elif section == 1:
                return 'Value'
            else:
                return
        else:
            return

    def index(self, row: int, column: int, parent: QModelIndex) -> QModelIndex:
        """
        Reimplement the index method.

        Parameters
        ----------
        row: int
            Row number
        column: int
            Column number
        parent: QModelIndex
            parent index

        Returns
        -------
        QModelIndex:
            The model index.
        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column, None)

    def rowCount(self, parent: QModelIndex = ...) -> int:
        """
        Return the number of rows.

        This corresponds to the number of items in the metadata object.

        Parameters
        ----------
        parent: QModelIndex
            Parent item in the model

        Returns
        -------
        int:
            The number of rows in the model under the parent index.
        """
        return len(self.metadata)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        """
        Return the number of columns

        This is a fixed number (2).

        Parameters
        ----------
        parent: QModelIndex
            Parent item in the model

        Returns
        -------
        int:
            2.
        """
        return 2

    def data(self, index: QModelIndex, role: int = ...) -> Any:
        """
        Reimplement the data method to retrieve data from the model.

        Parameters
        ----------
        index: QModelIndex
            The model index of the item for which the data is requested.
        role:
            The data role. Implemented only Qt.DisplayRole

        Returns
        -------
        str:
            Return the metadata value at index.row and index.column.
        """

        if not index.isValid():
            return
        if role != Qt.DisplayRole:
            return
        return self.metadata[index.row()][index.column()]
