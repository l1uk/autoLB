# -*- coding: utf-8 -*-
"""
Implement the GUI for the restore of recycle elements.

This specific dialog is connected with an item model and some other auxiliary classes and for this reason is
implemented in its own module instead of along with the other dialog windows in the dialog_windows.
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

from pathlib import Path
from typing import Any

from PyQt5 import QtCore
from PyQt5.QtCore import QAbstractListModel, QModelIndex, QObject, QRegExp, QSortFilterProxyModel, Qt
from PyQt5.QtWidgets import QDialog, QHeaderView, QMessageBox

from autologbook.autotools import reglob
from autologbook.file_type_guesser import regexp_repository
from autologbook.protocol_editor_models import UserRole
from autologbook.restore_element_dialog_ui import Ui_RecoverElementDialog

Signal = QtCore.pyqtSignal
Slot = QtCore.pyqtSlot


class FileListModel(QAbstractListModel):
    """
    Implementation of a list model to display a list of files.

    The DisplayRole is set to the file name.
    In the UserRole.ELEMENT_FULL_PATH the whole object path is stored.

    """

    def __init__(self, parent: QObject = None, file_list: list[Path] = None):
        super().__init__(parent)
        self.file_list = list()
        if file_list is not None:
            self.set_list(file_list)

    def set_list(self, file_list: list[Path]):
        """
        Set the list of files to the internal memory storage.

        Parameters
        ----------
        file_list: list[Path]
            A list of file path.
        """
        self.beginResetModel()
        self.file_list = file_list
        self.endResetModel()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
        """
        Set the header data for the model.

        Parameters
        ----------
        section: int
            It corresponds to the column. There is only one column in the model and it is set to 'Filename'.
        orientation: Qt.Orientation
            It is set only for the horizontal orientation.
        role: int
            The data role.
        Returns
        -------
        str:
            Returns 'Filename' for section=0 horizontal and DisplayRole
        """
        if role != Qt.DisplayRole:
            return
        if orientation == Qt.Orientation.Horizontal:
            if section == 0:
                return 'Filename'
            else:
                return
        else:
            return

    def index(self, row: int, column: int = ..., parent: QModelIndex = ...) -> QModelIndex:
        """
        Overload the index method

        Parameters
        ----------
        row: int
            The row index
        column: int
            The column index
        parent: QModelIndex
            The parent model index

        Returns
        -------
        QModelIndex:
            The model index with row, column and from parent.
        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column, None)

    def rowCount(self, parent: QModelIndex = ...) -> int:
        """
        Return the number of row.

        Parameters
        ----------
        parent: QModelIndex
            Not used

        Returns
        -------
        The length of the filename list.
        """
        return len(self.file_list)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        """
        Return the number of columns

        Parameters
        ----------
        parent: QModelIndex
            Not used

        Returns
        -------
        Always return 1.
        """
        return 1

    def data(self, index: QModelIndex, role: int = ...) -> Any:
        """
        Get the data for the index and with role.

        The list stored in the element contains full path.
        When the user asks for Qt.DisplayRole, then the absolute path is stripped away and only the file name is
        returned.
        When the user asks for UserRole.ELEMENT_FULL_PATH, then the full path is returned.

        Parameters
        ----------
        index: QModelIndex
            The index for which we want to get the data
        role: int
            The role of the data for which we want to get the data

        Returns
        -------
        The data for the index and with role.
        """
        if not index.isValid():
            return
        if role == Qt.DisplayRole:
            return str(Path(self.file_list[index.row()]).name)
        elif role == UserRole.ELEMENT_FULL_PATH:
            return self.file_list[index.row()]
        else:
            return


