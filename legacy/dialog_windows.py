# -*- coding: utf-8 -*-
"""Module containing ancillary dialog windows"""
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

import configparser
from pathlib import Path

from PyQt5 import QtCore
from PyQt5.QtCore import QObject
from PyQt5.Qt import QDialog, QFileDialog

from autologbook import autoconfig, autotools
from autologbook.about_dialog_ui import Ui_About
from autologbook.autotools import ReadOnlyDecision
from autologbook.change_sample_dialog_ui import Ui_ChangeSampleDialog
from autologbook.configuration_editor_ui import Ui_configurationDialog
from autologbook.edit_lock_dialog_ui import Ui_OverwriteEntryDialog
from autologbook.rename_dialog_ui import Ui_RenameDialog
from autologbook.user_editor_ui import Ui_UserEditor

Signal = QtCore.pyqtSignal
Slot = QtCore.pyqtSlot

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class AboutDialog(QDialog, Ui_About):
    """
    About Autolog Dialog.

    A very simple dialog message without button to show information about this
    program.
    """

    def __init__(self, parent=None):
        """
        Build an instance of the AboutDialog.

        Parameters
        ----------
        parent : QtObject, optional
            The parent calling QtObject. The default is None.

        Returns
        -------
        None.

        """
        super().__init__(parent)
        self.setupUi(self)


class ChangeSampleDialog(QDialog, Ui_ChangeSampleDialog):
    """
    Subclass of QDialog to deal with the moving of an item from one sample to another.
    """

    def __init__(self, parent: QObject = None, item_name: str | None = None, sample_name: str | None = None,
                 sample_list: list[str] | None = None) -> None:
        """
        Setup and initialize the dialog.

        Parameters
        ----------
        parent: QObject
            The parent object calling this dialog
        item_name: str
            The name of the item being moved.
        sample_name: str
            The sample (full name) where the item is at the moment. In the case of a root sample, use 'Samples' as
            sample name, it is to say the section name.
        sample_list: list[str]
            The list of all samples.
        """
        super().__init__(parent)
        self.setupUi(self)
        self.parent = parent

        is_root_sample = False
        if item_name is not None:
            self.item_name = item_name
            self.element_label.setText(self.item_name)
        if sample_name is not None:
            self.sample_name = sample_name
            if sample_name == 'Samples':
                # it means we are moving a root sample
                is_root_sample = True
            self.current_sample_label.setText(self.sample_name)
        if sample_list is not None:
            self.sample_list = sample_list  # [sample for sample in sample_list if sample != 'Protocol']
            self.sample_combo.addItems(self.sample_list)
            if not is_root_sample:
                self.sample_combo.model().item(self.sample_combo.findText(self.sample_name)).setEnabled(False)
            else:
                # since it is a root sample, then disable its name from the combo box.
                self.sample_combo.model().item(self.sample_combo.findText(self.item_name)).setEnabled(False)
            for i in range(self.sample_combo.count()):
                if self.sample_combo.model().item(i).isEnabled():
                    self.sample_combo.setCurrentIndex(i)
                    break


