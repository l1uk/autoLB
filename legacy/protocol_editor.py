# -*- coding: utf-8 -*-
"""Module to generate a graphical protocol editor"""
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

import logging
import subprocess
import time
import webbrowser
from pathlib import Path

from PyQt5 import QtCore
from PyQt5.Qt import (
    QAction,
    QEvent,
    QHeaderView,
    QIcon,
    QMenu,
    QObject,
    QPixmap,
    QPoint,
    QRegExp,
    QStandardItemModel,
    QUrl,
    QTimer,
)
from PyQt5.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QDialog, QFileDialog, QMessageBox

from autologbook import autoprotocol, autotools
from autologbook.autotools import CustomEditVisibilityFlag, ElementTypeVisitiliyFlag, MetadataVisibilityFlag
from autologbook.context_menu import (
    filter_context_menu,
    generate_context_menu_from_scheme,
    generate_tool_button_menu_from_scheme,
)
from autologbook.dialog_windows import ChangeSampleDialog, RenameDialog
from autologbook.file_system_command import FileSystemCommand, FSCommandType
from autologbook.file_type_guesser import ElementTypeGuesser, regexp_repository
from autologbook.html_helpers import HTMLHelperMixin
from autologbook.protocol_editor_models import (
    AttachmentItem,
    ElementType,
    MetadataModel,
    MicroPicItem,
    NavPicItem,
    OpticalImageItem,
    SampleItem,
    SectionItem,
    TreeViewerProxyModel,
    UserRole,
    VideoItem,
)
from autologbook.protocol_editor_ui import Ui_tree_viewer_dialog
from autologbook.restore_element import RecoverElementDialog
from autologbook import autogui, autoconfig

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'

Signal = QtCore.pyqtSignal
Slot = QtCore.pyqtSlot
Slot = QtCore.pyqtSlot

log = logging.getLogger('__main__')