class RecoverElementDialog(QDialog, Ui_RecoverElementDialog):
    """
    A subclass of QDialog to help the user decides which files are to be recovered.

    The UI has a file selector combobox with all existing samples in the protocol. Only samples with a recycle bin are
    selectable, all others are disabled.

    The list view widget is connected to a proxy model mapping a FileListModel in order to allow sorting and filtering.
    A line edit is provided to allow filtering of the elements.
    """

    # a static member to define the name of the recycle bin.
    bin_path = Path('excluded/')

    def __init__(self, parent: QObject = None, sample_list: list = None,
                 protocol_path: Path | str = None, current_sample: str = None):
        super().__init__(parent)
        self.setupUi(self)
        self.parent = parent
        # protocol path. we need this to be prepended to the sample full name
        self.protocol_path = Path(protocol_path)
        # sample full name list to fill in the sample selector
        self.sample_list = sample_list  # a list of sample_full_names
        # the current sample, i.e. the sample from where the dialog was called.
        self.current_sample = current_sample

        # there is the possibility that dialog has to be rejected as soon as it is executed. This happens if there are
        # no recycle bins in the protocol.
        self.to_be_rejected = False

        # prepare the file list model
        self.file_list_model = FileListModel(self)
        # prepare the file list model proxy
        self.file_list_model_proxy = QSortFilterProxyModel(self)
        self.file_list_model_proxy.setSourceModel(self.file_list_model)
        # connect the filter line edit to the proxy
        self.filter_line_edit.textChanged.connect(self.filter_file_list)
        # link the proxy to the viewer
        self.file_list_view.setModel(self.file_list_model_proxy)
        self.file_list_view.setSortingEnabled(True)
        self.file_list_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # if the sample_list is not None, then add all samples to sample_selector, disables the ones without recycle
        # bin, update the list model with all the recycled files and finally sort the table.
        if sample_list:
            self.sample_selector.addItems(self.sample_list)
            self.filter_sample_selector()
            self.update_file_list_model()
            self.file_list_model.sort(0, Qt.AscendingOrder)

    def exec_(self) -> int:
        """
        Overload of the exec call.

        Before calling the super class exec, check if it makes sense to start at all. If the to_be_rejected variable
        is set to True then, just leave.

        Returns
        -------
        Rejected if to_be_rejected is True, or super().exec_() otherwise.
        """
        if self.to_be_rejected:
            self.reject()
            return self.Rejected
        else:
            return super(RecoverElementDialog, self).exec_()

    @Slot(str)
    def filter_file_list(self, re: str) -> None:
        """
        Filter the proxy model using the string re.

        This slot is connected with filter_line_edit widget.

        Parameters
        ----------
        re: str
            The filter text.
        """
        self.file_list_model_proxy.setFilterRegExp(QRegExp(re, Qt.CaseInsensitive, QRegExp.FixedString))

    def filter_sample_selector(self):
        """
        Disables samples with no recycle bin.

        """
        # we leave active only samples with a recycle bin.
        for sample in self.sample_list:
            index = self.sample_selector.findText(sample)
            self.sample_selector.model().item(index).setEnabled(False)
            if sample == 'Protocol':
                path_to_test = self.protocol_path / self.bin_path
            else:
                path_to_test = self.protocol_path / Path(sample) / self.bin_path

            if path_to_test.is_dir():
                # it means that this folder exists.
                # it is a good start but it is not enough, because it could be empty.
                self.sample_selector.model().item(index).setEnabled(not self.is_path_empty(path_to_test))

        # if the user provided a current sample, then we need to have the sample_selector pointing to this sample,
        # but only if it is enabled! If the current sample is disabled, then inform the user about this and let him
        # decide if he wants to continue or not. If he decides to continue, then let's set the sample selector to the
        # first enabled sample. If there are no selectable items, then inform the user again about the issue and set
        # the to_be_rejected variable to True and leave.
        if self.current_sample:
            current_index = self.sample_selector.findText(self.current_sample)
            if self.sample_selector.model().item(current_index).isEnabled():
                self.sample_selector.setCurrentText(self.current_sample)
            else:
                reply = QMessageBox.question(self, 'Recover from recycling bin',
                                             f'Sample {self.current_sample} does not have any recycled items. {chr(10)}'
                                             f'Do you want to recycle from another sample?',
                                             buttons=(QMessageBox.Yes | QMessageBox.No))
                if reply == QMessageBox.No:
                    self.to_be_rejected = True
                    return

                enable_found = False
                for index in range(self.sample_selector.count()):
                    if self.sample_selector.model().item(index).isEnabled():
                        self.sample_selector.setCurrentIndex(index)
                        enable_found = True
                        break
                if not enable_found:
                    QMessageBox.warning(self, 'Recover from recycling bin',
                                        'There are no recycled items in this protocol.',
                                        buttons=QMessageBox.Ok)
                    self.to_be_rejected = True
                    self.reject()
                    return

    def update_file_list_model(self):
        """
        Updates the file list model with all the files contained in the recycle bin.

        Files must match the patterns for microscope_pictures and video_files.

        """
        if self.sample_selector.currentText() == 'Protocol':
            sample_path = self.protocol_path / self.bin_path
        else:
            sample_path = self.protocol_path / Path(self.sample_selector.currentText()) / self.bin_path
        patterns = list()
        patterns.extend(regexp_repository.get_matching('VIDEO'))
        patterns.extend(regexp_repository.get_matching('IMAGEFILE'))
        patterns.extend(regexp_repository.get_matching('ATTACHMENT'))
        patterns.extend(regexp_repository.get_matching('OPTICAL_IMAGE'))
        file_list = reglob(sample_path, matching_regexes=patterns, ignore_regexes=None, recursive=True)
        file_list = [Path(file) for file in file_list]
        self.file_list_model.set_list(file_list)

    @staticmethod
    def is_path_empty(path: Path) -> bool:
        """
        Check if a path is empty.

        This is a bit more complex that the basic os tools, because we check if in the directory there are files
        matching the microscope picture or video patterns.

        Parameters
        ----------
        path: Path
            The path to be tested

        Returns
        -------
        True if the directory is empty.
        """
        patterns = list()
        patterns.extend(regexp_repository.get_matching('ATTACHMENT'))
        patterns.extend(regexp_repository.get_matching('VIDEO'))
        patterns.extend(regexp_repository.get_matching('IMAGEFILE'))
        patterns.extend(regexp_repository.get_matching('OPTICAL_IMAGE'))
        if len(reglob(path, matching_regexes=patterns, ignore_regexes=None, recursive=True)) > 0:
            return False
        else:
            return True

    @Slot(str)
    def sample_selector_changed(self, sample):
        """
        React to a change in the sample selector.

        The file list model is update.

        Parameters
        ----------
        sample: str
            Not used.
        """
        self.update_file_list_model()