class ConfigurationEditorDialog(QDialog, Ui_configurationDialog):
    """
    A complete configuration editor dialog.

    This dialog window allows the user to manipulate all configuration
    parameters.

    The user can load a file, save the current configuration to a file or
    reset to the default configuration.

    """

    def __init__(self, parent=None):
        """
        Build an instance of the ConfigurationEditorDialog.

        Parameters
        ----------
        parent : QtObject, optional
            The parent caller of this dialog. The default is None.

        Returns
        -------
        None.

        """
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)

        # we need to fill in the microscope combolist
        for i in range(self.parent.select_microscope_comboBox.model().rowCount()):
            self.default_microscope_combo.addItem(self.parent.select_microscope_comboBox.model().item(i).text())

        # use this boolean to check if the password was changed during the
        # configuration editing.
        self.password_changed = False

        # use this string to store the encrypted password
        self.encrypted_pwd = ''

    @Slot(str)
    def password_edited(self, new_plain_text_pwd):
        """
        React to a password change.

        When the user edits the password, he is introducing a plain text string.
        This will never be saved in the configuration file nor in the configuration
        object.

        This slot is automatically invoked whenever the password field is edited,
        the new encrypted password is calculated and a flag to signalize that the
        password must be updated is raised.

        Parameters
        ----------
        new_plain_text_pwd : string
            The new plain text password.

        Returns
        -------
        None.

        """
        self.password_changed = True
        self.encrypted_pwd = autotools.encrypt_pass(new_plain_text_pwd)

    def set_all_values(self, config):
        """
        Set the values of all widgets to what is stored in the configuration object.

        The coding style of this method is terrible, I will look for something
        better.

        Parameters
        ----------
        config : ConfigParser object
            The configuration parser object containing all the parameters.

        Returns
        -------
        None.

        """
        # elog
        self.elog_user_field.setText(config.get('elog', 'elog_user', fallback=autoconfig.ELOG_USER))
        self.elog_password_field.setText(config.get('elog', 'elog_password', fallback=autoconfig.ELOG_PASSWORD))
        self.elog_hostname_field.setText(config.get('elog', 'elog_hostname', fallback=autoconfig.ELOG_HOSTNAME))
        self.elog_port_field.setValue(config.getint('elog', 'elog_port', fallback=autoconfig.ELOG_PORT))
        self.elog_max_auth_error_field.setValue(config.getint('elog', 'max_auth_error',
                                                              fallback=autoconfig.MAX_AUTH_ERROR))
        self.elog_ssl_check_box.setChecked(config.getboolean('elog', 'use_ssl', fallback=autoconfig.USE_SSL))
        self.elog_timeout_spinbox.setValue(config.getfloat('elog', 'elog_timeout', fallback=autoconfig.ELOG_TIMEOUT))
        self.attempts_on_timeout_spinbox.setValue(config.getint('elog', 'elog_timeout_max_retry',
                                                                fallback=autoconfig.ELOG_TIMEOUT_MAX_RETRY))
        self.waiting_time_between_timeout_attempts_spingbox.setValue(
            config.getfloat('elog', 'elog_timeout_wait', fallback=autoconfig.ELOG_TIMEOUT_WAIT))
        self.microscopy_protocol_list.setText(config.get('elog', 'microscopy_protocol_list',
                                                         fallback=autoconfig.PROTOCOL_LIST_LOGBOOK))

        # autolog
        self.autologbook_max_attempts_spinbox.setValue(
            config.getint('Autologbook watchdog', 'max_attempts',
                          fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS))
        self.autologbook_wait_min_spinbox.setValue(
            config.getfloat('Autologbook watchdog', 'wait_min', fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MIN))
        self.autologbook_wait_max_spinbox.setValue(
            config.getfloat('Autologbook watchdog', 'wait_max', fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MAX))
        self.autologbook_wait_increment_spinbox.setValue(
            config.getfloat('Autologbook watchdog', 'wait_increment',
                            fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT))
        self.autologbook_min_delay_spinbox.setValue(
            config.getfloat('Autologbook watchdog', 'minimum delay between elog post',
                            fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_MIN_DELAY))
        self.autologbook_observer_timeout_spinbox.setValue(
            config.getfloat('Autologbook watchdog', 'observer_timeout',
                            fallback=autoconfig.AUTOLOGBOOK_WATCHDOG_TIMEOUT))

        # mirroring
        self.mirroring_max_attempts_spinbox.setValue(
            config.getint('Mirroring watchdog', 'max_attempts', fallback=autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS))
        self.mirroring_wait_spinbox.setValue(
            config.getfloat('Mirroring watchdog', 'wait', fallback=autoconfig.AUTOLOGBOOK_MIRRORING_WAIT))
        self.mirroring_observer_timeout_spinbox.setValue(
            config.getfloat('Mirroring watchdog', 'observer_timeout',
                            fallback=autoconfig.AUTOLOGBOOK_MIRRORING_TIMEOUT))

        # quattro
        self.quattro_elog_logbook_field.setText(config.get('Quattro', 'logbook', fallback=autoconfig.QUATTRO_LOGBOOK))
        self.quattro_navcam_size_spinbox.setValue(
            config.getint('Quattro', 'image_navcam_width', fallback=autoconfig.IMAGE_NAVIGATION_MAX_WIDTH))

        # versa
        self.versa_elog_logbook_field.setText(config.get('Versa', 'logbook', fallback=autoconfig.VERSA_LOGBOOK))

        # vega
        self.vega_elog_logbook_field.setText(config.get('Vega', 'logbook', fallback=autoconfig.VEGA_LOGBOOK))
        self.vega_auto_calibrated_checkbok.setChecked(
            config.getboolean('Vega', 'auto_calibration', fallback=autoconfig.VEGA_AUTO_CALIBRATION))

        # xl40
        self.xl40_auto_calibrated_checkbok.setChecked(
            config.getboolean('XL40', 'auto_calibration', fallback=autoconfig.XL40_AUTO_CALIBRATION))
        self.xl40cold_elog_logbook_field.setText(
            config.get('XL40-Cold', 'logbook', fallback=autoconfig.XL40COLD_LOGBOOK))
        self.xl40gb_elog_logbook_field.setText(config.get('XL40-GB', 'logbook', fallback=autoconfig.XL40GB_LOGBOOK))

        # image server
        self.base_path_field.setText(
            config.get('Image_server', 'base_path', fallback=autoconfig.IMAGE_SERVER_BASE_PATH))
        self.server_root_field.setText(
            config.get('Image_server', 'server_root', fallback=autoconfig.IMAGE_SERVER_ROOT_URL))
        self.img_thumb_size_spinbox.setValue(
            config.getint('Image_server', 'image_thumb_width', fallback=autoconfig.IMAGE_SAMPLE_THUMB_MAX_WIDTH))
        self.custom_id_start_spinBox.setValue(
            config.getint('Image_server', 'custom_id_start', fallback=autoconfig.CUSTOMID_START))
        self.custom_id_tiff_tag_spinBok.setValue(
            config.getint('Image_server', 'tiff_tag_code', fallback=autoconfig.CUSTOMID_TIFFCODE))
        self.fei_auto_calibrated_checkbok.setChecked(
            config.getboolean('FEI', 'auto_calibration', fallback=autoconfig.FEI_AUTO_CALIBRATION))
        self.fei_crop_databar_checkbok.setChecked(
            config.getboolean('FEI', 'databar_removal', fallback=autoconfig.FEI_DATABAR_REMOVAL))

        # GUI default
        self.default_microscope_combo.setCurrentText(
            config.get('GUI_DEFAULT', 'default_microscope', fallback=autoconfig.DEFAULT_MICROSCOPE))
        self.default_protocol_folder.setText(
            config.get('GUI_DEFAULT', 'default_protocol_folder', fallback=autoconfig.DEFAULT_PROTOCOL_FOLDER))
        self.default_mirroring_folder.setText(
            config.get('GUI_DEFAULT', 'default_mirroring_folder', fallback=autoconfig.DEFAULT_MIRRORING_FOLDER))

        # be sure that the software is informed that the password has not been changed yet.
        self.password_changed = False

    def get_conf(self):
        """
        Get a configuration object from the value in the dialog.

        A configuration parser object is created with all the sections and all
        the options set to the values in the dialog.

        Returns
        -------
        config : ConfigParser
            A ConfigParser containing the options contained in the dialog.

        """
        config = configparser.ConfigParser()
        if self.password_changed:
            new_password = self.encrypted_pwd
        else:
            new_password = self.elog_password_field.text()
        config['elog'] = {
            'elog_user': self.elog_user_field.text(),
            'elog_password': new_password,
            'elog_hostname': self.elog_hostname_field.text(),
            'elog_port': str(self.elog_port_field.value()),
            'use_encrypt_pwd': True,
            'max_auth_error': self.elog_max_auth_error_field.value(),
            'use_ssl': self.elog_ssl_check_box.isChecked(),
            'elog_timeout': str(self.elog_timeout_spinbox.value()),
            'elog_timeout_max_retry': str(self.attempts_on_timeout_spinbox.value()),
            'elog_timeout_wait': str(self.waiting_time_between_timeout_attempts_spingbox.value()),
            'microscopy_protocol_list': str(self.microscopy_protocol_list.text()),
        }
        config['Autologbook watchdog'] = {
            'max_attempts': str(self.autologbook_max_attempts_spinbox.value()),
            'wait_min': str(self.autologbook_wait_min_spinbox.value()),
            'wait_max': str(self.autologbook_wait_max_spinbox.value()),
            'wait_increment': str(self.autologbook_wait_increment_spinbox.value()),
            'minimum delay between elog post': str(self.autologbook_min_delay_spinbox.value()),
            'observer_timeout': self.autologbook_observer_timeout_spinbox.value()
        }
        config['Mirroring watchdog'] = {
            'max_attempts': str(self.mirroring_max_attempts_spinbox.value()),
            'wait': str(self.mirroring_wait_spinbox.value()),
            'observer_timeout': self.mirroring_observer_timeout_spinbox.value()
        }
        config['Quattro'] = {
            'logbook': self.quattro_elog_logbook_field.text(),
            'image_navcam_width': self.quattro_navcam_size_spinbox.value()
        }
        config['Versa'] = {
            'logbook': self.versa_elog_logbook_field.text()
        }
        config['Image_server'] = {
            'base_path': str(Path(self.base_path_field.text())),
            'server_root': self.server_root_field.text(),
            'image_thumb_width': self.img_thumb_size_spinbox.value(),
            'custom_id_start': self.custom_id_start_spinBox.value(),
            'tiff_tag_code': self.custom_id_tiff_tag_spinBok.value()
        }
        config['FEI'] = {
            'auto_calibration': self.fei_auto_calibrated_checkbok.isChecked(),
            'databar_removal': self.fei_crop_databar_checkbok.isChecked()
        }
        config['Vega'] = {
            'auto_calibration': self.vega_auto_calibrated_checkbok.isChecked(),
            'logbook': self.vega_elog_logbook_field.text()
        }
        config['XL40'] = {
            'auto_calibration': self.xl40_auto_calibrated_checkbok.isChecked(),
        }
        config['XL40-GB'] = {
            'logbook': self.xl40gb_elog_logbook_field.text(),
        }
        config['XL40-Cold'] = {
            'logbook': self.xl40cold_elog_logbook_field.text(),
        }
        config['GUI_DEFAULT'] = {
            'default_microscope': self.default_microscope_combo.currentText(),
            'default_protocol_folder': str(Path(self.default_protocol_folder.text())),
            'default_mirroring_folder': str(Path(self.default_mirroring_folder.text())),
        }
        self.password_changed = False
        return config

    @Slot()
    def save_conf_file(self):
        """
        Save the configuration from the dialog to a file.

        This slot is connected with Save configuration push button.

        Returns
        -------
        None.

        """
        directory = Path.home() / Path('Documents')
        conffile = QFileDialog.getSaveFileName(self, 'Save configuration file', directory=str(directory),
                                               filter='Configuration file (*.ini)')
        if conffile[0]:
            autotools.write_conffile(self.get_conf(), conffile[0])

    @Slot()
    def load_conf_file(self):
        """
        Load a configuration file to the dialog.

        This slot is connected to the load file pushbutton.

        Returns
        -------
        None.

        """
        directory = Path.home() / Path('Documents')
        conffile = QFileDialog.getOpenFileName(self, 'Open configuration file', directory=str(directory),
                                               filter='Configuration file (*.ini)')
        if conffile[0]:
            conf = autotools.safe_configread(conffile[0])
            self.set_all_values(conf)

    @Slot()
    def reset_conf(self):
        """
        Reset the content of the dialog to the default.

        This slot is connected to the reset default pushbutton.

        Returns
        -------
        None.

        """
        self.set_all_values(autotools.generate_default_conf())

    @Slot()
    def search_basepath(self):
        """
        Search for the base path of the image server.

        This slot is connected to the tool button next to base folder input.

        Returns
        -------
        None.

        """
        if self.base_path_field:
            directory = Path(self.base_path_field.text())
        else:
            directory = Path.home() / Path('Documents')
        returnpath = QFileDialog.getExistingDirectory(self, 'Select base path of image server',
                                                      directory=str(directory))
        if returnpath:
            self.base_path_field.setText(returnpath)