class ProtocolEditor(HTMLHelperMixin, QDialog, Ui_tree_viewer_dialog):
    """Dialog window for the protocol editor."""

    # Signal to emit a file system command.
    # When the user is performing an operation on a protocol element, this is actually corresponding to a file system
    # command (rename / move / delete...).
    # The command is generated inside the ProtocolEditor and is transmitted as a signal argument to the MainWindow
    # where the actual command is received and executed.
    execute_filesystem_command = Signal(FileSystemCommand, name='execute_filesystem_command')

    def __init__(self, parent=None, autolog=None):
        """
        Build a new instance of the protocol editor.

        Parameters
        ----------
        parent : QObject, optional
            The parent object, very likely the MainWindow. The default is None.
        autolog : autologbook.Protocol, optional
            An instance of the protocol. The default is None.

        Returns
        -------
        None.

        """
        super().__init__(parent)
        self.parent = parent
        self.autolog = autolog
        self.setupUi(self)

        # prepare the media player
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.media_player.setVideoOutput(self.video_preview)
        self.media_player.stateChanged.connect(self.media_state_changed)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.media_player.error.connect(self.media_error_handler)

        # set the first page of the previewer stack to be shown
        self.preview_stack.setCurrentIndex(0)

        # connect the signals from MainWindow
        self.parent.added_element.connect(self.add_element)
        self.parent.removed_element.connect(self.remove_element)
        self.parent.change_autolog.connect(self.change_autolog)
        self.parent.reset_content.connect(self.reset_content)

        # prepare the model and get its root node
        self.tree_model = QStandardItemModel()
        self.rootNode = self.tree_model.invisibleRootItem()
        self.autolog_tree_viewer.setHeaderHidden(True)

        # prepare a proxy model and connected it to the model
        self.tree_model_proxy = TreeViewerProxyModel(self)
        self.tree_model_proxy.setSourceModel(self.tree_model)
        self.tree_model_proxy.setRecursiveFilteringEnabled(True)
        self.tree_model_proxy.setDynamicSortFilter(False)

        # now generate the model
        self.generate_model()

        # link the proxy model to the view
        self.autolog_tree_viewer.setModel(self.tree_model_proxy)

        # customize the context menu for the autolog_tree_viewer
        self.autolog_tree_viewer.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_viewer_context_menu = self.generate_tree_view_context_menu()
        self.autolog_tree_viewer.customContextMenuRequested.connect(self.on_tree_context_menu_request)
        self.tree_search_string.textChanged.connect(self.tree_filter)

        # this is the pointer to the last selected item in order to start again from there when reopening the protocol
        # editor window. It has to be a persistent item model because we want to store it
        self.tree_model_last_selected_item = None

        # this is a pointer of the last inserted item
        self.tree_model_last_inserted_item = None

        # prepare the sample_list_view.
        # This is linked to the same model as the autolog_tree_viewer and they share the same selection model.
        # At the beginning we set the root of the sample_list_view to the SectionItem named 'Samples'
        self.sample_list_view.setModel(self.tree_model_proxy)
        self.sample_list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sample_list_view_context_menu = self.generate_sample_list_view_context_menu()
        self.sample_list_view.customContextMenuRequested.connect(self.on_sample_list_context_menu_request)
        self.sample_list_view.setSelectionModel(self.autolog_tree_viewer.selectionModel())

        self.sample_list_view.setRootIndex(
            self.tree_model_proxy.mapFromSource(
                self.tree_model.findItems('Samples', QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)[0].index())
        )

        # connect the inserted new rows signals
        self.tree_model.rowsInserted.connect(self.new_rows_added)

        # connect the selection changed of the selectionModel of the autolog_tree_viewer to the get_and_update_values.
        # This slot is responsible to handle the customization fields (caption, description, extra).
        # The customization values of the previously selected item (if valid) are transferred from the GUI to the item
        # data fields and to the yaml dictionary.
        # The customization values from the newly selected item are transferred to the GUI.
        self.autolog_tree_viewer.selectionModel().selectionChanged.connect(self.get_and_update_values)

        # prepare the model for the metadata with its proxy and connect it to the table view
        self.metadata_model = MetadataModel()
        self.metadata_proxy_model = QSortFilterProxyModel(self)
        self.metadata_proxy_model.setSourceModel(self.metadata_model)
        self.metadata_table.setModel(self.metadata_proxy_model)
        self.metadata_table.setSortingEnabled(True)
        self.metadata_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_search_string.textChanged.connect(self.metadata_filter)
        # set the metadata context menu
        self.metadata_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.metadata_table_context_menu = self.generate_metadata_context_menu()
        self.metadata_table.customContextMenuRequested.connect(self.on_metadata_context_menu_request)

        # this is an emulation of the clipboard to copy all customization data in one go.
        self.custom_data_dict = {'Caption': '', 'Description': '', 'Extra': ''}
        self.custom_data_dict_available = False

        # initialize a yaml dictionary recycler
        self.yaml_dictionary_recycler = autotools.YAMLRecycler()

        # set the image preview context menu
        self.image_preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_preview_context_menu = self.generate_image_preview_context_menu()
        self.image_preview.customContextMenuRequested.connect(self.on_image_preview_context_menu_request)

        # set the custom fields context menu
        self.caption_field.setContextMenuPolicy(Qt.CustomContextMenu)
        self.caption_field.customContextMenuRequested.connect(self.on_custom_edit_context_menu_request)
        self.description_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.description_input.customContextMenuRequested.connect(self.on_custom_edit_context_menu_request)
        self.extrainfo_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.extrainfo_input.customContextMenuRequested.connect(self.on_custom_edit_context_menu_request)
        self.custom_edit_context_menu = self.generate_custom_edit_context_menu()

        # set the menu for the recycle_dropdown_button
        self.recycle_dropdown_button.setMenu(self.generate_recycle_dropdown_menu())
        self.recycle_dropdown_button.setDefaultAction(self.recycle_dropdown_button.menu().actions()[0])
        self.recycle_dropdown_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # set the menu for the edit_dropdown_button
        self.edit_dropdown_button.setMenu(self.generate_edit_dropdown_menu())
        self.edit_dropdown_button.setDefaultAction(self.edit_dropdown_button.menu().actions()[0])
        self.edit_dropdown_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # set the menu for the markdown_font_tool_button
        self.markdown_font_tool_button.setMenu(self.generate_markdown_font_tool_button())
        self.markdown_font_tool_button.setDefaultAction(self.markdown_font_tool_button.menu().actions()[0])
        self.markdown_font_tool_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.markdown_font_tool_button.setEnabled(False)

        # set the menu for the markdown_font_tool_button
        self.markdown_paragraph_tool_button.setMenu(self.generate_markdown_paragraph_tool_button())
        self.markdown_paragraph_tool_button.setDefaultAction(self.markdown_paragraph_tool_button.menu().actions()[0])
        self.markdown_paragraph_tool_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.markdown_paragraph_tool_button.setEnabled(False)

        # set the menu for the copy custom
        self.copy_custom_value_button.setMenu(self.generate_copy_custom_value_button())
        self.copy_custom_value_button.setDefaultAction(self.copy_custom_value_button.menu().actions()[0])
        self.copy_custom_value_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_custom_value_button.setEnabled(False)

        # set the menu for the copy custom
        self.paste_custom_value_button.setMenu(self.generate_paste_custom_value_button())
        self.paste_custom_value_button.setDefaultAction(self.paste_custom_value_button.menu().actions()[0])
        self.paste_custom_value_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.paste_custom_value_button.setEnabled(False)

        # install the event filter for some widgets
        self.description_input.installEventFilter(self)
        self.caption_field.installEventFilter(self)
        self.extrainfo_input.installEventFilter(self)
        self.image_preview.installEventFilter(self)

        # start the auto_save timer
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save)
        self.auto_save_timer.start(autoconfig.AUTO_SAVE_INTERVAL)

    def eventFilter(self, object_: QObject, event: QEvent) -> bool:
        """
        Overload the event filtering for the customized some specific events.

        In particular, we are taking care of the following events and sources:
            - FocusIn for caption_field, description_input and extrainfo_input:
                -> Used to enable/disable the customization edit / special copy and paste tool buttons.
            - MouseButtonDblClick for image_preview
                -> Used to open the image in the external viewer.

        Parameters
        ----------
        object_: QObject
            The object emitting the event.
        event: QEvent
            The emitted event.

        Returns
        -------
        bool
        """

        # edit controls
        edit_ctrls = [self.markdown_font_tool_button, self.markdown_paragraph_tool_button]
        adv_copy_ctrls = [self.copy_custom_value_button, self.paste_custom_value_button]
        if event.type() == QEvent.FocusIn and object_ in [self.description_input, self.extrainfo_input]:
            for ctrl in adv_copy_ctrls:
                ctrl.setEnabled(True)
            if not self.custom_data_dict_available:
                self.paste_custom_value_button.setEnabled(False)
            for ctrl in edit_ctrls:
                ctrl.setEnabled(True)

        if event.type() == QEvent.FocusIn and object_ in [self.caption_field]:

            for ctrl in edit_ctrls:
                ctrl.setEnabled(False)
            for ctrl in adv_copy_ctrls:
                ctrl.setEnabled(True)
            if not self.custom_data_dict_available:
                self.paste_custom_value_button.setEnabled(False)

        if event.type() == QEvent.MouseButtonDblClick and object_ == self.image_preview:
            self.open_external_image_viewer()

        return super(ProtocolEditor, self).eventFilter(object_, event)

    @Slot(QAction)
    def triggered_copy_custom_action(self, action: QAction):
        """
        React to a change in the copy custom tool button.

        The copy tool button is featuring a menu with several options. When the user selects a specific option for the
        copy, the same option is selected for the paste.

        Parameters
        ----------
        action: QAction
            Action selected in the copy_custom_value_button menu
        """
        for i, a in enumerate(self.copy_custom_value_button.menu().actions()):
            if a.text() == action.text():
                self.paste_custom_value_button.setDefaultAction(self.paste_custom_value_button.menu().actions()[i])
                break

    def generate_copy_custom_value_button(self) -> QMenu:
        """Generate the menu to be attached to the copy custom values button"""
        scheme = {
            'copy_all_custom_fields': {
                'icon': ':/resources/icons8-copy-all-48.png',
                'text': 'Copy all',
                'slot': lambda: self.copy_custom_values('all'),
            },
            'copy_caption': {
                'icon': ':/resources/icons8-copy-caption-48.png',
                'text': 'Copy caption',
                'slot': lambda: self.copy_custom_values('caption'),
            },
            'copy_description': {
                'icon': ':/resources/icons8-copy-description-48.png',
                'text': 'Copy description',
                'slot': lambda: self.copy_custom_values('description'),
            },
            'copy_extra': {
                'icon': ':/resources/icons8-copy-extra-48.png',
                'text': 'Copy extra',
                'slot': lambda: self.copy_custom_values('extra'),
            }
        }
        return generate_tool_button_menu_from_scheme(menu=None, parent=self.copy_custom_value_button,
                                                     menu_scheme=scheme)

    def generate_paste_custom_value_button(self) -> QMenu:
        """Generate the menu to be attached to the paste custom values button"""
        scheme = {
            'copy_all_custom_fields': {
                'icon': ':/resources/icons8-paste-all-48.png',
                'text': 'Paste all',
                'slot': lambda: self.paste_custom_values('all'),
            },
            'copy_caption': {
                'icon': ':/resources/icons8-paste-caption-48.png',
                'text': 'Paste caption',
                'slot': lambda: self.paste_custom_values('caption'),
            },
            'copy_description': {
                'icon': ':/resources/icons8-paste-description-48.png',
                'text': 'Paste description',
                'slot': lambda: self.paste_custom_values('description'),
            },
            'copy_extra': {
                'icon': ':/resources/icons8-paste-extra-48.png',
                'text': 'Paste extra',
                'slot': lambda: self.paste_custom_values('extra'),
            }
        }
        return generate_tool_button_menu_from_scheme(menu=None, parent=self.copy_custom_value_button,
                                                     menu_scheme=scheme)

    def generate_markdown_paragraph_tool_button(self) -> QMenu:
        """Generate the menu to be attached to the Markdown paragraph button"""
        scheme = {
            'link': {
                'icon': ':/resources/icons8-hyperlink-48.png',
                'text': 'Insert generic link...',
                'slot': lambda: self.edit_custom_text('link'),
            },
            'bulleted': {
                'icon': ':/resources/icons8-bulleted-list-48.png',
                'text': 'Insert bulleted list...',
                'slot': lambda: self.edit_custom_text('bullet')
            },
            'numbered': {
                'icon': ':/resources/icons8-numbered-list-48.png',
                'text': 'Insert numbered list...',
                'slot': lambda: self.edit_custom_text('number'),
            },
        }
        return generate_tool_button_menu_from_scheme(menu=None, parent=self.markdown_paragraph_tool_button,
                                                     menu_scheme=scheme)

    def generate_markdown_font_tool_button(self) -> QMenu:
        """Generate the menu to be attached to the markdown font button"""
        scheme = {
            'bold_action': {
                'icon': ':/resources/icons8-bold-48.png',
                'text': 'Bold',
                'slot': lambda: self.edit_custom_text('bold')
            },
            'italic_action': {
                'icon': ':/resources/icons8-italic-48.png',
                'text': 'Italic',
                'slot': lambda: self.edit_custom_text('italic')
            },
            'underline_action': {
                'icon': ':/resources/icons8-underline-48.png',
                'text': 'Underline',
                'slot': lambda: self.edit_custom_text('underline')
            },
            'strikeout': {
                'icon': ':/resources/icons8-strikethrough-48.png',
                'text': 'Strikeout',
                'slot': lambda: self.edit_custom_text('strikeout')
            },
            'subscript': {
                'icon': ':/resources/icons8-subscript-48.png',
                'text': 'Subscript',
                'slot': lambda: self.edit_custom_text('subscript')
            },
            'superscript': {
                'icon': ':/resources/icons8-superscript-48.png',
                'text': 'Superscript',
                'slot': lambda: self.edit_custom_text('superscript')
            },
        }

        return generate_tool_button_menu_from_scheme(menu=None, parent=self.markdown_font_tool_button,
                                                     menu_scheme=scheme)

    def generate_edit_dropdown_menu(self) -> QMenu:
        """Generate the menu to be attached to the edit dropdown button"""
        scheme = {
            'rename_action': {
                'icon': ':/resources/icons8-rename-48.png',
                'text': 'Rename element...',
                'slot': self.rename_protocol_element,
            },
            'move_action': {
                'icon': ':/resources/icons8-move-up-row-48.png',
                'text': 'Move to another sample...',
                'slot': self.move_element_to_another_sample,
            },

        }

        return generate_tool_button_menu_from_scheme(menu=None, parent=self.edit_dropdown_button, menu_scheme=scheme)

    def generate_recycle_dropdown_menu(self) -> QMenu:
        """Generate the menu to be attached to the recycle dropdown button"""
        scheme = {
            'recycle_action': {
                'icon': ':/resources/icons8-recycle-48.png',
                'text': 'Recycle element...',
                'slot': self.recycle_protocol_element,
            },
            'delete_action': {
                'icon': ':/resources/icons8-trash-can-48.png',
                'text': 'Delete element...',
                'slot': self.delete_protocol_element,
            },
            'restore_action': {
                'icon': ':/resources/icons8-trash-restore-48.png',
                'text': 'Restore element...',
                'slot': self.restore_element_from_trash,
            },

        }
        return generate_tool_button_menu_from_scheme(menu=None, parent=self.recycle_dropdown_button, menu_scheme=scheme)

    def restore_element_from_trash(self):
        """
        Restore one element from the recycling bin.

        Only Microscope Pictures and Videos can be restored.
        """

        # let's get the sample list (those are sample full names)
        sample_list = [self.sample_selector.itemText(i) for i in range(self.sample_selector.count())]

        # we need the base path to be prepended to the sample full name to have the path.
        protocol_path = self.parent.protocol_folder_path

        # we need the current sample. we can get it from the currently selected item in the tree view.
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        model_item = self.tree_model.itemFromIndex(model_index)
        item_type = model_item.data(UserRole.ITEM_TYPE)
        if item_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            sample_item = model_item.parent()
            sample_full_name = sample_item.data(UserRole.SAMPLE_FULL_NAME)
        elif item_type == ElementType.SAMPLE:
            sample_full_name = model_item.data(UserRole.SAMPLE_FULL_NAME)
        elif item_type in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:
            if model_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                sample_full_name = model_item.parent().data(UserRole.SAMPLE_FULL_NAME)
            else:
                sample_full_name = 'Protocol'
        else:
            sample_full_name = None

        # create an instance of the RecoverElementDialog
        dialog = RecoverElementDialog(parent=self, sample_list=sample_list,
                                      protocol_path=protocol_path, current_sample=sample_full_name)

        # execute the dialog
        if dialog.exec_():

            # this is a list of selected items to be restored.
            proxy_indexes = dialog.file_list_view.selectionModel().selectedIndexes()

            # elements in the basket bin are either
            # MICROSCOPE_PIC, VIDEO_FILE, ATTACHMENT or OPTICAL IMAGES but
            # in the bin we cannot check the type from the tree_model.
            # we need the type in order to perform a proper recycling.
            # we can use the type_guessers as in the watchdog.
            type_guessers = {}
            image_file_matching = regexp_repository.get_matching('IMAGEFILE')
            image_file_exclude = None
            type_guessers[str(ElementType.MICROSCOPE_PIC)] = \
                (ElementTypeGuesser(image_file_matching, image_file_exclude),
                 ElementType.MICROSCOPE_PIC)
            video_file_include_pattern = regexp_repository.get_matching('VIDEO')
            video_file_exclude_pattern = None
            type_guessers[str(ElementType.VIDEO_FILE)] = \
                (ElementTypeGuesser(video_file_include_pattern, video_file_exclude_pattern),
                 ElementType.VIDEO_FILE)
            attachment_file_include_pattern = regexp_repository.get_matching('ATTACHMENT')
            attachment_file_exclude_pattern = None
            type_guessers[str(ElementType.ATTACHMENT_FILE)] = \
                (ElementTypeGuesser(attachment_file_include_pattern, attachment_file_exclude_pattern),
                 ElementType.ATTACHMENT_FILE)
            optical_image_include_pattern = regexp_repository.get_matching('OPTICAL_IMAGE')
            optical_image_exclude_pattern = None
            type_guessers[str(ElementType.OPTICAL_PIC)] = \
                (ElementTypeGuesser(optical_image_include_pattern, optical_image_exclude_pattern),
                 ElementType.OPTICAL_PIC)

            # loop over all indexes
            for proxy_index in proxy_indexes:
                model_index = dialog.file_list_model_proxy.mapToSource(proxy_index)
                element_full_path = Path(model_index.data(UserRole.ELEMENT_FULL_PATH))
                old_path = element_full_path.relative_to(protocol_path)
                new_path = old_path.parent.parent / old_path.name

                # use the ElementTypeGuesser to guess the type of what we are restoring.
                item_type = None
                for (guesser, etype) in type_guessers.values():
                    if guesser.is_ok(element_full_path):
                        item_type = etype
                        break
                if item_type in [ElementType.VIDEO_FILE, ElementType.MICROSCOPE_PIC, ElementType.ATTACHMENT_FILE,
                                 ElementType.OPTICAL_PIC]:
                    # we can perform the recycling of the custom values
                    # this is a bit confusing. The basket bin is on the local_path pc, not necessarily on the
                    # image server, while the key in the yaml files are from paths from the image server.
                    # so actually now we cannot use the protocol_folder, but we shall use the mirror folder
                    # if it exists. To avoid this problem just use the autolog.path that is always pointing
                    # to the image server.
                    old_key = str(self.autolog.path / old_path)
                    new_key = str(self.autolog.path / new_path)
                    self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict, item_type, old_key, new_key)
                else:
                    log.warning('Recycling of other protocol elements is not possible.')

                command = FileSystemCommand(FSCommandType.RENAME_FILE, old_path, new_path)
                self.execute_filesystem_command.emit(command)
                autotools.dump_yaml_file(self.autolog.yamlDict, self.autolog.yamlFilename)

    def generate_metadata_context_menu(self) -> QMenu:
        """Generate the context menu for the metadata table view"""

        # Use the standard context menu as a starting point for the customization.
        context_menu = self.description_input.createStandardContextMenu()
        context_menu.addSeparator()

        menu_scheme = {
            'copy_special_menu': {
                'type': QMenu,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'copy_special_menu',
                'obj': None,
                'text': 'Copy special...',
                'icon': ':/resources/icons8-copy-48.png',
                'show_when_flag': MetadataVisibilityFlag.WITH_ITEM,
                'separator_after': True,
            },
            'copy_single_value': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_special_menu',
                'obj': None,
                'name': 'copy_single_value',
                'text': 'Copy current value to clipboard',
                'icon': ':/resources/icons8-copy-single-48.png',
                'slot': lambda: self.copy_metadata_to_clipboard('single_value'),
                'show_when_flag': MetadataVisibilityFlag.WITH_ITEM,
                'separator_after': False,
            },
            'copy_single_pair': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_special_menu',
                'obj': None,
                'name': 'copy_single_pair',
                'text': 'Copy current key/value pair to clipboard',
                'icon': ':/resources/icons8-copy-pair-48.png',
                'slot': lambda: self.copy_metadata_to_clipboard('single_pair'),
                'show_when_flag': MetadataVisibilityFlag.WITH_ITEM,
                'separator_after': False,
            },
            'copy_all_pairs': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_special_menu',
                'obj': None,
                'name': 'copy_all_pairs',
                'text': 'Copy all metadata to clipboard',
                'icon': ':/resources/icons8-copy-all-48.png',
                'slot': lambda: self.copy_metadata_to_clipboard('all'),
                'show_when_flag': MetadataVisibilityFlag.WITH_ITEM,
                'separator_after': False,
            },
            'save_metadata_to_file': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'save_metadata_to_file',
                'text': 'Save metadata to CSV file',
                'icon': ':/resources/icons8-save-as-48.png',
                'slot': lambda: self.save_metadata_to_file('all'),
                'show_when_flag': MetadataVisibilityFlag.WITH_ITEM,
                'separator_after': False,
            },
        }
        return generate_context_menu_from_scheme(context_menu, self.metadata_table, menu_scheme)

    def generate_custom_edit_context_menu(self) -> QMenu:
        """Generate the context menu for the caption/description/extra input fields"""

        # Use the standard context menu as a starting point for the customization.
        context_menu = self.description_input.createStandardContextMenu()
        context_menu.addSeparator()

        menu_scheme = {
            'custom_fields_menu': {
                'type': QMenu,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'custom_fields_menu',
                'obj': None,
                'text': 'Customization fields menu',
                'icon': ':/resources/icons8-design-48.png',
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': True,
            },
            'copy_custom_fields': {
                'type': QMenu,
                'parent_name': 'custom_fields_menu',
                'parent_obj': None,
                'name': 'copy_custom_fields',
                'obj': None,
                'text': 'Copy custom fields',
                'icon': ':/resources/icons8-copy-48.png',
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'copy_all_custom_fields': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_custom_fields',
                'obj': None,
                'name': 'copy_all_custom_fields',
                'text': 'Copy all custom fields to clipboard',
                'icon': ':/resources/icons8-copy-all-48.png',
                'slot': lambda: self.copy_custom_values('all'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'copy_caption': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_custom_fields',
                'obj': None,
                'name': 'copy_caption',
                'text': 'Copy caption to clipboard',
                'icon': ':/resources/icons8-copy-caption-48.png',
                'slot': lambda: self.copy_custom_values('caption'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'copy_description': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_custom_fields',
                'obj': None,
                'name': 'copy_description',
                'text': 'Copy description to clipboard',
                'icon': ':/resources/icons8-copy-description-48.png',
                'slot': lambda: self.copy_custom_values('description'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'copy_extra': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_custom_fields',
                'obj': None,
                'name': 'copy_extra',
                'text': 'Copy extra to clipboard',
                'icon': ':/resources/icons8-copy-extra-48.png',
                'slot': lambda: self.copy_custom_values('extra'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'paste_custom_fields': {
                'type': QMenu,
                'parent_name': 'custom_fields_menu',
                'parent_obj': None,
                'name': 'paste_custom_fields',
                'obj': None,
                'text': 'Paste custom fields',
                'icon': ':/resources/icons8-paste-special-48.png',
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'paste_all_custom_fields': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'paste_custom_fields',
                'obj': None,
                'name': 'paste_all_custom_fields',
                'text': 'Paste all custom fields',
                'icon': ':/resources/icons8-paste-special-48.png',
                'slot': lambda: self.paste_custom_values('all'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'paste_caption': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'paste_custom_fields',
                'obj': None,
                'name': 'paste_caption',
                'text': 'Paste caption',
                'icon': ':/resources/icons8-paste-special-48.png',
                'slot': lambda: self.paste_custom_values('caption'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'paste_description': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'paste_custom_fields',
                'obj': None,
                'name': 'paste_description',
                'text': 'Paste description',
                'icon': ':/resources/icons8-paste-special-48.png',
                'slot': lambda: self.paste_custom_values('description'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'paste_extra': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'paste_custom_fields',
                'obj': None,
                'name': 'paste_extra',
                'text': 'Paste extra',
                'icon': ':/resources/icons8-paste-special-48.png',
                'slot': lambda: self.paste_custom_values('extra'),
                'show_when_flag': CustomEditVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'mark_down_menu': {
                'type': QMenu,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'mark_down_menu',
                'obj': None,
                'text': 'Markdown menu',
                'icon': ':/resources/icons8-markdown-48.png',
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': True,
            },
            'mark_down_edit_menu': {
                'type': QMenu,
                'parent_name': 'mark_down_menu',
                'parent_obj': None,
                'name': 'mark_down_edit_menu',
                'obj': None,
                'text': 'Text edit menu',
                'icon': ':/resources/icons8-choose-font-48.png',
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': True,
            },
            'insert_bold_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_edit_menu',
                'obj': None,
                'name': 'insert_bold_action',
                'text': 'Insert bold',
                'icon': ':/resources/icons8-bold-48.png',
                'slot': lambda: self.edit_custom_text('bold'),
                'short_cut_key_sequence': 'Ctrl+Shift+B',
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_italic_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_edit_menu',
                'obj': None,
                'name': 'insert_italic_action',
                'text': 'Insert italic',
                'icon': ':/resources/icons8-italic-48.png',
                'slot': lambda: self.edit_custom_text('italic'),
                'short_cut_key_sequence': 'Ctrl+Shift+I',
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_underline_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_edit_menu',
                'obj': None,
                'name': 'insert_underline_action',
                'text': 'Insert underline',
                'icon': ':/resources/icons8-underline-48.png',
                'slot': lambda: self.edit_custom_text('underline'),
                'short_cut_key_sequence': 'Ctrl+Shift+U',
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_strikeout_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_edit_menu',
                'obj': None,
                'name': 'insert_strikeout_action',
                'text': 'Insert strikeout',
                'icon': ':/resources/icons8-strikethrough-48.png',
                'short_cut_key_sequence': 'Ctrl+Shift+T',
                'slot': lambda: self.edit_custom_text('strikeout'),
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': True,
            },
            'insert_subscript_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_edit_menu',
                'obj': None,
                'name': 'insert_subscript_action',
                'text': 'Insert subscript',
                'icon': ':/resources/icons8-subscript-48.png',
                'slot': lambda: self.edit_custom_text('subscript'),
                'short_cut_key_sequence': 'Ctrl+Shift+-',
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_superscript_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_edit_menu',
                'obj': None,
                'name': 'insert_superscript_action',
                'text': 'Insert superscript',
                'icon': ':/resources/icons8-superscript-48.png',
                'short_cut_key_sequence': 'Ctrl+Shift++',
                'slot': lambda: self.edit_custom_text('superscript'),
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_link_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_menu',
                'obj': None,
                'name': 'insert_link_action',
                'text': 'Insert link',
                'icon': ':/resources/icons8-hyperlink-48.png',
                'slot': lambda: self.edit_custom_text('link'),
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_bullet_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_menu',
                'obj': None,
                'name': 'insert_bullet_action',
                'text': 'Insert bulleted list',
                'icon': ':/resources/icons8-bulleted-list-48.png',
                'slot': lambda: self.edit_custom_text('bullet'),
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },
            'insert_numbered_list_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'mark_down_menu',
                'obj': None,
                'name': 'insert_numbered_list_action',
                'text': 'Insert numbered list',
                'icon': ':/resources/icons8-numbered-list-48.png',
                'slot': lambda: self.edit_custom_text('number'),
                'show_when_flag': CustomEditVisibilityFlag.MARKDOWN,
                'separator_after': False,
            },

        }
        return generate_context_menu_from_scheme(context_menu, self.description_input, menu_scheme)

    def generate_tree_view_context_menu(self) -> QMenu:
        """Generate the context menu for the tree view"""

        context_menu = None

        menu_scheme = {
            'expand_all_action': {
                'type': QAction,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'expand_all',
                'obj': None,
                'text': 'Expand all',
                'icon': ':/resources/icons8-expand-arrow-48.png',
                'slot': self.expand_all_elements,
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'collapse_all_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'collapse_all',
                'text': 'Collapse all',
                'icon': ':/resources/icons8-collapse-arrow-48.png',
                'slot': self.collapse_all_elements,
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'scroll_to_last': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'scroll_to_last',
                'text': 'Go to last inserted item',
                'icon': ':/resources/icons8-sniper-48.png',
                'slot': self.scroll_to_last_inserted_item,
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'markdown_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'markdown_menu',
                'text': 'Markdown tools',
                'icon': ':/resources/icons8-markdown-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'markdown_link_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'markdown_menu',
                'parent_obj': None,
                'name': 'markdown_link_menu',
                'text': 'Markdown link tools',
                'icon': ':/resources/icons8-tools-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'generic_link': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_link_menu',
                'obj': None,
                'name': 'generic_link',
                'text': 'Copy generic link to clipboard',
                'icon': ':/resources/icons8-hyperlink-48.png',
                'slot': lambda: QApplication.clipboard().setText('[link_text](link_URL)'),
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'specific_link': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_link_menu',
                'obj': None,
                'name': 'specific_link',
                'text': 'Copy anchor link of this element to clipboard',
                'icon': ':/resources/icons8-hyperlink-48.png',
                'slot': self.copy_anchor_link_markdown_to_clipboard,
                'show_when_flag': ElementTypeVisitiliyFlag.ANCHORABLE_ITEM,
                'separator_after': False,
            },
            'markdown_image_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'markdown_menu',
                'parent_obj': None,
                'name': 'markdown_image_menu',
                'text': 'Markdown image tools',
                'icon': ':/resources/icons8-picture-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'generic_image': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_image_menu',
                'obj': None,
                'name': 'generic_link',
                'text': 'Copy generic inline image to clipboard',
                'slot': lambda: QApplication.clipboard().setText('![image_alt_text](image_URL "image_title")'),
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'markdown_selected_image_thumb': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_image_menu',
                'obj': None,
                'name': 'markdown_selected_image_thumb',
                'text': 'Copy inline thumbnail image to clipboard',
                'icon': ':/resources/icons8-picture-48.png',
                'slot': self.copy_image_markdown_to_clipboard,
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': False,
            },
            'open_browser_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'open_browser',
                'text': 'Open a browser window here...',
                'icon': ':/resources/icons8-folder-48.png',
                'slot': self.open_protocol_folder,
                'show_when_flag': ElementTypeVisitiliyFlag.PROTOCOL_ITEM,
                'separator_after': False,
            },
            'copy_sample_path_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'copy_sample_path',
                'text': 'Copy sample path',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': self.copy_sample_path,
                'show_when_flag': ElementTypeVisitiliyFlag.SAMPLE,
                'separator_after': True,
            },
            'copy_full_path_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'copy_element_path',
                'text': 'Copy element path',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': self.copy_element_path,
                'show_when_flag': ElementTypeVisitiliyFlag.PROTOCOL_ITEM,
                'separator_after': True,
            },
            'change_sample_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'change_sample',
                'text': 'Move item in another sample...',
                'icon': ':/resources/icons8-move-up-row-48.png',
                'short_cut_key_sequence': 'Ctrl+F2',
                'slot': self.move_element_to_another_sample,
                'show_when_flag': ElementTypeVisitiliyFlag.MOVABLE_ITEM,
                'separator_after': False,
            },
            'rename_item_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'rename_action',
                'text': 'Rename item...',
                'icon': ':/resources/icons8-rename-48.png',
                'short_cut_key_sequence': 'F2',
                'slot': self.rename_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.RENAMEBABLE_ITEM,
                'separator_after': False,
            },
            'recycle_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'recycle_menu',
                'text': 'Recycle / delete / recover',
                'icon': ':/resources/icons8-recycle-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'delete_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'recycle_menu',
                'obj': None,
                'name': 'delete_action',
                'text': 'Delete item...',
                'icon': ':/resources/icons8-trash-can-48.png',
                'slot': self.delete_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.DELETABLE_ITEM,
                'separator_after': False,
            },
            'recycle_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'recycle_menu',
                'obj': None,
                'name': 'recycle_action',
                'text': 'Recycle item...',
                'icon': ':/resources/icons8-recycle-48.png',
                'slot': self.recycle_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.RECYCLABLE_ITEM,
                'separator_after': False,
            },
            'recover_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'recycle_menu',
                'obj': None,
                'name': 'recover_action',
                'text': 'Recover item from bin...',
                'icon': ':/resources/icons8-trash-restore-48.png',
                'slot': self.recycle_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.RECOVARABLE_ITEM,
                'separator_after': False,
            },
            'update_protocol_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'update_protocol_action',
                'text': 'Update protocol',
                'icon': ':/resources/icons8-upload-to-cloud-48.png',
                'short_cut_key_sequence': 'Ctrl+S',
                'slot': self.update_protocol,
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },

        }
        return generate_context_menu_from_scheme(context_menu, self.autolog_tree_viewer, menu_scheme)

    def generate_sample_list_view_context_menu(self) -> QMenu:
        """Generate the context menu for the sample list view"""

        context_menu = None

        menu_scheme = {
            'markdown_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'markdown_menu',
                'text': 'Markdown tools',
                'icon': ':/resources/icons8-markdown-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'markdown_link_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'markdown_menu',
                'parent_obj': None,
                'name': 'markdown_link_menu',
                'text': 'Markdown link tools',
                'icon': ':/resources/icons8-tools-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'generic_link': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_link_menu',
                'obj': None,
                'name': 'generic_link',
                'text': 'Copy generic link to clipboard',
                'icon': ':/resources/icons8-hyperlink-48.png',
                'slot': lambda: QApplication.clipboard().setText('[link_text](link_URL)'),
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'specific_link': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_link_menu',
                'obj': None,
                'name': 'specific_link',
                'text': 'Copy anchor link of this element to clipboard',
                'icon': ':/resources/icons8-hyperlink-48.png',
                'slot': self.copy_anchor_link_markdown_to_clipboard,
                'show_when_flag': ElementTypeVisitiliyFlag.ANCHORABLE_ITEM,
                'separator_after': False,
            },
            'markdown_image_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'markdown_menu',
                'parent_obj': None,
                'name': 'markdown_image_menu',
                'text': 'Markdown image tools',
                'icon': ':/resources/icons8-picture-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'generic_image': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_image_menu',
                'obj': None,
                'name': 'generic_link',
                'text': 'Copy generic inline image to clipboard',
                'slot': lambda: QApplication.clipboard().setText('![image_alt_text](image_URL "image_title")'),
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'markdown_selected_image_thumb': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'markdown_image_menu',
                'obj': None,
                'name': 'markdown_selected_image_thumb',
                'text': 'Copy inline thumbnail image to clipboard',
                'icon': ':/resources/icons8-picture-48.png',
                'slot': self.copy_image_markdown_to_clipboard,
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': False,
            },
            'open_browser_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'open_browser',
                'text': 'Open a browser window here...',
                'icon': ':/resources/icons8-folder-48.png',
                'slot': self.open_protocol_folder,
                'show_when_flag': ElementTypeVisitiliyFlag.PROTOCOL_ITEM,
                'separator_after': False,
            },
            'copy_sample_path_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'copy_sample_path',
                'text': 'Copy sample path',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': self.copy_sample_path,
                'show_when_flag': ElementTypeVisitiliyFlag.SAMPLE,
                'separator_after': True,
            },
            'copy_full_path_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'copy_element_path',
                'text': 'Copy element path',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': self.copy_element_path,
                'show_when_flag': ElementTypeVisitiliyFlag.PROTOCOL_ITEM,
                'separator_after': True,
            },
            'change_sample_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'change_sample',
                'text': 'Move item in another sample...',
                'icon': ':/resources/icons8-move-up-row-48.png',
                'slot': self.move_element_to_another_sample,
                'show_when_flag': ElementTypeVisitiliyFlag.MOVABLE_ITEM,
                'separator_after': False,
            },
            'rename_item_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'rename_action',
                'text': 'Rename item...',
                'icon': ':/resources/icons8-rename-48.png',
                'slot': self.rename_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.RENAMEBABLE_ITEM,
                'separator_after': False,
            },
            'recycle_menu': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'recycle_menu',
                'text': 'Recycle / delete / recover',
                'icon': ':/resources/icons8-recycle-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': True,
            },
            'delete_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'recycle_menu',
                'obj': None,
                'name': 'delete_action',
                'text': 'Delete item...',
                'icon': ':/resources/icons8-trash-can-48.png',
                'slot': self.delete_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.DELETABLE_ITEM,
                'separator_after': False,
            },
            'recycle_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'recycle_menu',
                'obj': None,
                'name': 'recycle_action',
                'text': 'Recycle item...',
                'icon': ':/resources/icons8-recycle-48.png',
                'slot': self.recycle_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.RECYCLABLE_ITEM,
                'separator_after': False,
            },
            'recover_action': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'recycle_menu',
                'obj': None,
                'name': 'recover_action',
                'text': 'Recover item from bin...',
                'icon': ':/resources/icons8-trash-restore-48.png',
                'slot': self.recycle_protocol_element,
                'show_when_flag': ElementTypeVisitiliyFlag.RECOVARABLE_ITEM,
                'separator_after': False,
            },
            'update_protocol_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'update_protocol_action',
                'text': 'Update protocol',
                'icon': ':/resources/icons8-upload-to-cloud-48.png',
                'slot': self.update_protocol,
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },

        }
        return generate_context_menu_from_scheme(context_menu, self.sample_list_view, menu_scheme)

    def generate_image_preview_context_menu(self) -> QMenu:
        """Generate the context menu for the image preview"""

        context_menu = None

        menu_scheme = {
            'open_external_viewer': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'open_external_viewer',
                'text': 'Show full screen in another window...',
                'icon': ':/resources/icons8-fullscreen-48.png',
                'slot': self.open_external_image_viewer,
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': False,
            },
            'open_browser_action': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'open_browser',
                'text': 'Open a browser window here...',
                'icon': ':/resources/icons8-folder-48.png',
                'slot': self.open_protocol_folder,
                'show_when_flag': ElementTypeVisitiliyFlag.ALWAYS,
                'separator_after': False,
            },
            'copy_preview': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'copy_preview',
                'text': 'Copy the thumbnail to clipboard',
                'icon': ':/resources/icons8-picture-48.png',
                'slot': self.copy_image_to_clipboard,
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': False,
            },
            'copy_path': {
                'type': QAction,
                'parent_obj': context_menu,
                'parent_name': 'root',
                'obj': None,
                'name': 'copy_path',
                'text': 'Copy image path to clipboard',
                'icon': ':/resources/icons8-copy-48.png',
                'slot': self.copy_element_path,
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': False,
            },
            'copy_image_url': {
                'type': QMenu,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'copy_image_url',
                'text': 'Copy image URLs',
                'icon': ':/resources/icons8-copy-link-48.png',
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': True,
            },
            'copy_image_tiff_url': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_image_url',
                'obj': None,
                'name': 'copy_image_tiff_url',
                'text': 'Copy TIFF URL to clipboard',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': lambda: self.copy_image_url(autotools.ImageType.TIFF),
                'show_when_flag': ElementTypeVisitiliyFlag.MICROSCOPE_PIC,
                'separator_after': False,
            },
            'copy_image_png_url': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_image_url',
                'obj': None,
                'name': 'copy_image_png_url',
                'text': 'Copy PNG URL to clipboard',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': lambda: self.copy_image_url(autotools.ImageType.PNG),
                'show_when_flag': ElementTypeVisitiliyFlag.IMAGE_ITEM,
                'separator_after': False,
            },
            'copy_image_thumb_url': {
                'type': QAction,
                'parent_obj': None,
                'parent_name': 'copy_image_url',
                'obj': None,
                'name': 'copy_image_thumb_url',
                'text': 'Copy thumbnail URL to clipboard',
                'icon': ':/resources/icons8-copy-link-48.png',
                'slot': lambda: self.copy_image_url(autotools.ImageType.THUMBNAIL),
                'show_when_flag': ElementTypeVisitiliyFlag.MICROSCOPE_PIC,
                'separator_after': False,
            },
        }
        return generate_context_menu_from_scheme(context_menu, self.image_preview, menu_scheme)

    def on_custom_edit_context_menu_request(self, pos: QPoint):
        """React to a request for context menu for the customization fields"""

        widget = self.sender()

        if widget.objectName() in ['description_input', 'extrainfo_input']:
            show_flag = CustomEditVisibilityFlag.MARKDOWN
            global_pos = widget.viewport().mapToGlobal(pos)
        elif widget.objectName() in ['caption_field']:
            show_flag = CustomEditVisibilityFlag.CAPTION
            global_pos = widget.mapToGlobal(pos)
        else:
            show_flag = CustomEditVisibilityFlag.NEVER
            global_pos = widget.mapToGlobal(pos)

        filter_context_menu(self.custom_edit_context_menu, show_flag)
        self.custom_edit_context_menu.exec(global_pos)

    def on_tree_context_menu_request(self, pos: QPoint):
        """
        React to a right click on the tree viewer.

        Parameters
        ----------
        pos: QPoint
            The position where the mouse was clicked.

        Returns
        -------

        """
        # this is the item where the mouse was clicked. If the mouse was clicked on the white area, then item will be
        # None.
        item = self.tree_model_proxy.mapToSource(self.autolog_tree_viewer.indexAt(pos))
        if item is None or not item.isValid():
            show_flag = ElementTypeVisitiliyFlag.NO_ITEM
        else:
            show_flag = autotools.get_visibility_from_item_type(item.data(UserRole.ITEM_TYPE))

        filter_context_menu(self.tree_viewer_context_menu, show_flag)
        self.tree_viewer_context_menu.exec(self.autolog_tree_viewer.viewport().mapToGlobal(pos))

    def on_metadata_context_menu_request(self, pos: QPoint):
        """
        React to a right click on the metadata table viewer.

        Parameters
        ----------
        pos: QPoint
            The position where the mouse was clicked.

        Returns
        -------

        """
        item = self.metadata_proxy_model.mapToSource(self.metadata_table.indexAt(pos))
        if item is None or not item.isValid():
            show_flag = MetadataVisibilityFlag.WITHOUT_ITEM
        else:
            show_flag = MetadataVisibilityFlag.WITH_ITEM

        filter_context_menu(self.metadata_table_context_menu, show_flag)
        self.metadata_table_context_menu.exec(self.metadata_table.viewport().mapToGlobal(pos))

    def on_sample_list_context_menu_request(self, pos: QPoint):
        """
        React to a right click on the tree viewer.

        Parameters
        ----------
        pos: QPoint
            The position where the mouse was clicked.

        Returns
        -------

        """
        # this is the item where the mouse was clicked. If the mouse was clicked on the white area, then item will be
        # None.
        item = self.tree_model_proxy.mapToSource(self.sample_list_view.indexAt(pos))
        if item is None or not item.isValid():
            show_flag = ElementTypeVisitiliyFlag.NO_ITEM
        else:
            show_flag = autotools.get_visibility_from_item_type(item.data(UserRole.ITEM_TYPE))

        filter_context_menu(self.sample_list_view_context_menu, show_flag)
        self.sample_list_view_context_menu.exec(self.sample_list_view.viewport().mapToGlobal(pos))

    def on_image_preview_context_menu_request(self, pos: QPoint):
        """React to a request for context menu for the image preview"""

        # get the item
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        if proxy_index.isValid():
            model_index = self.tree_model_proxy.mapToSource(proxy_index)
            current_item = self.tree_model.itemFromIndex(model_index)
        else:
            current_item = None

        if current_item is None:
            show_flag = ElementTypeVisitiliyFlag.NO_ITEM
        else:
            show_flag = autotools.get_visibility_from_item_type(current_item.data(UserRole.ITEM_TYPE))

        filter_context_menu(self.image_preview_context_menu, show_flag)
        self.image_preview_context_menu.exec(self.image_preview.mapToGlobal(pos))

    def copy_metadata_to_clipboard(self, what: str):
        """Copy the currently selected metadata item to the clipboard"""
        text_to_be_copied = self.get_metadata_text(what)
        if text_to_be_copied:
            QApplication.clipboard().setText(text_to_be_copied)

    def save_metadata_to_file(self, what: str = 'all'):
        """Save the currently selected metadata item to a file"""
        text_to_be_copied = self.get_metadata_text(what)
        if text_to_be_copied:
            directory = Path.home() / Path('Documents')
            returnpath = QFileDialog.getSaveFileName(self, 'Metadata file', directory=str(directory),
                                                     filter='CSV file (*.csv)')
            if returnpath:
                csvfile = Path(returnpath[0])
                with open(csvfile, 'w') as f:
                    f.write(text_to_be_copied)

    def get_metadata_text(self, what: str) -> str:
        """
        Get the currently selected metadata item as formatted text

        what: str
            Select what kind of information.
            Possible values:
            'single_value': get only the value of the currently selected row
            'single_pair': get both key and value of the currently selected row
            'all': get all keys and values
        """
        current_proxy_index = self.metadata_table.selectionModel().currentIndex()
        current_index = self.metadata_proxy_model.mapToSource(current_proxy_index)
        if what.lower() == 'single_value':
            if current_index.column() == 0:  # the user selected a key, but we want to have the value
                value_index = self.metadata_model.index(current_index.row(), 1, current_index.parent())
                text_to_be_copied = value_index.data(Qt.DisplayRole)
            else:  # the user was selecting a value.
                text_to_be_copied = current_index.data(Qt.DisplayRole)
        elif what.lower() == 'single_pair':
            if current_index.column() == 0:  # the user is selecting a key
                key_index = current_index
                value_index = self.metadata_model.index(current_index.row(), 1, current_index.parent())
            else:  # the user is selecting a value
                key_index = self.metadata_model.index(current_index.row(), 0, current_index.parent())
                value_index = current_index

            text_to_be_copied = f'{key_index.data(Qt.DisplayRole)}:{chr(9)} {value_index.data(Qt.DisplayRole)}'

        elif what.lower() == 'all':
            text_to_be_copied = ''
            for row in range(self.metadata_model.rowCount()):
                key_index = self.metadata_model.index(row, 0, self.metadata_table.rootIndex())
                value_index = self.metadata_model.index(row, 1, self.metadata_table.rootIndex())
                text_to_be_copied += f'{key_index.data(Qt.DisplayRole)}:{chr(9)} {value_index.data(Qt.DisplayRole)}' \
                                     f'{chr(10)}'
        else:
            text_to_be_copied = ''

        return text_to_be_copied

    def copy_image_markdown_to_clipboard(self):
        """Copy the markdown template for an image in the clipboard"""

        link = self.get_image_url('thumbnail')
        mark = f'![image_alt_text]({link})'
        QApplication.clipboard().setText(mark)

    def copy_anchor_link_markdown_to_clipboard(self):
        """Copy the markdown template for an anchor link in the clipboard"""

        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        current_item = self.tree_model.itemFromIndex(model_index)
        current_item_type = current_item.data(UserRole.ITEM_TYPE)
        if current_item_type == ElementType.SECTION:
            section_name = current_item.data(Qt.DisplayRole)
            name = section_name
            if section_name == 'Introduction':
                link = '#Introduction'
            elif section_name == 'Navigation images':
                link = '#Navigation_images_customization'
            elif section_name == 'Optical Images':
                link = '#general_optical_image_section'
            elif section_name == 'Samples':
                link = '#samplelist'
            elif section_name == 'Conclusion':
                link = '#conclusion'
            elif section_name == 'Attachments':
                link = '#attachments'
            else:
                link = '#link'
        elif current_item_type == ElementType.SAMPLE:
            name = current_item.data(UserRole.SAMPLE_FULL_NAME)
            link = f'#{name}'
        elif current_item_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            # anchor is sample_full_name/microscope_pic_filename
            sample_full_name = current_item.parent().data(UserRole.SAMPLE_FULL_NAME)
            element_name = current_item.text()
            name = f'{sample_full_name}/{element_name}'
            link = f'#{name}'
        elif current_item_type == ElementType.OPTICAL_PIC:
            parent_item = current_item.parent()
            if parent_item.data(UserRole.ITEM_TYPE) == ElementType.SECTION:
                # it means it is a protocol wide optical image. In this case the anchor is something like:
                # #full_optical_image_path
                name = f'{current_item.text()}'
                link = f'#{current_item.data(UserRole.OPTICAL_IMAGE_KEY)}'
            else:
                # it means it is a sample related optical image. in this case the anchor is
                # #sample_full_name/image_file_name
                sample_full_name = parent_item.data(UserRole.SAMPLE_FULL_NAME)
                element_name = current_item.text()
                name = f'{sample_full_name}/{element_name}'
                link = f'#{name}'
        elif current_item_type == ElementType.NAVIGATION_PIC:
            name = current_item.text()
            link = f'#{name}'
        elif current_item_type == ElementType.ATTACHMENT_FILE:
            parent_item = current_item.parent()
            if parent_item.data(UserRole.ITEM_TYPE) == ElementType.SECTION:
                name = current_item.text()
                link = f'#{name}'
            else:
                sample_full_name = parent_item.data(UserRole.SAMPLE_FULL_NAME)
                element_name = current_item.text()
                name = f'{sample_full_name}/{element_name}'
                link = f'#{name}'
        else:
            name = 'name'
            link = '#link'

        QApplication.clipboard().setText(f'[{name}]({link})')

    def edit_custom_text(self, edit_type: str):
        """Edit the text in the QPlainText"""
        widget = QApplication.focusWidget()
        if widget is None:
            return

        # exclude the caption input because this is just a line edit and not a PlainTextEdit
        if widget.objectName() not in ['description_input', 'extrainfo_input']:
            return

        # if we got here, it means that the widget in focus is either the description_input or the extrainfo_input
        # so it is ok to continue with text edit.
        cursor = widget.textCursor()
        if edit_type.lower() == 'subscript':
            left_text = '<sub>'
            right_text = '</sub>'
        elif edit_type.lower() == 'superscript':
            left_text = '<sup>'
            right_text = '</sup>'
        elif edit_type.lower() == 'bold':
            left_text = '**'
            right_text = '**'
        elif edit_type.lower() == 'italic':
            left_text = '*'
            right_text = '*'
        elif edit_type.lower() == 'underline':
            left_text = '<u>'
            right_text = '</u>'
        elif edit_type.lower() == 'strikeout':
            left_text = '<del>'
            right_text = '</del>'
        elif edit_type.lower() == 'bullet':
            left_text = ''
            right_text = (f'{chr(10)}'
                          f'*  Item 1{chr(10)}{chr(10)}'
                          f'*  Item 2{chr(10)}{chr(10)}'
                          f'*  Item 3{chr(10)}{chr(10)}')
        elif edit_type.lower() == 'number':
            left_text = ''
            right_text = (f'{chr(10)}'
                          f'1.  Item 1{chr(10)}{chr(10)}'
                          f'2.  Item 2{chr(10)}{chr(10)}'
                          f'3.  Item 3{chr(10)}{chr(10)}')
        elif edit_type.lower() == 'link':
            left_text = ''
            right_text = '[link_name](link_url)'
        else:
            left_text = ''
            right_text = ''
        if cursor.hasSelection():
            cursor.insertText(f'{left_text}{cursor.selectedText()}{right_text}')
        else:
            widget.insertPlainText(f'{left_text}{right_text}')

    @Slot(str)
    def tree_filter(self, re: str) -> None:
        """Apply the filter to the tree model"""
        self.tree_model_proxy.setFilterRegExp(QRegExp(re, Qt.CaseInsensitive, QRegExp.FixedString))

    @Slot(str)
    def metadata_filter(self, re: str) -> None:
        """
        Slot for filtering the metadata table view.

        The filtering is done using a regular expression in a case-insensitive manner and using a fixed string syntax.
        FixedString means that no wildcards or special matching characters will be used in the matching and the string
        will be matched as it is.

        Parameters
        ----------
        re: str
            The regular expression used for the matching.

        Returns
        -------
        None
        """
        self.metadata_proxy_model.setFilterRegExp(QRegExp(re, Qt.CaseInsensitive, QRegExp.FixedString))

    @Slot(QModelIndex, int, int)
    def new_rows_added(self, parent: QModelIndex, start: int, stop: int) -> None:
        """React to the addition of a new row to the model"""

        for row in range(start, stop + 1):
            new_row = self.tree_model.index(row, 0, parent)

            # Actually we are interested only if the new item is a sample. If so we have to check if the sample is
            # already present in the sample selector, otherwise we need to add it.
            if new_row.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                if self.sample_selector.findText(new_row.data(UserRole.SAMPLE_FULL_NAME)) != -1:
                    self.sample_selector.addItem(new_row.data(UserRole.SAMPLE_FULL_NAME))

    def open_protocol_webpage(self):
        url = self.autolog.get_protocol_url()
        webbrowser.open(url, new=0, autoraise=True)

    def open_protocol_folder(self):
        """
        Open a resource browser pointing to the monitored folder or to the folder where the selected resource is.

        Returns
        -------
        None.

        """
        if isinstance(self.parent, autogui.MainWindow):
            # if the protocol editor dialog was called from the MainWindow, then we can take the protocol folder from
            # there without risking confusion about mirroring or not.
            base_path = self.parent.protocol_folder_path
        else:
            # should it not be the case, then just take the path from the autolog instance.
            base_path = self.autolog.path

        # get the item
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        current_item = self.tree_model.itemFromIndex(model_index)

        current_item_type = current_item.data(UserRole.ITEM_TYPE)
        if current_item_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            # its parent must be a sample or a subsample
            parent_sample_item = current_item.parent()
            parent_sample_path = Path(parent_sample_item.data(UserRole.SAMPLE_FULL_NAME))
            path = base_path / parent_sample_path
        elif current_item_type == ElementType.SAMPLE:
            path = base_path / Path(current_item.data(UserRole.SAMPLE_FULL_NAME))
        elif current_item_type in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:
            if current_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                path = base_path / Path(current_item.parent().data(UserRole.SAMPLE_FULL_NAME))
            else:
                path = base_path
        else:
            path = base_path

        command = f'explorer {str(path)}'
        subprocess.Popen(command.split())

    def copy_sample_path(self):
        """Copy the path of a sample to the clipboard."""

        if isinstance(self.parent, autogui.MainWindow):
            # if the protocol editor dialog was called from the MainWindow, then we can take the protocol folder from
            # there without risking confusion about mirroring or not.
            base_path = self.parent.protocol_folder_path
        else:
            # should it not be the case, then just take the path from the autolog instance.
            base_path = self.autolog.path

        # get the item
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        current_item = self.tree_model.itemFromIndex(model_index)
        current_item_type = current_item.data(UserRole.ITEM_TYPE)
        if current_item_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            # its parent must be a sample or a subsample
            parent_sample_item = current_item.parent()
            parent_sample_path = Path(parent_sample_item.data(UserRole.SAMPLE_FULL_NAME))
            path = base_path / parent_sample_path
        elif current_item_type == ElementType.SAMPLE:
            path = base_path / Path(current_item.data(UserRole.SAMPLE_FULL_NAME))
        else:
            path = base_path

        QApplication.clipboard().setText(str(path))

    def copy_element_path(self):
        """Copy the path of a protocol element to the clipboard."""
        if isinstance(self.parent, autogui.MainWindow):
            # if the protocol editor dialog was called from the MainWindow, then we can take the protocol folder from
            # there without risking confusion about mirroring or not.
            base_path = self.parent.protocol_folder_path
        else:
            # should it not be the case, then just take the path from the autolog instance.
            base_path = self.autolog.path

        # get the item
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        current_item = self.tree_model.itemFromIndex(model_index)
        current_item_type = current_item.data(UserRole.ITEM_TYPE)
        if current_item_type in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            # its parent must be a sample or a subsample
            parent_sample_item = current_item.parent()
            parent_sample_path = Path(parent_sample_item.data(UserRole.SAMPLE_FULL_NAME))
            path = base_path / parent_sample_path / Path(current_item.data(Qt.DisplayRole))
        elif current_item_type == ElementType.SAMPLE:
            path = base_path / Path(current_item.data(UserRole.SAMPLE_FULL_NAME))
        elif current_item_type == ElementType.NAVIGATION_PIC:
            path = base_path / Path(current_item.data(Qt.DisplayRole))
        else:
            path = base_path / Path(current_item.data(Qt.DisplayRole))

        QApplication.clipboard().setText(str(path))

    def get_image_url(self, image_type: str | autotools.ImageType = 'tiff') -> str:
        """Return the image URL"""

        if isinstance(image_type, str):
            try:
                image_type = autotools.ImageType(image_type)
            except ValueError:
                log.warning('The provided image_type is not recognized.')
                return ''

        # get the base path
        base_path = self.autolog.path

        # get the item from the tree viewer
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        current_item = self.tree_model.itemFromIndex(model_index)
        current_item_type = current_item.data(UserRole.ITEM_TYPE)

        # get the link depending on the image_type
        if current_item_type == ElementType.MICROSCOPE_PIC:
            # pic_id = current_item.data(UserRole.PIC_ID)
            parent_item = current_item.parent()
            parent_name = parent_item.data(UserRole.SAMPLE_FULL_NAME)
            parent_path = Path(parent_name)
            path = base_path / parent_path / Path(current_item.data(Qt.DisplayRole))
            if image_type == autotools.ImageType.TIFF:
                link = self.autolog.samples[parent_name].images[str(path)].params['tiffurl']
            elif image_type == autotools.ImageType.PNG:
                link = self.autolog.samples[parent_name].images[str(path)].params['pngurl']
            elif image_type == autotools.ImageType.THUMBNAIL:
                link = self.autolog.samples[parent_name].images[str(path)].params['thumburl']
            else:
                link = ''
        elif current_item_type == ElementType.NAVIGATION_PIC:
            nav_image_name = current_item.data(Qt.DisplayRole)
            nav_image_path = base_path / Path(nav_image_name)
            link = self.convert_path_to_uri(nav_image_path)
        elif current_item_type == ElementType.OPTICAL_PIC:
            link = current_item.data(UserRole.OPTICAL_IMAGE_URL)
        else:
            link = ''

        return link

    def open_external_image_viewer(self):
        """Open the current image in an external viewer"""
        base_path = self.autolog.path
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        current_item = self.tree_model.itemFromIndex(model_index)
        current_item_type = current_item.data(UserRole.ITEM_TYPE)
        if current_item_type == ElementType.MICROSCOPE_PIC:
            parent_item = current_item.parent()
            parent_name = parent_item.data(UserRole.SAMPLE_FULL_NAME)
            parent_path = Path(parent_name)
            path = base_path / parent_path / Path(current_item.data(Qt.DisplayRole))
        elif current_item_type == ElementType.NAVIGATION_PIC:
            nav_image_name = current_item.data(Qt.DisplayRole)
            path = base_path / Path(nav_image_name)
        elif current_item_type == ElementType.OPTICAL_PIC:
            path = current_item.data(UserRole.OPTICAL_IMAGE_PATH)
        else:
            path = None

        if path:
            command = f'explorer "{str(path)}"'
            subprocess.Popen(command)

    def copy_image_url(self, image_type: str | autotools.ImageType = 'tiff'):
        """Copy the current image URL to the clipboard"""
        link = self.get_image_url(image_type)
        QApplication.clipboard().setText(link)

    def copy_image_to_clipboard(self):
        """Copy the current image thumbnail to the clipboard"""
        QApplication.clipboard().setPixmap(self.image_preview.pixmap())

    @Slot(str)
    def change_sample_list_root(self, sample_full_name: str):
        """
        Change the table view root item.

        The sample table view is rooted to the selected sample and this is automatically updated every time the user
        select a new item from the tree viewer or when the sample selector value is changed.

        When an item not belonging to a sample is selected, the sample table is rooted to the protocol root.

        Parameters
        ----------
        sample_full_name: str
            The sample full name to be set as root item of the table view.

        Returns
        -------
        None
        """
        if self.sample_selector.count() == 0:
            items = self.tree_model.findItems("Samples", QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            if len(items) > 1:
                log.error('More than one Samples section found (size %s)', len(items))
            elif len(items) == 0:
                self.sample_list_view.setRootIndex(self.tree_model_proxy.mapFromSource(self.rootNode.index()))
            else:
                self.sample_list_view.setRootIndex(self.tree_model_proxy.mapFromSource(items[0].index()))
        elif sample_full_name == 'Protocol':
            self.sample_list_view.setRootIndex(self.tree_model_proxy.mapFromSource(self.rootNode.index()))
        else:
            sample_last_name = sample_full_name.split('/')[-1]
            items = self.tree_model.findItems(sample_last_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            good_item = None
            for item in items:
                if item.data(UserRole.SAMPLE_FULL_NAME) == sample_full_name:
                    good_item = item
                    break
            if good_item:
                self.sample_list_view.setRootIndex(self.tree_model_proxy.mapFromSource(good_item.index()))

    @Slot()
    def collapse_all_elements(self):
        """
        Collapse all elements in the tree view.

        Returns
        -------
        None
        """
        self.autolog_tree_viewer.collapseAll()

    @Slot()
    def expand_all_elements(self):
        """
        Expand all elements in the tree view.

        Returns
        -------
        None
        """
        self.autolog_tree_viewer.expandAll()

    def media_error_handler(self):
        """
        Handle error with media player
        """
        errors = {QMediaPlayer.NoError: 'No error',
                  QMediaPlayer.ResourceError: 'A media resource could not be resolved',
                  QMediaPlayer.FormatError: 'The format of a media resource is not supported',
                  QMediaPlayer.NetworkError: 'A network_path error occurred',
                  QMediaPlayer.AccessDeniedError: 'There are not the appropriate permissions to play a media resource',
                  QMediaPlayer.ServiceMissingError: 'A valid playback service wa not found, playback cannot proceed'}

        mp_statuses = {QMediaPlayer.StoppedState: 'Stopped',
                       QMediaPlayer.PlayingState: 'Playing',
                       QMediaPlayer.PausedState: 'Paused'}

        md_statuses = {QMediaPlayer.UnknownMediaStatus: 'The status of the media cannot be determined.',
                       QMediaPlayer.NoMedia: 'There is no current media. The player is in the stopped state.',
                       QMediaPlayer.LoadingMedia: 'The current media is being loaded.',
                       QMediaPlayer.LoadedMedia: 'The current media has been loaded. The player is in the stopped '
                                                 'state.',
                       QMediaPlayer.StalledMedia: 'Playback of the current media has stalled.',
                       QMediaPlayer.BufferingMedia: 'The player is buffering but has enough data for playback.',
                       QMediaPlayer.BufferedMedia: 'The player has fully buffered the current media.',
                       QMediaPlayer.EndOfMedia: 'Playback has reached the end of the current media.',
                       QMediaPlayer.InvalidMedia: 'The current media cannot be played.'
                       }

        error_no = self.media_player.error()
        mp_status = self.media_player.state()
        md_status = self.media_player.mediaStatus()
        log.error('There was an error handling the current media.')
        log.error('Error: %s' % errors.get(error_no))
        log.error('Media Player Status: %s' % mp_statuses.get(mp_status))
        log.error('Media status: %s' % md_statuses.get(md_status))
        self.preview_stack.setCurrentIndex(0)
        self.image_preview.setText('There was a problem reproducing the video. See log for more details.')
        if md_status == QMediaPlayer.InvalidMedia:
            log.error('Have you installed the CODEC package?')

    def play(self):
        """
        Start the reproduction of the current media

        Returns
        -------
        None
        """
        if self.media_player.state() == QMediaPlayer.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def media_state_changed(self, state):
        """
        React to a change in the media player state.

        In case the media player is in playing state, the control button icon will be changed in pause.
        In case the media player is in paused state, the control button icon will be changed in play.

        Parameters
        ----------
        state : QMediaPlayer.State
            There are three possible states:
            1. Stopped.
            2. Playing.
            3. Paused.
        """
        play_icon = QIcon()
        play_icon.addPixmap(QPixmap(":/resources/icons8-play-48.png"), QIcon.Normal, QIcon.Off)
        pause_icon = QIcon()
        pause_icon.addPixmap(QPixmap(":/resources/icons8-pause-48.png"), QIcon.Normal, QIcon.Off)
        if self.media_player.state() == QMediaPlayer.PlayingState:
            self.video_play_button.setIcon(pause_icon)
        else:
            self.video_play_button.setIcon(play_icon)

    def position_changed(self, position):
        """
        React to a change in the media position.

        Parameters
        ----------
        position: float
            The new position
        """
        self.video_slider.setValue(position)

    def duration_changed(self, duration):
        """
        React to a change in the media duration.

        Adapt the slider to the new duration

        Parameters
        ----------
        duration: float
            The duration

        Returns
        -------
        None
        """
        self.video_slider.setRange(0, duration)

    def set_position(self, position):
        """
        React to a change of the slider position.

        Parameters
        ----------
        position:
            The selected position on the slider.
        """
        self.media_player.setPosition(position)

    def clear_fields(self):
        """
        Clear all the fields upon windows opening.

        This method is called just before the ProtocolEditor window is shown.
        It clears the selection on the TreeView and reset the three textual
        fields.

        Returns
        -------
        None.

        """
        self.autolog_tree_viewer.selectionModel().clearSelection()
        self.caption_field.setText('')
        self.description_input.document().setPlainText('')
        self.extrainfo_input.document().setPlainText('')
        self.selected_element_label.setText('No item selected')
        if self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
            self.update_values(self.autolog_tree_viewer.selectionModel().currentIndex())

    @Slot(autoprotocol.Protocol)
    def change_autolog(self, autolog):
        """
        Change the reference to the autolog.

        When new parameters are sent to the worker, it is very likely that a new autolog reference is generated.
        If the protocol editor was already created, then the main window needs to inform it that the autolog reference
        is changed.

        After setting the autolog reference, we need to reset the content of the model.

        Parameters
        ----------
        autolog : autoprotocol.Protocol
            The reference of the current autolog.

        Returns
        -------
        None.

        """
        log.debug('Changing the autolog reference')
        self.autolog = autolog
        self.reset_content()

    def refresh_view(self):
        """
        Regenerate the content of the TreeModel.

        This function is used to assure that the model content is update and
        what is shown in the editor window corresponds to the protocol model.

        Returns
        -------
        None.

        """
        self.tree_model_proxy.sort(0, Qt.AscendingOrder)

    def generate_model(self):
        """
        Generate the data model.

        We use a QStandardItemModel.

        This method generates the whole model standard from the autolog instance

        Returns
        -------
        None.

        """
        introduction_section = SectionItem('Introduction')
        introduction_section.get_data_from_yaml(self.autolog.yamlDict)
        self.rootNode.appendRow(introduction_section)

        # a navigation camera section exists only if the protocol is of a
        # Quattro microscope.
        if isinstance(self.autolog, (autoprotocol.QuattroELOGProtocol, autoprotocol.MultiMicroscopeELOGProtocol)):
            navcam_section = SectionItem('Navigation images')
            navcam_section.get_data_from_yaml(self.autolog.yamlDict)

            for navpic in self.autolog.navcamimages:
                navpic_item = NavPicItem(Path(navpic).name, str(Path(navpic)))
                navpic_item.get_data_from_yaml(self.autolog.yamlDict)
                navcam_section.appendRow(navpic_item)

            self.rootNode.appendRow(navcam_section)

        optical_images_section = SectionItem('Optical images')
        optical_images_section.get_data_from_yaml(self.autolog.yamlDict)
        for optical_image in self.autolog.optical_images:
            optical_image_item = OpticalImageItem(optical_image)
            optical_image_item.get_data_from_yaml(self.autolog.yamlDict)
            optical_images_section.appendRow(optical_image_item)
        self.rootNode.appendRow(optical_images_section)

        sample_section = SectionItem('Samples')
        sample_section.get_data_from_yaml(self.autolog.yamlDict)
        self.sample_selector.addItem('Protocol')

        # in the sample dictionary, the sample keys are the
        # sample full_name
        for full_name, sample in self.autolog.samples.items():
            if sample.parent is None:
                log.debug('Adding top level sample %s' % full_name)
                # we got a top level sample. add this and process
                # all its child
                entry = SampleItem(full_name)
                entry.get_data_from_yaml(self.autolog.yamlDict)
                for key, image in sample.images.items():
                    pic = MicroPicItem(Path(key).name, image.key, image.params['thumbfilename'])
                    pic.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(pic)
                for key, video in sample.videos.items():
                    video_item = VideoItem(key=key, path=video.get('path'),
                                           url=video.get('url'), txt=video.get('filename'))
                    video_item.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(video_item)
                for key, attachment in sample.attachments.items():
                    attach_item = AttachmentItem(key)
                    attach_item.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(attach_item)
                for key in sample.optical_images.keys():
                    optical_image_item = OpticalImageItem(key)
                    optical_image_item.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(optical_image_item)

                sample_section.appendRow(entry)
                self.sample_selector.addItem(full_name)
                if len(sample.subsamples) != 0:
                    self.add_subsample_recursively(sample.subsamples, entry)

        self.rootNode.appendRow(sample_section)

        conclusion_section = SectionItem('Conclusion')
        conclusion_section.get_data_from_yaml(self.autolog.yamlDict)
        self.rootNode.appendRow(conclusion_section)

        attachment_section = SectionItem('Attachments')
        last_element = attachment_section
        for key in self.autolog.attachments.keys():
            attachment = AttachmentItem(key)
            last_element = attachment
            attachment.get_data_from_yaml(self.autolog.yamlDict)
            attachment_section.appendRow(attachment)

        attachment_section.get_data_from_yaml(self.autolog.yamlDict)
        self.rootNode.appendRow(attachment_section)

        # since we have regenerated the model the persistent model indexes pointing to the last inserted and last
        # selected items will become invalid, so for the last inserted we just use either the last attachment or the
        # attachment section itself. For the last selected, it makes no sense to have something assign, so we put it to
        # None and wait for the user next selection.
        last_element_index = self.tree_model.indexFromItem(last_element)
        last_element_proxy = self.tree_model_proxy.mapFromSource(last_element_index)
        self.tree_model_last_inserted_item = QPersistentModelIndex(last_element_proxy)
        self.tree_model_last_selected_item = None

    def add_subsample_recursively(self, sample_list, parent_entry):
        """
        Add a subsample list to a parent sample recursively.

        When building the protocol model, all subsample of a parent must be
        registered and this procedure must be repeated recursively.

        Parameters
        ----------
        sample_list : list
            The list of subsamples belonging to the parent sample.
        parent_entry : SectionItem | SampleItem
            The section item where the subsamples must be appended.

        Returns
        -------
        None.

        """
        # sample_list stores sample_full_names
        for sample_full_name in sample_list:
            if sample_full_name in self.autolog.samples.keys():
                sample = self.autolog.samples[sample_full_name]
                log.debug('Adding subsample %s to %s' % (sample_full_name, sample.parent))
                entry = SampleItem(sample_full_name)
                entry.get_data_from_yaml(self.autolog.yamlDict)
                for key, image in sample.images.items():
                    pic = MicroPicItem(Path(key).name, image.key, image.params['thumbfilename'])
                    pic.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(pic)
                for key, video in sample.videos.items():
                    video_item = VideoItem(key=key, path=video.get('path'),
                                           url=video.get('url'), txt=video.get('filename'))
                    video_item.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(video_item)
                for key, attach in sample.attachments.items():
                    attach_item = AttachmentItem(key)
                    attach_item.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(attach_item)
                for key in sample.optical_images.keys():
                    optical_image_item = OpticalImageItem(key)
                    optical_image_item.get_data_from_yaml(self.autolog.yamlDict)
                    entry.appendRow(optical_image_item)
                if len(sample.subsamples) != 0:
                    self.add_subsample_recursively(sample.subsamples, entry)
                parent_entry.appendRow(entry)
                self.sample_selector.addItem(sample_full_name)

    @Slot(ElementType, str, str)
    def add_element(self, element_type, element_name, parent_name):  # noqa: C901
        """
        Add an element to the model.

        Slot function connected to the addition of a new element to the model

        Parameters
        ----------
        element_type : ElementType
            This enumerator contains all possible element types
        element_name : string
            For NavPic and MicroPic the element name is the full path of the
            image.
            For Sample, it is just the sample name
        parent_name : string
            For MicroPic, the sample name.
            For Sample, the parent name or 'Samples' for top level samples.

        Raises
        ------
        ValueError
            Raised if more than one parent section is found in the model

        Returns
        -------
        None.

        """
        new_item = None
        if element_type == ElementType.NAVIGATION_PIC:
            # element_name must be the full path
            path = Path(element_name)
            name = path.name

            # the parent name must be Navigation images
            items = self.tree_model.findItems('Navigation images',
                                              QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            if len(items) == 1:
                new_item = NavPicItem(name, str(path))
                new_item.get_data_from_yaml(self.autolog.yamlDict)
                items[0].appendRow(new_item)
            else:
                raise ValueError('More than one navigation image section found')

        elif element_type == ElementType.MICROSCOPE_PIC:
            # element_name must be the full path
            if not isinstance(element_name, Path):
                path = Path(element_name)
            else:
                path = element_name

            # take the picture name from the full path
            name = path.name

            # the parent name is a sample_full_name
            sample_full_name = parent_name
            # take the sample_last_name
            sample_last_name = parent_name.split('/')[-1]

            # to build the MicroPicItem we need:
            #   the image reference,
            #   the image_id
            #   the thumbfilename
            image = self.autolog.samples[sample_full_name].images[str(path)]
            image_id = image.key
            thumb = image.params['thumbfilename']

            new_item = MicroPicItem(name, image_id, thumb)
            new_item.get_data_from_yaml(self.autolog.yamlDict)

            # we need to find the sample to append this MicroPicItem
            # the search works on sample_last_name, so there could be many
            items = self.tree_model.findItems(sample_last_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)

            # there might be more than one with the same last name
            # but only one is the good one with the exact full name
            good_item = None
            for item in items:
                if item.data(UserRole.SAMPLE_FULL_NAME) == sample_full_name:
                    good_item = item
                    break
            good_item.appendRow(new_item)

        elif element_type == ElementType.VIDEO_FILE:
            # element_name is the path / key
            # parent_name is the sample_full_name
            parent_last_name = parent_name.split('/')[-1]
            key = str(element_name)
            txt = self.autolog.samples[parent_name].videos[key].get('filename')
            url = self.autolog.samples[parent_name].videos[key].get('url')
            path = self.autolog.samples[parent_name].videos[key].get('path')
            new_item = VideoItem(txt=txt, key=key, url=url, path=path)
            new_item.get_data_from_yaml(self.autolog.yamlDict)

            # we need to find the sample to append this VideoItem
            # the search works on parent_last_name, so there could be many
            items = self.tree_model.findItems(parent_last_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)

            # there might be more than one with the same last name
            # but only one is the good one with the exact full name
            good_item = None
            for item in items:
                if item.data(UserRole.SAMPLE_FULL_NAME) == parent_name:
                    good_item = item
                    break
            good_item.appendRow(new_item)

        elif element_type == ElementType.SAMPLE:
            if parent_name == 'Samples':
                # we are adding a top level sample
                new_item = SampleItem(element_name)
                new_item.get_data_from_yaml(self.autolog.yamlDict)
                items = self.tree_model.findItems(parent_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
                # this must be just one, because we have a top level sample
                if len(items) != 1:
                    log.critical('More than 1 sample main section.')
                    raise ValueError
                else:
                    items[0].appendRow(new_item)
                    self.sample_selector.addItem(new_item.data(UserRole.SAMPLE_FULL_NAME))
            else:
                parent_full_name = parent_name
                parent_last_name = parent_name.split('/')[-1]
                sample_full_name = element_name

                new_item = SampleItem(sample_full_name)
                new_item.get_data_from_yaml(self.autolog.yamlDict)
                items = self.tree_model.findItems(parent_last_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive,
                                                  0)

                # this time items can have more than 1 item because last names are not
                # unique, but full names are!
                good_item = None
                for item in items:
                    if item.data(UserRole.SAMPLE_FULL_NAME) == parent_full_name:
                        good_item = item
                        break
                good_item.appendRow(new_item)
                self.sample_selector.addItem(new_item.data(UserRole.SAMPLE_FULL_NAME))

        elif element_type == ElementType.ATTACHMENT_FILE:
            # the element name is the full path
            # the parent name is "Attachments" for protocol wide attachments
            # or the sample full name for sample attachments
            if parent_name == 'Attachments':
                items = self.tree_model.findItems(parent_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
                if len(items) == 1:
                    new_item = AttachmentItem(element_name)
                    new_item.get_data_from_yaml(self.autolog.yamlDict)
                    items[0].appendRow(new_item)
                else:
                    raise ValueError('More than one attachment section found')
            else:
                sample_full_name = parent_name
                sample_last_name = parent_name.split('/')[-1]

                # build the attachment
                new_item = AttachmentItem(element_name)
                new_item.get_data_from_yaml(self.autolog.yamlDict)

                # search for the sample
                items = self.tree_model.findItems(sample_last_name,
                                                  QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
                good_item = None
                for item in items:
                    if item.data(UserRole.SAMPLE_FULL_NAME) == sample_full_name:
                        good_item = item
                        break
                good_item.appendRow(new_item)

        elif element_type == ElementType.OPTICAL_PIC:
            # the element name is the full path,
            # the parent name if 'Optical images' for protocol wide images
            # or the sample full name for sample wide images
            if parent_name == 'Optical images':
                items = self.tree_model.findItems(parent_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
                if len(items) == 1:
                    new_item = OpticalImageItem(element_name)
                    new_item.get_data_from_yaml(self.autolog.yamlDict)
                    items[0].appendRow(new_item)
                else:
                    raise ValueError('More than one optical image section found')
            else:
                sample_full_name = parent_name
                sample_last_name = parent_name.split('/')[-1]

                # build the attachment
                new_item = OpticalImageItem(element_name)
                new_item.get_data_from_yaml(self.autolog.yamlDict)

                # search for the sample
                items = self.tree_model.findItems(sample_last_name,
                                                  QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
                good_item = None
                for item in items:
                    if item.data(UserRole.SAMPLE_FULL_NAME) == sample_full_name:
                        good_item = item
                        break
                good_item.appendRow(new_item)

        elif element_type == ElementType.YAML_FILE:
            log.debug('new yaml file available')
            # TODO: force refresh all items from file.

        if new_item:
            model_index = self.tree_model.indexFromItem(new_item)
            proxy_index = self.tree_model_proxy.mapFromSource(model_index)
            self.refresh_view()
            self.autolog_tree_viewer.scrollTo(proxy_index)
            self.tree_model_last_inserted_item = QPersistentModelIndex(proxy_index)
            if self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
                self.update_metadata_table(self.autolog_tree_viewer.selectionModel().currentIndex())

    @Slot(ElementType, str, str)
    def remove_element(self, element_type, element_name, parent_name):  # noqa: C901
        """
        Remove an element from the model.

        Slot function connected to the removal of an existing element to the model

        Parameters
        ----------
        element_type : ElementType
            This enumerator contains all possible element types
        element_name : string
            For NavPic and MicroPic the element name is the full path of the
            image.
            For Sample, it is just the sample name
        parent_name : string
            For MicroPic, the sample name.
            Useless for NavPic and Sample.

        Returns
        -------
        None.

        """
        if element_type in [ElementType.NAVIGATION_PIC, ElementType.MICROSCOPE_PIC]:
            name = Path(element_name).name
            items = self.tree_model.findItems(
                name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            if len(items) == 1:
                item = items[0]
                parent_index = item.parent().index()
                item.model().removeRow(item.row(), parent_index)
            elif len(items) > 1:
                # log.error('Expected only one element with name %s.' % name)
                # log.error('Found instead %s' % len(items))
                # log.warning('Removing all of them and verify the protocol.')
                for item in items:
                    if item.parent().text() == parent_name:
                        parent_index = item.parent().index()
                        item.model().removeRow(item.row(), parent_index)

        elif element_type == ElementType.VIDEO_FILE:
            # element_name is the full path/key
            key = element_name
            name = Path(element_name).name
            sample_full_name = parent_name
            items = self.tree_model.findItems(name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            good_item = None
            for item in items:
                if item.data(UserRole.VIDEO_KEY) == key:
                    good_item = item
                    break
            parent_index = good_item.parent().index()
            good_item.model().removeRow(good_item.row(), parent_index)

        elif element_type == ElementType.SAMPLE:

            sample_full_name = element_name
            sample_last_name = sample_full_name.split('/')[-1]
            items = self.tree_model.findItems(sample_last_name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            good_item = None
            for item in items:
                if item.data(UserRole.SAMPLE_FULL_NAME) == sample_full_name:
                    good_item = item
                    break
            parent_index = good_item.parent().index()
            good_item.model().removeRow(good_item.row(), parent_index)
            index = self.sample_selector.findText(sample_full_name, QtCore.Qt.MatchExactly)
            if index != -1:
                self.sample_selector.removeItem(index)

        elif element_type == ElementType.ATTACHMENT_FILE:
            key = element_name
            name = Path(element_name).name

            items = self.tree_model.findItems(name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            good_item = None
            for item in items:
                if item.data(UserRole.ATTACHMENT_PATH) == key:
                    good_item = item
                    break

            parent_index = good_item.parent().index()
            good_item.model().removeRow(good_item.row(), parent_index)

        elif element_type == ElementType.OPTICAL_PIC:
            key = element_name
            name = Path(element_name).name

            items = self.tree_model.findItems(name, QtCore.Qt.MatchExactly or QtCore.Qt.MatchRecursive, 0)
            good_item = None
            for item in items:
                if item.data(UserRole.OPTICAL_IMAGE_KEY) == key:
                    good_item = item
                    break

            parent_index = good_item.parent().index()
            good_item.model().removeRow(good_item.row(), parent_index)

        self.refresh_view()

    @Slot(QItemSelection, QItemSelection)
    def get_and_update_values(self, new_item: QItemSelection, old_item: QItemSelection) -> None:
        """
        Get the new item and save the old one.

        This slot is called everytime the selection of the treeview is changed.
        The old_item was the one previously selected, for this item we need to
        save the information inserted by the user in the text edit fields.
        This is accomplished by the update_values method

        The newItem is the currently selected line. For this we need to retrieve
        the information and show them in the text edit fields.
        This is accomplished by the get_values method.


        Parameters
        ----------
        new_item : QItemSelection
            The list of items currently selected.
        old_item : QItemSelection
            The list of items that were previously selected.

        Returns
        -------
        None.

        """
        if old_item:
            old_index = old_item.indexes()[0]
            self.update_values(old_index)
        if new_item:
            new_index = new_item.indexes()[0]
            self.update_metadata_table(new_index)
            self.update_sample_selector(new_index)
            self.get_values(new_index)

    def populate_metadata_table(self, dictionary: dict) -> None:
        """
        Populate the metadata model.

        The metadata pair (property / value)
        """
        self.metadata_model.set_metadata(dictionary)

    def update_metadata_table(self, index: QModelIndex) -> None:
        """
        Slot function to request an update of the metadata table.

        This function is taking the QModelIndex from the tree model (the selection model is shared between the tree
        and the table view) and preparing a dictionary of metadata depending on the item type.

        Parameters
        ----------
        index: QModelIndex
            The model index for which we want to update the metadata table.

        Returns
        -------
        None

        """

        dictionary = {}

        try:

            new_item = self.tree_model.itemFromIndex(self.tree_model_proxy.mapToSource(index))
            if new_item.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                if new_item.data(UserRole.SAMPLE_FULL_NAME) in self.autolog.samples:
                    # it is possible that the sample was removed in the other thread.
                    # if not there, then ignore it.
                    sample = self.autolog.samples[new_item.data(UserRole.SAMPLE_FULL_NAME)]

                    dictionary['Parent'] = sample.parent
                    dictionary['Full Name'] = sample.full_name
                    dictionary['Last Name'] = sample.last_name
                    dictionary['Number of subsamples'] = len(sample.subsamples)
                    dictionary['Number of images'] = len(sample.images)
                    dictionary['Number of videos'] = len(sample.videos)

            elif new_item.data(UserRole.ITEM_TYPE) == ElementType.ATTACHMENT_FILE:
                key = str(new_item.data(UserRole.ATTACHMENT_PATH))
                if new_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                    sample_full_name = new_item.parent().data(UserRole.SAMPLE_FULL_NAME)
                    dictionary = self.autolog.samples[sample_full_name].attachments[key].params
                elif new_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SECTION:
                    dictionary = self.autolog.attachments[key].params
                else:
                    dictionary = {}
            elif new_item.data(UserRole.ITEM_TYPE) == ElementType.MICROSCOPE_PIC:
                sample_full_name = new_item.parent().data(UserRole.SAMPLE_FULL_NAME)
                picture_name = new_item.text()
                path = self.autolog.path
                key = str(path / Path(sample_full_name) / Path(picture_name))
                dictionary = self.autolog.samples[sample_full_name].images[key].params
            elif new_item.data(UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE:
                key = new_item.data(UserRole.VIDEO_KEY)
                sample_full_name = new_item.parent().data(UserRole.SAMPLE_FULL_NAME)
                dictionary = self.autolog.samples[sample_full_name].videos[key].params

            elif new_item.data(UserRole.ITEM_TYPE) == ElementType.OPTICAL_PIC:
                key = new_item.data(UserRole.OPTICAL_IMAGE_KEY)
                if new_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                    sample_full_name = new_item.parent().data(UserRole.SAMPLE_FULL_NAME)
                    dictionary = self.autolog.samples[sample_full_name].optical_images[key].params
                elif new_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SECTION:
                    dictionary = self.autolog.optical_images[key].params
                else:
                    dictionary = {}

            dictionary = autotools.convert_to_string(dictionary)

        except KeyError:

            dictionary = {}

        self.populate_metadata_table(dictionary)

    @Slot()
    def show_main_window(self):
        """
        Slot function to hide the editor window.

        By hiding the protocol window, its parent (the main window) will become visible.

        Returns
        -------
        None
        """
        self.hide()

    def update_sample_selector(self, index: QModelIndex) -> None:
        """
        Update the selection of the sample selector combo.

        Based on the ItemType of the index, the selected item in the sample selector will be updated in order to match
        either the currently selected sample or the parent of the currently selected microscope picture or video.
        In general the sample selector contains all subsamples of the current protocol plus the 'Protocol' entry
        corresponding to the root level.


        Parameters
        ----------
        index: QModelIndex
            The index corresponding to the currently selected item in the tree view.

        Returns
        -------
        None
        """
        new_item = self.tree_model.itemFromIndex(self.tree_model_proxy.mapToSource(index))
        if new_item.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
            self.sample_selector.setCurrentText(new_item.data(UserRole.SAMPLE_FULL_NAME))
        elif new_item.data(UserRole.ITEM_TYPE) in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            self.sample_selector.setCurrentText(new_item.parent().data(UserRole.SAMPLE_FULL_NAME))
        elif (new_item.data(UserRole.ITEM_TYPE) in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]
              and new_item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE):
            self.sample_selector.setCurrentText(new_item.parent().data(UserRole.SAMPLE_FULL_NAME))
        else:
            self.sample_selector.setCurrentText('Protocol')

    @Slot()
    def reset_content(self):
        """
        Trigger a refresh of the view.

        This slot is triggered by the reset of the content of the protocol instance.
        Particularly used when the watchdog is stopped and restarted without changing any parameter in the main window.
        """
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        self.sample_selector.clear()
        self.generate_model()
        self.refresh_view()

    def update_values(self, index):
        """
        Update the values of the item corresponding to index.

        The information contained in the edit fields are transferred to the
        data container of the Item and also to the autolog yaml_dict.
        In this way, the next time the autologbook triggers a regeneration of
        the HTML, the new information saved in the yaml_dict are applied.

        From the GUI to the YAML and to the Data container.

        Parameters
        ----------
        index : QModelIndex
            The index of the item to be updated.

        Returns
        -------
        None.

        """
        if index.data(UserRole.ITEM_TYPE) == ElementType.MICROSCOPE_PIC:
            key = index.data(UserRole.PIC_ID)
        elif index.data(UserRole.ITEM_TYPE) == ElementType.OPTICAL_PIC:
            key = index.data(UserRole.OPTICAL_IMAGE_KEY)
        elif index.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
            key = index.data(UserRole.SAMPLE_FULL_NAME)
        elif index.data(UserRole.ITEM_TYPE) == ElementType.ATTACHMENT_FILE:
            key = index.data(UserRole.ATTACHMENT_PATH)
        elif index.data(UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE:
            key = index.data(UserRole.VIDEO_KEY)
        else:
            key = index.data(Qt.DisplayRole)

        if index.data(UserRole.ITEM_TYPE) in (
                ElementType.NAVIGATION_PIC, ElementType.MICROSCOPE_PIC, ElementType.OPTICAL_PIC):
            dict_entry = self.autolog.yamlDict.get(
                key, {'Caption': '', 'Description': '', 'Extra': ''})
            if self.caption_field.text():
                dict_entry['Caption'] = self.caption_field.text()
            index.model().setData(index, self.caption_field.text(), UserRole.CAPTION)
        elif index.data(UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE:
            dict_entry = self.autolog.yamlDict.get(key, {'Caption': '', 'Description': '', 'Extra': ''})
            dict_entry['Caption'] = self.caption_field.text()
            index.model().setData(index, self.caption_field.text(), UserRole.CAPTION)
        else:
            dict_entry = self.autolog.yamlDict.get(key, {'Description': '', 'Extra': ''})

        dict_entry['Description'] = autotools.literal_str(self.description_input.document().toPlainText())
        index.model().setData(index, self.description_input.document().toPlainText(), UserRole.DESCRIPTION)

        dict_entry['Extra'] = autotools.literal_str(self.extrainfo_input.document().toPlainText())
        index.model().setData(index, self.extrainfo_input.document().toPlainText(), UserRole.EXTRA)

        self.autolog.yamlDict[key] = dict_entry

    @Slot(QModelIndex)
    def get_values(self, index: QModelIndex) -> None:
        """
        Retrieve the data from the item and display them.

        From the data containers to the GUI.

        Parameters
        ----------
        index : QModelIndex
            The index corresponding to the item being displayed.

        Returns
        -------
        None.

        """
        self.tree_model_last_selected_item = QPersistentModelIndex(index)
        self.selected_element_label.setText(f'Element being edited / displayed: {index.data(QtCore.Qt.DisplayRole)}')
        if index.data(UserRole.ITEM_TYPE) in [ElementType.NAVIGATION_PIC, ElementType.MICROSCOPE_PIC,
                                              ElementType.OPTICAL_PIC]:
            self.preview_stack.setCurrentIndex(0)
            self.image_preview.setPixmap(QPixmap(index.data(UserRole.IMAGE)).scaledToWidth(390, 1))
            self.caption_field.setEnabled(True)
            self.caption_field.setText(index.data(UserRole.CAPTION))
            self.description_input.setPlainText(index.data(UserRole.DESCRIPTION))
            self.extrainfo_input.setPlainText(index.data(UserRole.EXTRA))
        elif index.data(UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE:
            self.preview_stack.setCurrentIndex(1)
            self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(str(index.data(UserRole.VIDEO_PATH)))))
            self.media_player.play()
            time.sleep(0.1)
            self.media_player.pause()
            self.caption_field.setEnabled(True)
            self.caption_field.setText(index.data(UserRole.CAPTION))
            self.description_input.setPlainText(index.data(UserRole.DESCRIPTION))
            self.extrainfo_input.setPlainText(index.data(UserRole.EXTRA))
        elif index.data(UserRole.ITEM_TYPE) in [ElementType.TEXT, ElementType.SECTION, ElementType.SAMPLE,
                                                ElementType.ATTACHMENT_FILE]:
            self.preview_stack.setCurrentIndex(0)
            self.image_preview.setText('Image preview not available for this element')
            self.caption_field.clear()
            self.caption_field.setEnabled(False)
            self.description_input.setPlainText(index.data(UserRole.DESCRIPTION))
            self.extrainfo_input.setPlainText(index.data(UserRole.EXTRA))

    @Slot()
    def copy_custom_values(self, what='all'):
        """
        Copy the content of the custom fields to the custom_data_dict dictionary.

        This button is mimicking the copy to clipboard action, but it takes all three customizable texts and made it
        available for the paste_custom_values function.

        This slot is called when the copy button is pressed.

        Returns
        -------

        """
        if what.lower() == 'all':
            self.custom_data_dict = {
                'Caption': self.caption_field.text(),
                'Description': self.description_input.document().toPlainText(),
                'Extra': self.extrainfo_input.document().toPlainText()
            }
        elif what.lower() == 'caption':
            self.custom_data_dict = {'Caption': self.caption_field.text()}
        elif what.lower() == 'description':
            self.custom_data_dict = {'Description': self.description_input.document().toPlainText()}
        elif what.lower() == 'extra':
            self.custom_data_dict = {'Extra': self.extrainfo_input.document().toPlainText()}
        self.paste_custom_value_button.setEnabled(True)
        self.custom_data_dict_available = True

    @Slot()
    def paste_custom_values(self, what='all'):
        """
        Paste the content of the custom_data_dict dictionary to the custom fields.

        This slot is called when the paste button is pressed.

        Returns
        -------

        """
        if what.lower() in ['all', 'caption']:
            if 'Caption' in self.custom_data_dict.keys():
                self.caption_field.setText(self.custom_data_dict['Caption'])
        if what.lower() in ['all', 'description']:
            if 'Description' in self.custom_data_dict.keys():
                self.description_input.document().setPlainText(self.custom_data_dict['Description'])
        if what.lower() in ['all', 'extra']:
            if 'Extra' in self.custom_data_dict.keys():
                self.extrainfo_input.document().setPlainText(self.custom_data_dict['Extra'])

    @Slot()
    def update_protocol(self):
        """
        Update the protocol.

        Slot connected to the Update protocol. When clicked the current item values
        are transferred to the yaml_dict and the whole yaml_dict is dumped to the
        yaml protocol file.

        This filesystem change triggers the watchdog to force the generation of
        the whole HTML and its publication to the ELOG.

        Returns
        -------
        None.

        """
        if self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
            self.update_values(self.autolog_tree_viewer.selectionModel().currentIndex())
            self.tree_model_last_selected_item = QPersistentModelIndex(
                self.autolog_tree_viewer.selectionModel().currentIndex()
            )
        autotools.dump_yaml_file(self.autolog.yamlDict, self.autolog.yamlFilename)

    @Slot()
    def auto_save(self):
        if self.isVisible():
            log.info('Automatic save of the protocol customizations')
            self.update_protocol()

    def scroll_to_last_selected_item(self):
        """
        Scroll the tree viewer down to the last selected item.

        This item is used when the protocol editor window is opened a second time.
        So that the user will be able to continue editing from the same item where he was when he left.

        Returns
        -------
        None.
        """
        self.autolog_tree_viewer.selectionModel().clearSelection()
        if self.tree_model_last_selected_item and self.tree_model_last_selected_item.isValid():
            index = QModelIndex(self.tree_model_last_selected_item)
            self.autolog_tree_viewer.selectionModel().select(index, QItemSelectionModel.SelectCurrent)
            self.autolog_tree_viewer.scrollTo(index, QAbstractItemView.EnsureVisible)
            self.enable_filesystem_command_buttons(index)
        else:
            self.clear_fields()
            self.enable_filesystem_command_buttons(None)

    @Slot()
    def scroll_to_last_inserted_item(self):
        """
        Scroll the tree viewer down to the last inserted item.

        When this slot is called, the tree viewer will automatically scroll and select the last inserted item.

        Returns
        -------
        None
        """
        if self.tree_model_last_inserted_item and self.tree_model_last_inserted_item.isValid():
            self.autolog_tree_viewer.selectionModel().clearSelection()
            index = QModelIndex(self.tree_model_last_inserted_item)
            self.autolog_tree_viewer.selectionModel().select(index, QItemSelectionModel.SelectCurrent)
            self.autolog_tree_viewer.scrollTo(index, QAbstractItemView.EnsureVisible)
            self.enable_filesystem_command_buttons(index)

    @Slot()
    def rename_protocol_element(self):
        """
        Rename the currently selected protocol element.

        This slot is calling the RenameDialog in order to obtain from the user a new name for the currently selected
        item.
        The slot is available only on editable items (so not on SectionItem).

        If the new name is different from the old one, then a FileSystemCommand is prepared and sent via the signal /
        slot mechanism to the commander.

        Custom fields (caption, description, extra) stored in the yaml dictionary will be moved to the renamed item in
        a so-called recycling process.
        In case of renaming a sample or subsamples, also all the customization of all their members will be recycled.

        Returns
        -------
        None
        """
        # if the index is invalid, exit now!
        if not self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
            return

        # get the item
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        item = self.tree_model.itemFromIndex(model_index)

        # if the item is not editable, then exit now!
        if item.data(UserRole.ITEM_TYPE) in [ElementType.SECTION, ElementType.TEXT]:
            return

        # be sure that the custom values of the currently selected item are transferred
        self.update_values(self.autolog_tree_viewer.selectionModel().currentIndex())

        text = f'Enter a new name for element {item.text()} and then click OK'
        original_name = item.text()
        rename_dialog = RenameDialog(self, text, original_name)
        if rename_dialog.exec_():
            new_name = rename_dialog.new_name_field.text()
            if new_name == original_name:
                return
            else:
                if item.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                    original_path = Path(item.data(UserRole.SAMPLE_FULL_NAME))
                    new_path = original_path.parent / Path(new_name)
                    old_key = str(original_path).replace('\\', '/')
                    new_key = str(new_path).replace('\\', '/')
                    self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict, item.data(UserRole.ITEM_TYPE),
                                                          old_key, new_key)
                    command = FileSystemCommand(FSCommandType.RENAME_DIR, original_path, new_path)

                elif item.data(UserRole.ITEM_TYPE) in [ElementType.VIDEO_FILE, ElementType.MICROSCOPE_PIC]:
                    parent_path = item.parent().data(UserRole.SAMPLE_FULL_NAME)
                    name = item.text()

                    # we recycle the customization elements.
                    old_key = item.data(UserRole.VIDEO_KEY) if item.data(
                        UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE else item.data(UserRole.PIC_ID)
                    new_key = str(Path(old_key).parent / Path(new_name))

                    self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict,
                                                          item.data(UserRole.ITEM_TYPE), old_key, new_key)
                    command = FileSystemCommand(FSCommandType.RENAME_FILE,
                                                Path(parent_path) / Path(name),
                                                Path(parent_path) / Path(new_name))

                elif item.data(UserRole.ITEM_TYPE) == ElementType.NAVIGATION_PIC:
                    input_path = Path(item.text())
                    output_path = Path(new_name)

                    key = str(input_path)
                    new_key = str(output_path)
                    self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict,
                                                          item.data(UserRole.ITEM_TYPE), key, new_key)
                    command = FileSystemCommand(FSCommandType.RENAME_FILE, input_path, output_path)

                elif item.data(UserRole.ITEM_TYPE) in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:
                    if item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                        # it is a sample wide element
                        input_path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path(item.text())
                        output_path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path(new_name)
                    else:
                        # it is a protocol wide element
                        input_path = Path(item.text())
                        output_path = Path(new_name)
                    if item.data(UserRole.ITEM_TYPE) == ElementType.ATTACHMENT_FILE:
                        old_key = str(item.data(UserRole.ATTACHMENT_PATH))
                        new_key = str(Path(old_key).parent / Path(new_name))
                    else:  # ElementType == OPTICAL_PIC
                        old_key = item.data(UserRole.OPTICAL_IMAGE_KEY)
                        new_key = str(item.data(UserRole.OPTICAL_IMAGE_PATH).parent / Path(new_name))
                    self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict,
                                                          item.data(UserRole.ITEM_TYPE), old_key, new_key)
                    command = FileSystemCommand(FSCommandType.RENAME_FILE, input_path, output_path)

                else:
                    command = None

                if command:
                    self.execute_filesystem_command.emit(command)

                # dump to yaml file
                autotools.dump_yaml_file(self.autolog.yamlDict, self.autolog.yamlFilename)

    def recycle_protocol_element(self):
        """Recycle a protocol element putting it in the bin and out from the protocol"""
        # current index is invalid. exit now
        if not self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
            return

        # get the item from the index
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        item = self.tree_model.itemFromIndex(model_index)

        # be sure that the custom values of the currently selected item are transferred
        self.update_values(self.autolog_tree_viewer.selectionModel().currentIndex())

        # only microscope_picture, videos, optical images and attachments can be recycled
        if item.data(UserRole.ITEM_TYPE) in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:

            sample = item.parent()
            sample_path = Path(sample.data(UserRole.SAMPLE_FULL_NAME))
            old_path = sample_path / Path(item.data(Qt.DisplayRole))
            new_path = sample_path / Path('excluded/') / Path(item.data(Qt.DisplayRole))

            if item.data(UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE:
                old_key = item.data(UserRole.VIDEO_KEY)
                new_key = str(Path(old_key).parent / Path('excluded/') / Path(item.data(Qt.DisplayRole)))
            else:  # ElementType.MICROSCOPE_PIC
                old_key = item.data(UserRole.PIC_ID)
                new_key = str(Path(old_key).parent / Path('excluded/') / Path(item.data(Qt.DisplayRole)))

            command = FileSystemCommand(FSCommandType.MOVE_FILE, old_path, new_path)
        elif item.data(UserRole.ITEM_TYPE) in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:

            if item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                old_path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path(item.text())
                new_path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path('excluded/') / Path(item.text())
            else:
                old_path = Path(item.text())
                new_path = Path('excluded/') / Path(item.text())

            if item.data(UserRole.ITEM_TYPE) == ElementType.ATTACHMENT_FILE:
                old_key = str(item.data(UserRole.ATTACHMENT_PATH))
                new_key = str(Path(old_key).parent / Path('excluded/') / Path(item.text()))
            else:  # ElementType.OPTICAL_PIC
                old_key = item.data(UserRole.OPTICAL_IMAGE_KEY)
                new_key = str(item.data(UserRole.OPTICAL_IMAGE_PATH).parent / Path('excluded/') / Path(item.text()))

            command = FileSystemCommand(FSCommandType.MOVE_FILE, old_path, new_path)

        else:
            command = None
            log.warning('Only microscope pictures, videos, optical images and attachments can be recycled.')
            QMessageBox.warning(self, 'Element recycle',
                                'Only microscope pictures, videos, optical images and attachments can be recycled.',
                                buttons=QMessageBox.Ok)

        if command:
            reply = QMessageBox.question(self, 'Element recycle',
                                         f'Are you sure you want to recycle {str(command.input_path.name)}?{chr(10)}'
                                         f'A recycled item will be removed from the protocol, but not deleted from the '
                                         f'disk.{chr(10)}'
                                         f'You can still retrieve it from the basket bin in a later stage.',
                                         buttons=(QMessageBox.Yes | QMessageBox.No))
            if reply == QMessageBox.Yes:
                self.execute_filesystem_command.emit(command)

                if old_key:
                    self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict, item.data(UserRole.ITEM_TYPE),
                                                          old_key, new_key)
                # dump to yaml file
                autotools.dump_yaml_file(self.autolog.yamlDict, self.autolog.yamlFilename)

    @Slot()
    def move_element_to_another_sample(self):
        """
        Slot to transfer an editable item from one sample to another.

        In the case of a microscope picture or a video, from a filesystem point of view it is like moving them from a
        directory to another.

        In the case of a sample, the filesystem equivalent is to rename the folder with a different name.

        For sample and videos, the yaml customization is preserved.

        Returns
        -------

        """
        # current index is invalid. exit now
        if not self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
            return

        # get the item from the index
        proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
        model_index = self.tree_model_proxy.mapToSource(proxy_index)
        item = self.tree_model.itemFromIndex(model_index)

        # check if the item could be moved to another sample. if not, just exit
        if item.data(UserRole.ITEM_TYPE) in [ElementType.SECTION, ElementType.TEXT, ElementType.NAVIGATION_PIC]:
            QMessageBox.information(self, 'Move to another sample',
                                    f'This element type {item.data(UserRole.ITEM_TYPE)} cannot be move to another '
                                    f'sample',
                                    buttons=QMessageBox.Ok)
            return

        # be sure that the custom values of the currently selected item are transferred
        self.update_values(self.autolog_tree_viewer.selectionModel().currentIndex())

        item_name = item.text()

        if item.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
            sample_name = item.data(UserRole.SAMPLE_FULL_NAME)
        elif item.data(UserRole.ITEM_TYPE) in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            sample_name = item.parent().data(UserRole.SAMPLE_FULL_NAME)
        elif item.data(UserRole.ITEM_TYPE) in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:
            if item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                sample_name = item.parent().data(UserRole.SAMPLE_FULL_NAME)
            else:
                sample_name = 'Protocol'
        else:
            sample_name = None

        sample_list = [self.sample_selector.itemText(i) for i in range(self.sample_selector.count())]
        if item.data(UserRole.ITEM_TYPE) in [ElementType.SAMPLE, ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
            sample_list.remove('Protocol')

        move_sample_dialog = ChangeSampleDialog(self, item_name, sample_name, sample_list)
        if move_sample_dialog.exec_():
            new_sample_full_name = move_sample_dialog.sample_combo.currentText()
        else:
            return

        if item.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
            # we are moving a sample to another sample.
            # from a FS point of view this is equivalent of renaming a directory
            src_dir = item.data(UserRole.SAMPLE_FULL_NAME)
            dest_dir = new_sample_full_name + '/' + item.data(UserRole.SAMPLE_LAST_NAME)

            # recycle the yaml customization
            self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict, item.data(UserRole.ITEM_TYPE),
                                                  src_dir, dest_dir)

            # prepare the command
            command = FileSystemCommand(FSCommandType.RENAME_DIR, Path(src_dir), Path(dest_dir))

        elif item.data(UserRole.ITEM_TYPE) in [ElementType.VIDEO_FILE, ElementType.MICROSCOPE_PIC]:
            # we are moving a video from one sample to another
            old_path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path(item.text())
            new_path = Path(new_sample_full_name) / Path(item.text())

            # recycle the yaml customization
            old_key = item.data(UserRole.VIDEO_KEY) if item.data(UserRole.ITEM_TYPE) == ElementType.VIDEO_FILE else \
                item.data(UserRole.PIC_ID)
            new_key = str(autotools.strip_path(old_key, old_path) / new_path)
            self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict,
                                                  item.data(UserRole.ITEM_TYPE), old_key, new_key)

            # prepare the command
            command = FileSystemCommand(FSCommandType.RENAME_FILE, old_path, new_path)

        elif item.data(UserRole.ITEM_TYPE) in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:
            if item.data(UserRole.ITEM_TYPE) == ElementType.ATTACHMENT_FILE:
                old_key = str(item.data(UserRole.ATTACHMENT_PATH))
            else:
                old_key = item.data(UserRole.OPTICAL_IMAGE_KEY)

            # we are moving an attachment or an optical image.
            if item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                # it is a sample wide element
                old_path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path(item.text())
                if new_sample_full_name == 'Protocol':
                    new_path = Path(item.text())
                else:
                    new_path = Path(new_sample_full_name) / Path(item.text())
            else:
                # it is protocol wide element
                old_path = Path(item.text())
                if new_sample_full_name == 'Protocol':
                    new_path = Path(item.text())
                else:
                    new_path = Path(new_sample_full_name) / Path(item.text())
            new_key = str(autotools.strip_path(old_key, old_path) / new_path)
            self.yaml_dictionary_recycler.recycle(self.autolog.yamlDict,
                                                  item.data(UserRole.ITEM_TYPE), old_key, new_key)

            # prepare the command
            command = FileSystemCommand(FSCommandType.RENAME_FILE, old_path, new_path)

        else:
            command = None

        if command:
            self.execute_filesystem_command.emit(command)

        # dump to yaml file
        autotools.dump_yaml_file(self.autolog.yamlDict, self.autolog.yamlFilename)

    def delete_protocol_element(self):
        """Delete one protocol element"""
        if self.autolog_tree_viewer.selectionModel().currentIndex().isValid():
            proxy_index = self.autolog_tree_viewer.selectionModel().currentIndex()
            model_index = self.tree_model_proxy.mapToSource(proxy_index)
            item = self.tree_model.itemFromIndex(model_index)
            if item.data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                command = FileSystemCommand(FSCommandType.DELETE_DIR,
                                            Path(item.data(UserRole.SAMPLE_FULL_NAME)))
            elif item.data(UserRole.ITEM_TYPE) in [ElementType.MICROSCOPE_PIC, ElementType.VIDEO_FILE]:
                parent_path = item.parent().data(UserRole.SAMPLE_FULL_NAME)
                name = item.text()
                command = FileSystemCommand(FSCommandType.DELETE_FILE,
                                            Path(parent_path) / Path(name))
            elif item.data(UserRole.ITEM_TYPE) == ElementType.NAVIGATION_PIC:
                path = Path(item.text())
                command = FileSystemCommand(FSCommandType.DELETE_FILE, path)
            elif item.data(UserRole.ITEM_TYPE) in [ElementType.ATTACHMENT_FILE, ElementType.OPTICAL_PIC]:
                if item.parent().data(UserRole.ITEM_TYPE) == ElementType.SAMPLE:
                    path = Path(item.parent().data(UserRole.SAMPLE_FULL_NAME)) / Path(item.text())
                else:
                    path = Path(item.text())
                command = FileSystemCommand(FSCommandType.DELETE_FILE, path)
            else:
                command = None

            if command:
                reply = QMessageBox.question(self, 'Delete protocol element',
                                             f'Are you sure you want to delete {str(command.input_path)}? This '
                                             f'operation can not be undone.',
                                             buttons=(QMessageBox.Yes | QMessageBox.No))
                if reply == QMessageBox.Yes:
                    self.execute_filesystem_command.emit(command)

    @Slot(QModelIndex)
    def enable_filesystem_command_buttons(self, index: QModelIndex | None):
        """Enable the filesystem dropdown buttons"""
        fs_buttons = [self.recycle_dropdown_button, self.edit_dropdown_button]

        if index is None:
            enable = False
        else:
            item = self.tree_model.itemFromIndex(self.tree_model_proxy.mapToSource(index))

            if item.data(UserRole.ITEM_TYPE) in [ElementType.MICROSCOPE_PIC,
                                                 ElementType.VIDEO_FILE,
                                                 ElementType.SAMPLE,
                                                 ElementType.ATTACHMENT_FILE,
                                                 ElementType.OPTICAL_PIC,
                                                 ElementType.NAVIGATION_PIC]:
                enable = True
            else:
                enable = False

        for button in fs_buttons:
            button.setEnabled(enable)
