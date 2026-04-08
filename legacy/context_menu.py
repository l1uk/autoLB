# -*- coding: utf-8 -*-
"""Utility for context menu handling."""
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

from PyQt5.QtCore import QObject
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QAction, QMenu, QShortcut

from autologbook.autotools import VisibilityFlag


def generate_context_menu_from_scheme(context_menu: QMenu | None, parent: QObject, menu_scheme: dict) -> QMenu:
    if context_menu is None:
        # the context_menu passed by the user is empty. it means that we need to create one.
        context_menu = QMenu(parent)
        for element in menu_scheme.values():
            # we need to replace the context_menu object to the scheme
            if element['parent_name'] == 'root':
                element['parent_obj'] = context_menu

    icon = QIcon()

    for key, element in menu_scheme.items():
        new_item = element['type'](element['text'], element['parent_obj'])
        new_item.setObjectName(element['name'])

        # use the set property method of the QObject to store the show_when_flag
        # this can be done for QMenus and QActions
        new_item.setProperty('visibility', element['show_when_flag'])
        element['obj'] = new_item

        if isinstance(new_item, QAction):
            new_item.setText(element['text'])
            # noinspection PyUnresolvedReferences
            new_item.triggered.connect(element['slot'])
            element['parent_obj'].addAction(new_item)
            # new_item.setData(element['show_when_flag'])
            if element.get('short_cut_key_sequence', None):
                sc = QShortcut(element['short_cut_key_sequence'], parent, member=element['slot'])
                new_item.setShortcut(sc.key())

        else:  # if isinstance(new_item, QMenu):
            new_item.setTitle(element['text'])
            element['parent_obj'].addMenu(new_item)

        if element.get('icon', None):
            icon.addPixmap(QPixmap(element['icon']), QIcon.Normal, QIcon.Off)
            new_item.setIcon(icon)

        if element['separator_after']:
            element['parent_obj'].addSeparator()

        # I need to reloop in order to update its child.
        for e in menu_scheme.values():
            if key == e['parent_name']:
                e['parent_obj'] = new_item
    return context_menu


def filter_context_menu(menu: QMenu, visibility: VisibilityFlag):
    for element in menu.actions():
        if element.isSeparator():
            pass
        elif element.menu():
            filter_context_menu(element.menu(), visibility)
            if 'visibility' in element.dynamicPropertyNames():
                element.setVisible(bool(element.property('visibility') & visibility))
            else:
                element.setVisible(True)
        else:  # element is action
            if 'visibility' in element.dynamicPropertyNames():
                element.setVisible(bool(element.property('visibility') & visibility))
            else:
                element.setVisible(True)

    for element in menu.actions():
        if element.menu():
            item_visibility = [sub_el.isVisible() for sub_el in element.menu().actions() if not sub_el.isSeparator()]
            element.setVisible(any(item_visibility))


def generate_tool_button_menu_from_scheme(menu: QMenu | None, parent: QObject, menu_scheme: dict) -> QMenu():
    if menu is None:
        menu = QMenu(parent)

    icon = QIcon()
    for element in menu_scheme.values():
        new_action = QAction(element['text'], menu)
        icon.addPixmap(QPixmap(element['icon']), QIcon.Normal, QIcon.Off)
        new_action.setIcon(icon)
        new_action.triggered.connect(element['slot'])
        menu.addAction(new_action)

    return menu