class ReadOnlyEntryDialog(QDialog, Ui_OverwriteEntryDialog):
    """Dialog window to decide how to handle read-only entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setupUi(self)
        self.decision = ReadOnlyDecision.Edit

    def set_message(self, protocol_id):
        """
        Update the message of the dialog window using the current protocol_id.

        Parameters
        ----------
        protocol_id : string
            The current protocol ID number.

        Returns
        -------
        None.

        """
        msg = (f'<html><head/><body><p>On the elog server, an entry corresponding to the protocol number {protocol_id} '
               'already exists and it is<span style=" font-weight:600;"> read-only</span>.'
               '</p><p>In order to continue, '
               'you have to select one of the following three options.'
               '</p><ul style="margin-top: 0px; margin-bottom: 0px; margin-left: 0px; margin-right: 0px;'
               ' -qt-list-indent: 1;">'
               '<li style=" margin-top:12px; margin-bottom:12px; margin-left:0px; margin-right:0px;'
               '-qt-block-indent:0; text-indent:0px;">'
               'Force overwrite the read-only entry (<span style=" font-weight:600;">Force overwrite</span>)</li>'
               '<li style=" margin-top:12px; margin-bottom:12px; margin-left:0px; margin-right:0px;'
               ' -qt-block-indent:0; text-indent:0px;">'
               'Make a backup of the read-only entry modifying its protocol ID (<span style=" font-weight:600;">'
               'Backup read-only entry</span>)</li><li style=" margin-top:12px; margin-bottom:12px; margin-left:0px; '
               'margin-right:0px; -qt-block-indent:0; text-indent:0px;">Change the protocol ID of'
               ' the current experiment'
               'manually (<span style=" font-weight:600;">Edit manually</span>)</li></ul></body></html>')
        self.label.setText(msg)

    @Slot()
    def force_overwrite_selected(self):
        """
        Set decision to ReadOnlyDecision.Overwrite.

        Returns
        -------
        None.

        """
        self.decision = ReadOnlyDecision.Overwrite
        self.done(self.decision)

    @Slot()
    def backup_readonly_selected(self):
        """
        Set decision to ReadOnlyDecision.Backup.

        Returns
        -------
        None.

        """
        self.decision = ReadOnlyDecision.Backup
        self.done(self.decision)

    @Slot()
    def cancel_selected(self):
        """
        Set decision to ReadOnlyDecision.Edit.

        Returns
        -------
        None.

        """
        self.decision = ReadOnlyDecision.Edit
        self.done(self.decision)


class RenameDialog(QDialog, Ui_RenameDialog):
    """
    Subclass of QDialog to deal with the renaming of an item.
    """

    def __init__(self, parent: QObject = None, text: str = None, original_name: str = None):
        """
        Setup and initialize the dialog.

        Parameters
        ----------
        parent: QObject
            The parent object calling this dialog.
        text: str
            The text to be displayed.
        original_name: str
            The original name of the object being renamed.
        """
        super().__init__(parent)
        self.setupUi(self)
        self.parent = parent
        if text is not None:
            self.message.setText(text)
        if original_name is not None:
            self.new_name_field.setText(original_name)


class UserEditor(QDialog, Ui_UserEditor):
    """Dialog window for the user credential editor."""

    def __init__(self, parent=None, username=None, password=None):
        """
        Build a new instance of the user editor.

        Parameters
        ----------
        parent : QObject, optional
            The parent object, very likely the MainWindow. The default is None.
        username : string, optional
            The current username. The default is None
        password : string, optional
            The current password. The default is None

        Returns
        -------
        None.

        """
        super().__init__(parent)
        self.setupUi(self)
        self.parent = parent
        self.username = username
        self.username_line_edit.setText(username)
        self.password = password
        self.password_line_edit.setText(password)

    @Slot(str)
    def password_edited(self, new_plain_text_pwd):
        """
        React to a password change.

        This slot is called everytime the password field is edited.

        Parameters
        ----------
        new_plain_text_pwd : string
            The newly entered password in plain text.

        Returns
        -------
        None.

        """
        self.password = autotools.encrypt_pass(new_plain_text_pwd)

    @Slot(str)
    def username_edited(self, new_username):
        """
        React to a username change.

        This slot is called everytime the username field is edited.

        Parameters
        ----------
        new_username : string
            The newly entered username in plain text.

        Returns
        -------
        None.

        """
        self.username = new_username
