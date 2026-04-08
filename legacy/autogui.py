# -*- coding: utf-8 -*-
"""
Created on Sat May 21 12:10:26 2022

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
from __future__ import annotations

import configparser
import ctypes
import logging
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import elog
import urllib3
import yaml
from bs4 import BeautifulSoup
from elog.logbook_exceptions import LogbookServerTimeout
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QPoint, QSettings, Qt, QTimer
from PyQt5.QtWidgets import QAction, QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox
from tenacity import after_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from yaml.representer import SafeRepresenter

from autologbook import autoconfig, autoerror, autoprotocol, autotools
from autologbook.autotools import ReadOnlyDecision
from autologbook.context_menu import filter_context_menu, generate_context_menu_from_scheme
from autologbook.dialog_windows import AboutDialog, ConfigurationEditorDialog, ReadOnlyEntryDialog, UserEditor
from autologbook.elog_interface import ELOGConnectionParameters, elog_handle_factory
from autologbook.file_system_command import FileSystemCommand, FileSystemCommander
from autologbook.jinja_integration import jinja_env
from autologbook.main_window_ui import Ui_MainWindow
from autologbook.protocol_editor import ProtocolEditor
from autologbook.protocol_editor_models import ElementType
from autologbook.thread_worker import SingleWatchdogWorker

Signal = QtCore.pyqtSignal
Slot = QtCore.pyqtSlot

urllib3.disable_warnings()

represent_literal_str = autotools.change_style('|', SafeRepresenter.represent_str)
yaml.add_representer(autotools.literal_str, represent_literal_str)

log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class PathValidator:
    """
    Helper class to validate the input paths.

    Use it to validate the input folder fields to decide
    if the watchdog can be started or not.

    """

    # TODO: consider the possibility to replace the validity constants with
    # a flag enumerator.
    Invalid = 0
    AcceptableIfMirroringActive = 10
    AcceptableIfCustomOwnership = 20
    Acceptable = 30

    def __init__(self, path: str | Path, base_path='R:\\A226\\Results',
                 pattern='^([\\d]+)\\s*[-_]\\s*([\\w\\W]+)\\s*[-_]\\s*([\\w\\W]+)$'):
        r"""
        Build an instance of the PathValidator.

        You won't use it because you should use the static class function ValidatePath

        Note: traditionally Versa paths are starting with a # symbol. While this is perfectly
              ok with the filesystem, when the path is converted to a URI on the image file server
              the # symbol is causing problems. The webserver will consider it as the starting
              point of a URL fragment and not part of the URL itself.
              **We cannot accept # symbols in protocol folder on the Image Server!**

        Parameters
        ----------
        path : Path | str
            This is the path that is being validated.
        base_path : Path | str, optional
            This is the base path where all the protocols should be saved.
            The default is 'R:\\A226\\Results'.
        pattern : str, optional
            This is the pattern that the leaf folder should match.
            It should be something like this:
                1234 - ProjectName - ProjectResponsible
            The default is '^([\d]+)\s*[-_]\s*([\w\W]+)\s*[-_]\s*([\w\W]+)$'.

        Returns
        -------
        None.

        """
        self.path = path
        self.base_path = Path(base_path)
        self.pattern = pattern

    def get_ownership_parameters(self):
        """
        Retrieve the ownership parameters from the folder name.

        Using the pattern provided in the constructor, try to guess the three
        ownership parameters. If it fails, None is returned.

        Returns
        -------
        int or str
            The project ID
        str
            The project name
        str
            The responsible..

        """
        if self.path == '':
            return None
        self.path = Path(self.path)
        folder_name = self.path.parts[-1]
        match = re.search(self.pattern, folder_name)
        if match:
            return match[1], match[2], match[3]
        return None

    def validate(self):
        """
        Validate the path.

        This class member can return three possible state:
            1. Invalid. The provided path is invalid and thus the watchdog cannot be start
            2. AcceptableIfMirroringActive. The provided path is not invalid and the watchdog
               can be started if the mirroring is activated and the mirroring folder is Acceptable
            3. Acceptable. The provided path is valid in all cases.

        There are several checks that need to be done:
            1. The path is empty or not existing, or not a directory, then Invalid is returned.
            2. The path is not relative to the base_path, then AcceptableIfMirroringActive is returned.
            3. The path is relative to the base_path, but the leaf directory is not matching the regular
               expression, then AccetableIfMirroringActive is returned.
            4. the path is starting with # symbol (traditional Versa folder), then
               AcceptableIfMirroringActive is returned
            5. The path is relative to the base_path and the leaf directory is matching the regular
               expression then Acceptable is returned.

        Returns
        -------
        VALIDITY Constant
            See the description for an explanation.

        """
        if not self.path:
            return self.Invalid
        self.path = Path(self.path)

        if len(str(self.path)) == 0:
            return self.Invalid
        if self.path.exists() and self.path.is_dir():
            if '#' in str(self.path):
                # found a # symbol in the path. Very likely this is a Versa folder.
                # the folder can be accepted only if it is mirrored somewhere else.
                return self.AcceptableIfMirroringActive
            if self.path.is_relative_to(autoconfig.IMAGE_SERVER_BASE_PATH):
                # the path is in the right position.
                # let's check if the ownership variables are in the folder name
                folder_name = self.path.parts[-1]
                match = re.search(self.pattern, folder_name)
                if match:
                    # very good, we are all set
                    return self.Acceptable
                else:
                    # we need to ask the user to use custom ownership variables
                    return self.AcceptableIfCustomOwnership
            return self.AcceptableIfMirroringActive
        return self.Invalid


def validate_path(path: str | Path, base_path: str | Path = 'R:\\A226\\Results',
                  pattern: str | re.Pattern = '^*([\\d]+)\\s*[-_]\\s*([\\w\\W]+)\\s*[-_]\\s*([\\w\\W]+)$') -> int:
    """Return the validity of a path."""
    return PathValidator(path, base_path, pattern).validate()


class Signaller(QtCore.QObject):
    """
    A subclass of QObject to contain a signal.

    Only QObejct derived instances are allowed to have a signal, so if you want to have a no
    QtObject to emit a signal, you have to add a Signaller like this to its attributes.

    This specific signaller contains only one Qt Signal emitting a formatted string a logging.LogRecord
    and it is used to establish a communication between the logging module and a PlainText object in a
    QtWindow.

    """

    signal = Signal(str, logging.LogRecord)


class QtHandler(logging.Handler):
    """
    A subclass of the logging.Handler.

    It incorporates a Signaller to be able to emit a Qt Signal.

    """

    def __init__(self, slotfunc, *args, **kwargs):
        """
        Build an instance of QtHandler.

        Parameters
        ----------
        slotfunc : CALLABLE
            The slot function which the Signaller.signal is connected.
        *args : positional arguments
            All other positional arguments to be passed to the parent constructor.
        **kwargs : keyword arguments
            All keywork arguments to be passed to the parent constructor.

        Returns
        -------
        None.

        """
        super().__init__(*args, **kwargs)
        self.signaller = Signaller()
        self.signaller.signal.connect(slotfunc)

    def emit(self, record):
        """Emit the signaller signal containing the formatted string and the logging.Record."""
        s = self.format(record)
        self.signaller.signal.emit(s, record)


class MainWindow(QMainWindow, Ui_MainWindow):
    """The main window of the GUI."""

    # Used to have different colors for each logging level.
    COLORS = {
        logging.DEBUG: 'black',
        logging.INFO - 5: 'hotpink',
        logging.INFO: 'blue',
        logging.WARNING: 'orange',
        logging.ERROR: 'red',
        logging.CRITICAL: 'purple'
    }

    # prepare custom signals
    added_element = Signal(ElementType, str, str, name='added_element')
    removed_element = Signal(ElementType, str, str, name='removed_element')
    change_autolog = Signal(autoprotocol.Protocol, name='change_autolog')
    reset_content = Signal(name='reset_content')

    title_modifier = ' *'

    max_recent_files = 5

    class GUIContent:
        """
        Helper class to store and manipulate the content of the GUI.
        """

        def __init__(self):
            self.protocol_folder = None
            self.mirroring_folder = None
            self.microscope = None
            self.mirroring_switch = False
            self.custom_switch = False
            self.custom_protocolID = None
            self.custom_project = None
            self.custom_responsible = None

        def __eq__(self, other: MainWindow.GUIContent):

            are_the_same = True and self.protocol_folder == other.protocol_folder \
                           and self.microscope == other.microscope \
                           and self.mirroring_switch == other.mirroring_switch \
                           and self.custom_switch == other.custom_switch

            if self.mirroring_switch:
                are_the_same = are_the_same and self.mirroring_folder == other.mirroring_folder

            if self.custom_switch:
                are_the_same = are_the_same and self.custom_protocolID == other.custom_protocolID \
                               and self.custom_project == other.custom_project \
                               and self.custom_responsible == other.custom_responsible

            return are_the_same

        @classmethod
        def from_main_window(cls, main_window: MainWindow) -> MainWindow.GUIContent:
            """
            Build a GUIContent given a main window instance.

            Parameters
            ----------
            main_window:
                The instance of the main window from where the GUI parameters are retrieved.

            Returns
            -------
            A GUIContent class containing the values present in the GUI.
            """
            c = cls()
            c.protocol_folder = main_window.protocol_folder_text.text()
            c.mirroring_folder = main_window.mirroring_folder_text.text()
            c.mirroring_switch = main_window.mirror_checkBox.isChecked()
            c.microscope = main_window.select_microscope_comboBox.currentText()
            c.custom_switch = main_window.custom_ownership_checkbox.isChecked()
            c.custom_protocolID = main_window.projectID_field.text()
            c.custom_project = main_window.project_name_field.text()
            c.custom_responsible = main_window.responsible_field.text()
            return c

        def apply_to_gui(self, gui: MainWindow):
            """
            Set the values of all the gui widgets with the values stored in the class.

            Parameters
            ----------
            gui: MainWindow
                The instance of MainWindow where the values stored in the class will be applied.
            """
            gui.protocol_folder_text.setText(self.protocol_folder)
            gui.mirroring_folder_text.setText(self.mirroring_folder)
            gui.mirror_checkBox.setChecked(self.mirroring_switch)
            gui.select_microscope_comboBox.setCurrentText(self.microscope)
            gui.custom_ownership_checkbox.setChecked(self.custom_switch)
            gui.projectID_field.setText(self.custom_protocolID)
            gui.project_name_field.setText(self.custom_project)
            gui.responsible_field.setText(self.custom_responsible)

        def transfer_to_config(self, config: configparser.ConfigParser) -> configparser.ConfigParser:
            """
            Transfer the GUI content values to a configuration object.

            This method can be used to generate an experiment file.

            Parameters
            ----------
            config: configparser.ConfigParser
                The configuration parser object to transfer

            Returns
            -------
            The configuration parser containing also the GUI values
            """
            if 'GUI' not in config.sections():
                config.add_section('GUI')
            config.set('GUI', 'src_path', str(Path(self.protocol_folder)))
            config.set('GUI', 'mirror', str(self.mirroring_switch))
            if self.mirroring_switch:
                config.set('GUI', 'mirror_path', str(Path(self.mirroring_folder)))
            else:
                config.set('GUI', 'mirror_path', '')
            config.set('GUI', 'microscope', self.microscope)
            config.set('GUI', 'custom_ownership', str(self.custom_switch))
            if self.custom_switch:
                config.set('GUI', 'projectID', self.custom_protocolID)
                config.set('GUI', 'project_name', self.custom_project)
                config.set('GUI', 'responsible', self.custom_responsible)
            else:
                config.set('GUI', 'projectID', '')
                config.set('GUI', 'project_name', '')
                config.set('GUI', 'responsible', '')
            return config

    def __init__(self, app: QApplication, config: configparser.ConfigParser):
        """
        Build an instance of the GUI main window.

        Setup the user interface as produced by the QtDesigner
        Setup the logging machinery in order to have all logging messages
        redirected to the GUI
        Call the start_thread method and finally do all signal slot connections.

        Parameters
        ----------
        app : QApplication
            The application calling the main window.

        Returns
        -------
        None.

        """
        super().__init__()
        self.app = app
        self.config = config
        self.setupUi(self)

        # set the protocol editor to none
        self.protocol_editor = None

        # create a logging handler with a slot function pointing to update_status
        self.handler = QtHandler(self.update_status)

        # create a formatter and assign it to the handler
        fs = '[%(asctime)s] %(threadName)-15s %(levelname)-8s %(message)s'
        formatter = logging.Formatter(fs, datefmt='%Y%m%d-%H:%M:%S')
        self.handler.setFormatter(formatter)
        log.addHandler(self.handler)

        # create a logging handler to a timed rotated file
        log_filepath = Path.home() / Path('autologbook') / Path('logs')
        log_filepath.mkdir(parents=True, exist_ok=True)
        log_filename = log_filepath / Path('autologbook-gui.log')

        self.file_handler = TimedRotatingFileHandler(filename=log_filename,
                                                     when='D', interval=7, backupCount=7)
        self.file_handler.setFormatter(formatter)
        log.addHandler(self.file_handler)

        # initialize workers and threads dictionaries
        self.workers = {}
        self.worker_threads = {}

        # start the threads and their workers
        self.start_thread()

        self.base_path = Path(autoconfig.IMAGE_SERVER_BASE_PATH)
        self.pattern = '^#*([\\d]+)\\s*[-_]\\s*([\\w\\W]+)\\s*[-_]\\s*([\\w\\W]+)$'
        self.is_watchdog_running = False
        self.is_watchdog_enabled = False

        self.is_ok_to_start = False
        self.are_user_credentials_checked = False
        self.is_mirroring_requested = self.mirror_checkBox.isChecked()
        self.is_custom_ownership_requested = self.custom_ownership_checkbox.isChecked()
        self.protocol_folder_path = None
        self.mirroring_folder_path = None
        self.microscope = self.config.get('GUI_DEFAULT', 'default_microscope', fallback='Quattro')
        self.select_microscope_comboBox.blockSignals(True)
        self.select_microscope_comboBox.setCurrentText(self.microscope)
        self.select_microscope_comboBox.blockSignals(False)
        self.browser_process = ''
        self.projectID = None
        self.project_name = None
        self.project_responsible = None
        self.path = None

        # recently open related stuff
        self.recent_file_actions = []
        # [self.actionRecent1, self.actionRecent2, self.actionRecent3, self.actionRecent4]
        self.generate_recent_file_actions()
        self.update_recent_file_actions()

        self.connect_signals_slot()

        self.experiment_filename = None
        self.experiment_need_save = False

        self.check_threads_status()
        self.thread_check_timer = QTimer()
        self.thread_check_timer.timeout.connect(self.check_threads_status)
        self.thread_check_timer.start(autoconfig.THREAD_STATUS_UPDATE)

        # create a FS Commander to execute commands received from the protocol editor
        self.file_system_commander = FileSystemCommander()

        self.log_message_box.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_context_menu = self.generate_log_context_menu()
        self.log_message_box.customContextMenuRequested.connect(self.show_log_context_menu)

        # store the current GUI content
        self.current_gui_content = MainWindow.GUIContent.from_main_window(self)

        # store the GUI content as from the last loaded experiment
        self.last_loaded_gui_content = MainWindow.GUIContent.from_main_window(self)

        # get a handle to the microscopy list
        elog_handle_factory.set_connection_parameters(ELOGConnectionParameters.from_config_module())

    def generate_recent_file_actions(self):

        for i in range(self.max_recent_files):
            action = QAction(self)
            action.setObjectName(f'actionRecent{i}')
            self.menuLoad_recent.addAction(action)
            self.recent_file_actions.append(action)

    def update_recent_file_actions(self):
        settings = QSettings('ecjrc', 'autologbook')
        files = settings.value('recent_file_list', [])
        for action in self.recent_file_actions:
            action.setVisible(False)
        for file, action in zip(files, self.recent_file_actions):
            p = Path(file)
            action.setText(f'{p.name}')
            action.setData(file)
            action.setVisible(True)

    def open_recent(self):
        action = self.sender()
        if action:
            self._load_experiment(action.data())

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if self.is_watchdog_running:
            event.ignore()
        else:
            if event.mimeData().hasUrls():
                event.accept()
            else:
                event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if len(files) > 1:
            log.warning('You have dropped more than one file, but only 1 experiment file can be loaded.')
            log.warning('Loading file %s', files[0])
        gui_content = MainWindow.GUIContent.from_main_window(self)
        try:
            self._load_experiment(files[0])
        except (UnicodeError, configparser.Error):
            log.error('Error loading experiment file %s' % files[0])
            gui_content.apply_to_gui(self)

    def show_log_context_menu(self, pos: QPoint):
        visibility_flag = autotools.LogMessageBoxVisibilityFlag.NO_SELECTION
        if self.log_message_box.textCursor().hasSelection():
            visibility_flag = autotools.LogMessageBoxVisibilityFlag.SELECTION

        filter_context_menu(self.log_context_menu, visibility_flag)
        self.log_context_menu.exec(self.log_message_box.viewport().mapToGlobal(pos))

    def generate_log_context_menu(self) -> QMenu:

        context_menu = self.log_message_box.createStandardContextMenu()
        context_menu.addSeparator()

        menu_scheme = {
            'clear': {
                'type': QAction,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'clear',
                'text': 'Clear logger',
                'icon': ':/resources/icons8-cancel-48.png',
                'slot': self.clear_logger,
                'show_when_flag': autotools.LogMessageBoxVisibilityFlag.ALWAYS,
                'separator_after': False,
            },
            'save': {
                'type': QAction,
                'obj': None,
                'parent_name': 'root',
                'parent_obj': context_menu,
                'name': 'save',
                'text': 'Save logger as...',
                'icon': ':/resources/icons8-save-as-48.png',
                'slot': self.save_logger,
                'show_when_flag': autotools.LogMessageBoxVisibilityFlag.ALWAYS,
                'separator_after': False,
            }
        }

        return generate_context_menu_from_scheme(context_menu, self.log_message_box, menu_scheme)

    def show(self, loglevel: int = logging.INFO):
        """
        Show the main window.

        Overload of the parent show method adding a message in the log window.

        Params:
        loglevel: int
            Change the Main Window appearance depending on the logging level.
            If loglevel >= logging.INFO, the standard GUI will be rendered, otherwise
            debug widgets will be shown.

        """
        log.info('Welcome to the autologbook GUI!')
        if loglevel >= logging.INFO:
            self.hide_debug_elements(True)

        super().show()

    def start_thread(self):
        """Start a separate thread where the single watchdog worker is working."""

        # prepare the single watchdog worker
        new_worker = SingleWatchdogWorker()
        new_worker.parent = self
        new_worker_thread = QtCore.QThread()
        new_worker.setObjectName('SingleWatchdog')
        new_worker_thread.setObjectName('WatchThread')
        new_worker.moveToThread(new_worker_thread)

        # connect the worker signals to the MainWindow slots
        new_worker.worker_is_running.connect(self.disable_inputs)

        # this start an event loop on the thread, not the Worker!
        new_worker_thread.start()

        # add references of the worker and of the thread to the MainWindow
        # to avoid garbage collection
        self.workers['SingleWatchdog'] = new_worker
        self.worker_threads['WatchThread'] = new_worker_thread

    def connect_signals_slot(self):
        """Connect Qt Signals to corresponding slots."""
        self.actionClose.triggered.connect(self.close)
        self.watchdog_pushbutton.clicked.connect(self.workers['SingleWatchdog'].toggle)
        self.action_toggle_watchdog.triggered.connect(self.workers['SingleWatchdog'].toggle)
        self.action_toggle_watchdog.triggered.connect(self.toggled_watchdog)
        self.action_Load_experiment.triggered.connect(self.load_experiment)
        self.actionSave_experiment.triggered.connect(self.save_experiment)
        self.actionSave_logger.triggered.connect(self.save_logger)
        self.actionClear_logger.triggered.connect(self.clear_logger)
        self.actionLoad_configuration_file.triggered.connect(self.load_conffile)
        self.actionAbout_Autologbook.triggered.connect(self.show_about)
        self.actionReset_to_default.triggered.connect(self.reset_conf)
        self.actionEdit_configuration.triggered.connect(self.edit_conf)
        self.actionChange_user_credentials.triggered.connect(self.edit_user_credentials)
        self.app.aboutToQuit.connect(self.force_quit)
        for action in self.recent_file_actions:
            action.triggered.connect(self.open_recent)

    def edit_conf(self):
        """
        Open the configuration editor window.

        After closing the window the following actions are processed:
            1. The configuration information from the window are transferred to
               the local_path dictionary
            2. The autotools.init function is called in order to initialize all
               sub-modules global variables.
            3. Inputs of the main window are validated.

        Returns
        -------
        None.

        """
        dialog = ConfigurationEditorDialog(parent=self)
        dialog.set_all_values(self.config)
        if dialog.exec_():
            self.config = dialog.get_conf()
            autotools.init(self.config)
            log.info('Configuration updated')
            self.are_user_credentials_checked = False
            self.validate_inputs()

    def load_conffile(self):
        """
        Load a configuration file.

        This function is called from the GUI and allows the user to load presets
        from a configuration file.

        It opens a file selection dialog restricted to *.ini file.
        If the user click on open, the following actions are processed:
            1. A configuration parser is created and the configuration file is parsed
            2. The autotools.init function is called
            3. The configuration object is assigned to the local_path configuration
            4. The inputs of the main window are validated.

        Returns
        -------
        None.

        """
        directory = Path.home() / Path('Documents')
        returnpath = QFileDialog.getOpenFileName(
            self, 'Configuration file', directory=str(directory), filter='Conf file (*.ini)')
        if returnpath[0]:
            conffile = Path(returnpath[0])
            conf = configparser.ConfigParser()
            conf.read(conffile)
            autotools.init(conf)
            self.config = conf
            log.info('Loading configuration file %s' % (str(conffile)))
            self.are_user_credentials_checked = False
            self.validate_inputs()

    def reset_conf(self):
        """
        Reset the configuration to the default.

        A new configuration object is created using the autotools.generate_default_conf()
        The autotools.init function is called.
        The local_path configuration object is reassigned.

        Returns
        -------
        None.

        """
        conf = autotools.generate_default_conf()
        autotools.init(conf)
        self.config = conf
        log.info('Loading default configuration')
        self.are_user_credentials_checked = False
        self.validate_inputs()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.experiment_need_save:
            ans = QMessageBox.question(self, 'Save experiment',
                                       'The current experiment was not saved. Would you like to save before exiting?',
                                       buttons=(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel))
            if ans == QMessageBox.Yes:
                self.save_experiment()
                event.accept()
            elif ans == QMessageBox.No:
                event.accept()
            elif ans == QMessageBox.Cancel:
                event.ignore()
            else:
                event.ignore()

    def force_quit(self):
        """
        Force quit the application.

        This function is called by the about to quit signal. It allows to
        quit as clean as possible all the open and running threads.

        Returns
        -------
        None.

        """

        for worker in self.workers.values():
            try:
                if worker.observer.is_alive():
                    worker.stop()
            except AttributeError:
                log.debug('Trying to quit an observer that was not created yet.')
        for thread in self.worker_threads.values():
            if thread.isRunning():
                thread.quit()
                thread.wait()

    def update_microscopy_protocol_list(self, status: str = 'On going'):
        elog_instance = elog_handle_factory.get_logbook_handle(autoconfig.PROTOCOL_LIST_LOGBOOK)
        msg_id = elog_instance.get_msg_id(self.projectID_field.text())
        if msg_id:
            message, attributes, attachments = elog_instance.read(msg_id, timeout=autoconfig.ELOG_TIMEOUT)

            # update the attributes
            attributes['Analysis status'] = status

            # let's check what was in the message
            soup = BeautifulSoup(message, 'lxml')
            description = soup.find(id='sample_description')
            url = self.workers['SingleWatchdog'].autoprotocol_instance.get_protocol_url()
            link = soup.find('a', href=url)
            if description and link:
                pass
            elif description and not link:
                message += jinja_env.get_template('microscope_list_post_url_only_template.yammy').render(url=url)
            else:
                message = jinja_env.get_template('microscope_list_post_url_only_template.yammy').render(
                    url=url, description=attributes['Sample description'])
            elog_instance.post(message, msg_id=msg_id, attributes=attributes, attachments=attachments,
                               encoding='HTML', timeout=autoconfig.ELOG_TIMEOUT)
            log.info('Updating protocol list database. Analysis status set to %s' % status)
        else:
            log.warning('Unable to update protocol list database')

    @Slot(str, logging.LogRecord)
    def update_status(self, status, record):
        """
        Update the status window.

        This is the Qt Slot connected to the QtHandler Signaller.

        Parameters
        ----------
        status : STRING
            The formatted string to be appended to the message window.
        record : logging.LogRecord
            The LogRecord as transmitted by the logging module.

        Returns
        -------
        None.

        """
        color = self.COLORS.get(record.levelno, 'black')
        s = '<pre><font color="%s">%s</font></pre>' % (color, status)
        self.log_message_box.appendHtml(s)

    def watchdog_pushbutton_facelift(self):
        """
        Adapt the main window appearance.

        Depending on the fact that the watchdog is running or not, the main window
        has to look differently. This function is performing a facelift of the main window

        Returns
        -------
        None.

        """

        if self.is_watchdog_running:
            self.watchdog_pushbutton.setText('Stop watchdog')
            self.watchdog_pushbutton.setToolTip('Stop the watchdog')
            icon3 = QtGui.QIcon()
            icon3.addPixmap(QtGui.QPixmap(":/resources/icons8-stop-sign-48.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.watchdog_pushbutton.setIcon(icon3)
            self.action_toggle_watchdog.setText('Stop watchdog')
            self.action_toggle_watchdog.setIcon(icon3)
            self.menuSettings.setEnabled(False)
            self.open_explorer_pushbuttom.setEnabled(True)
            self.open_browser_button.setEnabled(True)
            self.edit_custom_html_file_pushbutton.setEnabled(True)
            self.action_Load_experiment.setEnabled(False)
        else:
            self.watchdog_pushbutton.setText('Start watchdog')
            self.watchdog_pushbutton.setToolTip('Start the watchdog')
            icon3 = QtGui.QIcon()
            icon3.addPixmap(QtGui.QPixmap(":/resources/icons8-play-48.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.watchdog_pushbutton.setIcon(icon3)
            self.menuSettings.setEnabled(True)
            self.action_toggle_watchdog.setText('Start watchdog')
            self.action_toggle_watchdog.setIcon(icon3)
            self.open_explorer_pushbuttom.setEnabled(False)
            self.open_browser_button.setEnabled(False)
            self.edit_custom_html_file_pushbutton.setEnabled(False)
            if self.protocol_editor:
                self.protocol_editor.hide()
            self.action_Load_experiment.setEnabled(True)

    def changed_microscope(self, microscope):
        """
        Change the microscope.

        Parameters
        ----------
        microscope : name of the microscope
            For the moment the following microscopes are accepted:
                1. Quattro.
                2. Versa.
                3. Vega.
                4. XL40-GB
                5. XL40-Cold
            If an invalid name is provided, the microscope is set back to Quattro

        Returns
        -------
        None.

        """
        log.info('Setting protocol parameters for microscope %s', microscope)
        self.microscope = microscope
        if microscope not in ['Quattro', 'Versa', 'Vega', 'XL40-GB', 'XL40-Cold']:
            self.microscope = 'Quattro'
            log.error('Microscope %s not yet implemented, reverting to default Quattro' % microscope)
            self.select_microscope_comboBox.setCurrentText('Quattro')
            self.microscope = 'Quattro'
        self.validate_inputs()

    @Slot(bool)
    def disable_inputs(self, set_disable: bool = True) -> None:
        """
        Disable the main window inputs.

        As soon as the watchdog is started, it is important to disable the
        input fields to avoid possible problems.

        Parameters
        ----------
        set_disable : bool, optional
            If set to False, the inputs will be enabled. The default is True.

        Returns
        -------
        None.

        """
        self.protocol_folder_text.setEnabled(not set_disable)
        self.select_protocol_folder.setEnabled(not set_disable)
        if self.is_mirroring_requested:
            self.mirroring_folder_text.setEnabled(not set_disable)
        if self.is_custom_ownership_requested:
            self.projectID_field.setEnabled(not set_disable)
            self.project_name_field.setEnabled(not set_disable)
            self.responsible_field.setEnabled(not set_disable)
        self.select_mirroring_folder.setEnabled(not set_disable)
        self.mirror_checkBox.setEnabled(not set_disable)
        self.select_microscope_comboBox.setEnabled(not set_disable)
        self.custom_ownership_checkbox.setEnabled(not set_disable)

    @Slot(bool)
    def toggled_mirroring(self, toggled):
        """
        Act upon a change in the mirror_checkBok.

        TODO: understand if we can remove the toggled argument, because it is not used.

        Parameters
        ----------
        toggled : bool
            the status.

        Returns
        -------
        None.

        """
        if self.mirror_checkBox.isChecked():
            self.is_mirroring_requested = True
        else:
            self.is_mirroring_requested = False
        self.validate_inputs()

    @Slot(bool)
    def toggled_custom_ownership(self, toggled):
        """
        Act upon a change in the custom_ownership_checkbox.

        TODO: understand if we can remove the toggled argument, because it is not used.

        Parameters
        ----------
        toggled : bool
            the status.

        Returns
        -------
        None.
        """
        if self.custom_ownership_checkbox.isChecked():
            self.is_custom_ownership_requested = True
        else:
            self.is_custom_ownership_requested = False
        self.validate_inputs()

    @Slot()
    def toggled_watchdog(self):
        """
        Emulate the behavior of a toggle button.

        The watchdog pushbutton has to work like a toggle switch.
        You press it once and the process starts, you press it again and
        it stops.

        We can perform also a facelift to the push button to change its
        text and the icon.

        Returns
        -------
        None.

        """
        # first change the status of the watchdog
        self.is_watchdog_running = not self.is_watchdog_running

        # update the pushbutton appearance
        self.watchdog_pushbutton_facelift()

    def open_browser(self):
        """
        Open a resource browser pointing to the monitored folder.

        Returns
        -------
        None.

        """
        command = f'explorer {str(self.protocol_folder_path)}'
        self.browser_process = subprocess.Popen(command.split())

    def open_protocol_webpage(self):
        """Open the protocol webpage using the default browser."""
        url = self.workers['SingleWatchdog'].autoprotocol_instance.get_protocol_url()
        webbrowser.open(url, new=0, autoraise=True)

    def open_yaml_editor(self):
        """
        Open the protocol editor.

        Returns
        -------
        None.

        """
        if not self.protocol_editor:
            self.protocol_editor = ProtocolEditor(parent=self,
                                                  autolog=self.workers['SingleWatchdog'].autoprotocol_instance)
            self.protocol_editor.execute_filesystem_command.connect(self.receive_filesystem_command)

        self.protocol_editor.scroll_to_last_selected_item()
        self.protocol_editor.show()
        self.protocol_editor.raise_()
        self.protocol_editor.activateWindow()

    @Slot(FileSystemCommand)
    def receive_filesystem_command(self, command: FileSystemCommand):
        patched_command = self.patch_command_path(command)
        self.file_system_commander.execute(patched_command)

    def patch_command_path(self, command: FileSystemCommand) -> FileSystemCommand:

        if command.input_path.is_absolute():
            log.warning('Unable to patch command path because it is absolute')
            log.warning('The command will be applied to the original path (%s)' % str(command.input_path))
            return command
        else:
            input_path = self.protocol_folder_path / command.input_path
            output_path = None if command.output_path is None else self.protocol_folder_path / command.output_path
            return FileSystemCommand(command.command, input_path, output_path)

    @Slot()
    def open_protocol_folder(self):
        """Open a file dialog for the protocol folder."""
        directory = self.protocol_folder_text.text()
        if not directory:
            directory = str(Path(autoconfig.DEFAULT_PROTOCOL_FOLDER))
        returnpath = QFileDialog.getExistingDirectory(
            self, 'Select a protocol folder', directory=directory)
        if returnpath:
            returnpath = Path(returnpath)
            self.protocol_folder_path = returnpath
            self.protocol_folder_text.setText(str(returnpath))
            self.validate_inputs()

    @Slot()
    def open_mirroring_folder(self):
        """Open a file dialog for the mirroring folder."""
        directory = self.mirroring_folder_text.text()
        if not directory:
            directory = str(Path(autoconfig.DEFAULT_MIRRORING_FOLDER))
        returnpath = QFileDialog.getExistingDirectory(self, 'Select a mirroring folder',
                                                      directory=directory)
        if returnpath:
            returnpath = Path(returnpath)
            self.mirroring_folder_path = returnpath
            self.mirroring_folder_text.setText(str(returnpath))
            self.validate_inputs()

    def _strip_spaces(self):
        line_edit_list = [self.protocol_folder_text,
                          self.mirroring_folder_text,
                          self.projectID_field,
                          self.project_name_field,
                          self.responsible_field]

        for line in line_edit_list:
            if line.isEnabled():
                line.setText(line.text().strip())

    def validate_inputs(self, force_validation: bool = False):  # noqa: C901
        """
        Validate all inputs.

        The input_folder can be local_path on the microscope PC or directly on the
        image server, while the mirroring_folder must be on the image server.

        We need to check that:
            1. The protocol folder is not Invalid. If Invalid just quit.
            2. If the mirroring switch is selected then:
                2.1 Check that the Mirroring folder is not Invalid
                2.2 If the custom ownership is requested:
                    2.2.1 Are the custom ownership fields ok?
                        2.2.1.1 If yes: The mirroring can be Acceptable or
                                AcceptableIfCustomOwnership
                        2.2.1.2 If No: The mirroring must be Acceptable
                2.3 If the custom ownership is not requested:
                    2.3.1 The mirroring must be Acceptable
            3. If the mirroring switch is not selected then:
                3.1 If the custom ownership is requested:
                    3.1.1 Are the custom ownership fields ok?
                        3.1.1.1 If yes: the protocol folder can be Acceptable or
                                AcceptableIfCustomOwnership
                        3.1.1.2 If no: the protocol folder must be Acceptable.
                3.2 If the custom ownership is not requested:
                    3.2.1 The protocol folder must be Acceptable

        Returns
        -------
        None.

        """
        present_gui_content = MainWindow.GUIContent.from_main_window(self)
        if not force_validation:
            if self.current_gui_content == present_gui_content:
                # nothing changed.
                # no need to continue, just confirm the actual status of the watchdog
                self.enable_watchdog(self.is_watchdog_enabled)
                return

        self.current_gui_content = present_gui_content

        if self.current_gui_content != self.last_loaded_gui_content:
            self.experiment_need_save = True
            if not self.windowTitle().endswith(self.title_modifier):
                self.setWindowTitle(f'{self.windowTitle()}{self.title_modifier}')
        else:
            self.experiment_need_save = False
            if self.windowTitle().endswith(self.title_modifier):
                self.setWindowTitle(self.windowTitle().rstrip(self.title_modifier))

        self._strip_spaces()

        protocol_folder = PathValidator(self.protocol_folder_text.text(),
                                        autoconfig.IMAGE_SERVER_BASE_PATH, self.pattern)
        protocol_folder_validity = protocol_folder.validate()
        protocol_ownership_variables = protocol_folder.get_ownership_parameters()

        mirroring_folder = PathValidator(self.mirroring_folder_text.text(),
                                         autoconfig.IMAGE_SERVER_BASE_PATH, self.pattern)
        mirroring_folder_validity = mirroring_folder.validate()
        mirroring_ownership_variables = mirroring_folder.get_ownership_parameters()

        custom_ownership_validity = self.projectID_field.text() and self.project_name_field.text() \
                                    and self.responsible_field.text()

        # Condition 1
        if protocol_folder_validity != PathValidator.Invalid:
            # transfer the field text to the variable
            self.protocol_folder_path = Path(self.protocol_folder_text.text())
        else:
            # check if the field text is not empty
            if self.protocol_folder_text.text():
                # print a warning message
                log.warning('Protocol input folder is invalid')
            self.enable_watchdog(False)
            # stop here, it doesn't make sense to continue
            return

        # Condition 2
        if self.is_mirroring_requested:
            # if we get here the protocol_folder_validity is for sure not Invalid

            # Condition 2.1
            if mirroring_folder_validity != PathValidator.Invalid:
                # the mirroring folder is either Acceptable, AccetableIfMirroring or
                # AcceptableIfCustomOwnership

                # Condition 2.2
                if self.is_custom_ownership_requested:

                    # Condition 2.2.1
                    if custom_ownership_validity:
                        self.projectID = self.projectID_field.text()
                        self.project_name = self.project_name_field.text()
                        self.project_responsible = self.responsible_field.text()

                        # Condition 2.2.1.1
                        if mirroring_folder_validity in (PathValidator.Acceptable,
                                                         PathValidator.AcceptableIfCustomOwnership):
                            # we are good to go
                            # transfer the field texts to the parameters and enable the
                            # watchdog
                            self.mirroring_folder_path = Path(self.mirroring_folder_text.text())
                            self.enable_watchdog(True and self.are_user_credentials_ok()
                                                 and self.is_elog_entry_editable(self.projectID)
                                                 )

                            if mirroring_folder_validity == PathValidator.Acceptable:
                                # inform the user that the custom ownership variables
                                # will be used
                                log.info('Custom parameters will be used (#=%s, Project=%s, Responsible=%s)' %
                                         (self.projectID, self.project_name, self.project_responsible))

                            return
                        else:
                            if mirroring_folder_validity == PathValidator.AcceptableIfCustomOwnership:
                                log.warning('Please specify all three custom parameters')
                            self.enable_watchdog(False)

                    else:
                        # the three ownership fields are empty
                        self.projectID = None
                        self.project_name = None
                        self.project_responsible = None

                        # Condition 2.2.1.2
                        if mirroring_folder_validity == PathValidator.Acceptable:

                            # we are good to go
                            # transfer the field texts to the parameters and enable the
                            # watchdog
                            self.mirroring_folder_path = Path(
                                self.mirroring_folder_text.text())
                            self.projectID_field.setText(
                                mirroring_ownership_variables[0])
                            self.project_name_field.setText(
                                mirroring_ownership_variables[1])
                            self.responsible_field.setText(
                                mirroring_ownership_variables[2])
                            self.enable_watchdog(
                                True and self.are_user_credentials_ok()
                                and self.is_elog_entry_editable(mirroring_ownership_variables[0]))

                            return

                        else:
                            log.warning(
                                'Please specify all three custom parameters')
                            self.enable_watchdog(False)
                            # stop here, it doesn't make sense to continue
                            return

                # Condition 2.3
                else:
                    self.projectID = None
                    self.project_name = None
                    self.project_responsible = None

                    # Condition 2.3.1
                    if mirroring_folder_validity == PathValidator.Acceptable:
                        # we are good to go
                        # transfer the field texts to the parameters and enable the
                        # watchdog
                        self.mirroring_folder_path = Path(
                            self.mirroring_folder_text.text())

                        self.projectID_field.setText(mirroring_ownership_variables[0])
                        self.project_name_field.setText(mirroring_ownership_variables[1])
                        self.responsible_field.setText(mirroring_ownership_variables[2])
                        self.enable_watchdog(True and self.are_user_credentials_ok()
                                             and self.is_elog_entry_editable(mirroring_ownership_variables[0]))
                        return

                    else:
                        if mirroring_folder_validity == PathValidator.AcceptableIfCustomOwnership:
                            log.warning('Please activate Use custom parameters')
                            log.warning('Please specify all three custom parameters')
                        else:
                            if self.mirroring_folder_text.text():
                                # print the error message only if the input field is
                                # not empty
                                log.error('Mirroring folder is invalid')
                        self.enable_watchdog(False)

            else:
                # the mirroring folder is Invalid.
                # check if the field text is not empty
                if self.mirroring_folder_text.text():
                    # print the error message only if the input field is
                    # not empty
                    log.error('Mirroring folder is invalid')
                self.enable_watchdog(False)

        # Condition 3
        # the mirroring is not requested.
        else:

            # Condition 3.1
            if self.is_custom_ownership_requested:

                # Condition 3.1.1
                if custom_ownership_validity:
                    self.projectID = self.projectID_field.text()
                    self.project_name = self.project_name_field.text()
                    self.project_responsible = self.responsible_field.text()

                    # Condition 3.1.1.1
                    if protocol_folder_validity in (PathValidator.Acceptable,
                                                    PathValidator.AcceptableIfCustomOwnership):
                        # we are good to go
                        # transfer the field texts to the parameters and enable the
                        # watchdog
                        self.protocol_folder_path = Path(self.protocol_folder_text.text())
                        self.enable_watchdog(True and self.are_user_credentials_ok()
                                             and self.is_elog_entry_editable(self.projectID))
                        return
                    else:
                        # all other cases should be already analyzed
                        log.warning('The protocol folder is valid only if mirroring is selected')
                        self.enable_watchdog(False)
                else:
                    # the three ownership fields are empty
                    self.projectID = None
                    self.project_name = None
                    self.project_responsible = None

                    # Condition 3.1.1.2
                    if protocol_folder_validity == PathValidator.Acceptable:
                        # we are good to go
                        # transfer the field texts to the parameters and enable the
                        # watchdog
                        self.protocol_folder_path = Path(
                            self.protocol_folder_text.text())
                        # display the ownership variables in the disable field
                        self.projectID_field.setText(
                            protocol_ownership_variables[0])
                        self.project_name_field.setText(
                            protocol_ownership_variables[1])
                        self.responsible_field.setText(
                            protocol_ownership_variables[2])
                        self.enable_watchdog(
                            True and self.are_user_credentials_ok()
                            and self.is_elog_entry_editable(protocol_ownership_variables[0]))
                        return
                    else:
                        # all other cases should be already analyzed
                        log.warning('The protocol folder is valid only if mirroring is selected')
                        if protocol_ownership_variables:
                            self.projectID_field.setText(
                                protocol_ownership_variables[0])
                            self.project_name_field.setText(
                                protocol_ownership_variables[1])
                            self.responsible_field.setText(
                                protocol_ownership_variables[2])
                        self.enable_watchdog(False)

            # Condition 3.2
            else:

                self.projectID = None
                self.project_name = None
                self.project_responsible = None

                # Condition 3.2.1
                if protocol_folder_validity == PathValidator.Acceptable:
                    # we are good to go
                    # transfer the field texts to the parameters and enable the
                    # watchdog
                    self.protocol_folder_path = Path(
                        self.protocol_folder_text.text())
                    # fill in the ownership field with the guessed values
                    self.projectID_field.setText(
                        protocol_ownership_variables[0])
                    self.project_name_field.setText(
                        protocol_ownership_variables[1])
                    self.responsible_field.setText(
                        protocol_ownership_variables[2])
                    self.enable_watchdog(
                        True and self.are_user_credentials_ok()
                        and self.is_elog_entry_editable(protocol_ownership_variables[0]))
                    return
                else:
                    # all other cases should be already analyzed
                    log.warning(
                        'The protocol folder is valid only if mirroring is selected')
                    if protocol_ownership_variables:
                        self.projectID_field.setText(
                            protocol_ownership_variables[0])
                        self.project_name_field.setText(
                            protocol_ownership_variables[1])
                        self.responsible_field.setText(
                            protocol_ownership_variables[2])
                    self.enable_watchdog(False)

    @retry(retry=retry_if_exception_type(LogbookServerTimeout),
           reraise=True, stop=stop_after_attempt(autoconfig.ELOG_TIMEOUT_MAX_RETRY),
           wait=wait_fixed(autoconfig.ELOG_TIMEOUT_WAIT),
           after=after_log(log, logging.WARNING))
    def is_elog_entry_editable(self, protocol_id):
        """
        Check if the entry with protocol_id is editable.

        This method is checking if there is an entry with Protocol ID exactly
        matching the protocol_id of the current protocol.

        If this is found, then it is checking if this is read-only. In this case
        the handle_readonly_entry function is called in order to give the
        possibility to the user to resolve the issue.

        Parameters
        ----------
        protocol_id : string
            The protocol ID of the current protocol. It is either guessed from
            the folder name or from the custom ownership method.

        Returns
        -------
        editable_flag : bool
            True if there are no entries with Protocol ID exactly matching the
            protocol_id.
            True if an entry with the exact matching Protocol ID is found and
            it is editable
            True if the user decided to override the read-only flag or to make
            a backup.
            False if the user decided to manually edit the protocol ID of the
            current experiment.

        """
        elog_instance = elog_handle_factory.get_logbook_handle(self.config[self.select_microscope_comboBox.currentText(
        )]['logbook'])

        real_ids = elog_instance.get_msg_ids(protocol_id)

        if len(real_ids):
            for msg_id in real_ids:
                message, attributes, attchments = elog_instance.read(msg_id)
                if attributes.get('Edit Lock', 'Unprotected') == 'Protected':
                    log.error('An entry with protocol ID %s already exists and it is read-only' % protocol_id)
                    # we need to ask the user how to recover this situation
                    return self.handle_readonly_entry(protocol_id, elog_instance, msg_id)
                else:
                    # the entry is not locked
                    return True
        # there are no entries with this number
        return True

    def handle_readonly_entry(self, protocol_id, elog_instance, msg_id):
        """
        Handle the case of a read only entry.

        This method is called by the is_elog_entry_editable to handle the
        user interaction as a response to the fact that the entry is read-only.

        It will open a dialog window explaining the problem and offering the
        three solutions:
            Overwrite: the edit-lock is switched off and the read-only entry is
                turned editable.

            Backup: the read-only entry is backed up in another entry with the same
                content but where the protocol number has been edited inserting
                a backup tag.

            Edit: the user has the possibility to modify the protocol number of
                the current entry hopefully not corresponding to another
                read-only entry.

        Parameters
        ----------
        protocol_id : string
            The protocol ID of the current protocol. It is either guessed from
            the folder name or from the custom ownership method.
        elog_instance : elog.Logbook
            The elog instance to be queried.
        msg_id : int
            The message ID of the read-only entry.

        Returns
        -------
        editable_flag : bool
            True if the user decides to override the read-only flag or to make
            a backup.
            False if the user decides to manually edit the protocol ID of the
            current experiment.

        """
        dialog = ReadOnlyEntryDialog(self)
        dialog.set_message(protocol_id)
        if dialog.exec_():
            if dialog.decision == ReadOnlyDecision.Overwrite:
                self.force_overwrite_readonly(elog_instance, msg_id)
                return True
            elif dialog.decision == ReadOnlyDecision.Backup:
                self.backup_readonly(elog_instance, msg_id)
                return True
            else:
                # ReadOnlyDecision.Edit
                log.warning('Manually change the protocol ID to a new value')
                self.manual_edit_protocol()
                return False
        else:
            # dialog cancel.
            log.warning(
                'Cancel dialog: manually change the protocol ID to a new value')
            self.manual_edit_protocol()
            return False

    @staticmethod
    def force_overwrite_readonly(elog_instance, msg_id):
        """
        Override the read-only flag of an entry.

        This method takes message msg_id from elog_instance and turns the
        read-only flag to Unprotected.

        Parameters
        ----------
        elog_instance : elog.Logbook
            The elog instance to be quiered.
        msg_id : int
            The message ID of the read-only entry.

        Returns
        -------
        None.

        """
        message, attributes, attachments = elog_instance.read(msg_id)
        attributes['Edit Lock'] = 'Unprotected'
        elog_instance.post(
            message, msg_id=msg_id, attributes=attributes, attachments=attachments, encoding='HTML',
            timeout=autoconfig.ELOG_TIMEOUT)
        log.info('Set protocol ID %s entry to editable' %
                 attributes['Protocol ID'])

    @staticmethod
    def backup_readonly(elog_instance, msg_id):
        """
        Execute a backup of a read-only entry.

        It takes from elog_instance the entry number msg_id and duplicate it
        renaming the ProtocolID by adding a timestamp.

        Parameters
        ----------
        elog_instance : elog.Logbook
            The elog instance to be quiered.
        msg_id : int
            The message ID of the read-only entry.

        Returns
        -------
        None.

        """
        message, attributes, attachments = elog_instance.read(msg_id)
        attributes['Protocol ID'] = f'{attributes["Protocol ID"]}-{datetime.now():%Y%m%d-%H%M%S} (backup)'
        elog_instance.post(
            message, msg_id, attributes=attributes, attachments=attachments, encoding='HTML',
            timeout=autoconfig.ELOG_TIMEOUT)
        log.info('Previous read-only entry renamed in %s' %
                 attributes['Protocol ID'])

    def manual_edit_protocol(self):
        """
        Allow manual editing of protocol ID.

        The user wants to preserve the existing entry as read-only and prefers
        to change the protocol ID number to a something different.

        To accomplish this, the custom ownership switch is turned on and the
        three custom ownership fields are enabled.

        Returns
        -------
        None.

        """
        self._sleep_input(True)
        self.custom_ownership_checkbox.setChecked(True)
        self.is_custom_ownership_requested = True
        wl = [self.projectID_field, self.project_name_field, self.responsible_field]
        for w in wl:
            w.setEnabled(True)
        self.projectID_field.setFocus()
        self._sleep_input(False)

    def are_user_credentials_ok(self):
        """
        Check whether the user credentials are ok.

        If the credentials were never checked before, perform a validity check
        trying to connect to the elog and download some numbers.

        If the check fails, the user is prompted with a dialog window to re-introduce
        the credentials. This occurs in a loop with a maximum number of repetition
        defined by the configuration variable max_auth_error.

        Returns
        -------
        bool
            The status of the user credentials.

        """
        if not self.are_user_credentials_checked:
            log.info('Verifying user credentials')

            for i in range(self.config.getint('elog', 'max_auth_error')):
                if self._are_user_credentials_ok():
                    log.info('User credentials are OK')
                    return True
                else:
                    self._edit_user_credentials()

            log.error('Wrong user name and password.')
            log.error('Use Settings/Change User credentials to correct the problem and continue.')
            return False
        else:
            self.are_user_credentials_checked = True
            log.info('User credentials are OK')
            return True

    @retry(retry=retry_if_exception_type(LogbookServerTimeout),
           reraise=True, stop=stop_after_attempt(autoconfig.ELOG_TIMEOUT_MAX_RETRY),
           wait=wait_fixed(autoconfig.ELOG_TIMEOUT_WAIT),
           after=after_log(log, logging.WARNING))
    def _are_user_credentials_ok(self):
        try:

            elog_instance = elog_handle_factory.get_logbook_handle(
                self.config[self.select_microscope_comboBox.currentText()]['logbook'])
            if not elog_instance.connection_verified:
                elog_instance.check_connection()
            return elog_instance.connection_verified
        except elog.LogbookAuthenticationError:
            log.warning('Authentication error, please review your username and password')
            return False

    def edit_user_credentials(self):
        """Open the user credentials dialog."""
        self._edit_user_credentials()
        self.are_user_credentials_ok()
        self.validate_inputs(force_validation=True)

    def _edit_user_credentials(self):
        dialog = UserEditor(self, username=self.config['elog']['elog_user'],
                            password=self.config['elog']['elog_password'])
        if dialog.exec_():
            self.config['elog']['elog_user'] = dialog.username
            self.config['elog']['elog_password'] = dialog.password
            autotools.init(self.config)
            self.are_user_credentials_checked = False

    def enable_watchdog(self, is_ok):
        """
        Make the watchdog able to start.

        This method is called after the input validation.

        Parameters
        ----------
        is_ok : BOOL
            If True, the watchdog is enabled and the relevant parameters are
            transferred to the Worker

        Returns
        -------
        None.

        """
        self.watchdog_pushbutton.setEnabled(is_ok)
        self.actionSta_rt_watchdog.setEnabled(is_ok)
        self.is_watchdog_enabled = is_ok
        self.actionSave_experiment.setEnabled(is_ok)

        params_to_be_sent = dict()
        if is_ok and not self.is_watchdog_running:
            params_to_be_sent['original_path'] = self.protocol_folder_path
            params_to_be_sent['is_mirroring_requested'] = self.mirror_checkBox.isChecked()
            if params_to_be_sent['is_mirroring_requested']:
                params_to_be_sent['destination_path'] = self.mirroring_folder_path
            else:
                params_to_be_sent['destination_path'] = self.protocol_folder_path
            params_to_be_sent['microscope'] = self.select_microscope_comboBox.currentText()
            params_to_be_sent['projectID'] = self.projectID
            params_to_be_sent['project_name'] = self.project_name
            params_to_be_sent['responsible'] = self.project_responsible

            # send all parameters to the worker
            self.workers['SingleWatchdog'].update_parameters(**params_to_be_sent)

            # inform the rest of the software about the new autoprotocol_instance
            self.change_autolog.emit(self.workers['SingleWatchdog'].autoprotocol_instance)

            log.info('Folder selection is ok. Ready to start the watchdog')

    @Slot()
    def clear_logger(self):
        """
        Clear the logger message box.

        This slot is called by the clear logger button clicked event

        Returns
        -------
        None.

        """
        self.log_message_box.clear()

    @Slot()
    def save_logger(self):
        """
        Save the content of the logger message box.

        The user has the possibility to save the content as a simple plain text
        or as a formatted HTML document, since the document is actually originally
        formatted as HTML.

        Returns
        -------
        None.

        """
        directory = Path.home() / Path('Documents')
        logger_file = QFileDialog.getSaveFileName(self, 'Logger file name',
                                                  filter='HTML file (*.html);;Text file (*.txt)',
                                                  directory=str(directory))
        if logger_file[0]:
            if logger_file[1] == 'HTML file (*.html)':
                text = str(self.log_message_box.document().toHtml())
            elif logger_file[1] == 'Text file (*.txt)':
                text = str(self.log_message_box.toPlainText())
            else:
                text = 'Wrong format'
            with open(Path(logger_file[0]), 'w') as lf:
                lf.write(text)

    def show_about(self):
        """
        Show the about dialog.

        Returns
        -------
        None.

        """
        dialog = AboutDialog(self)
        dialog.exec_()

    def load_experiment(self):
        """
        Load an experiment file.

        An experiment file is a modified version of a configuration file with a
        dedicated section to the GUI. In this way, all GUI fields are preset
        to the values stored in the file.

        After loading, the validate_inputs method is called so that if everything
        is ok, the Start Watchdog is enabled and all parameters are sent to the
        workers.

        Returns
        -------
        None.

        """
        if self.experiment_need_save:
            ans = QMessageBox.question(self, 'Save current experiment file',
                                       'Before loading a new experiment, would you like to save the current one?',
                                       buttons=QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Yes:
                self.save_experiment()
            elif ans == QMessageBox.No:
                pass
            else:  # ans = QMessageBox.Cancel
                return
        if self.experiment_filename:
            directory = Path(self.experiment_filename).parent
        else:
            directory = Path.home() / 'Documents'
        returnpath = QFileDialog.getOpenFileName(self, 'Open experiment file',
                                                 directory=str(directory),
                                                 filter='Experiments (*.exp)')
        if returnpath[0]:
            self._load_experiment(returnpath[0])
            self.experiment_filename = Path(returnpath[0])

    def _sleep_input(self, sleep):
        widget_list = [self.protocol_folder_text,
                       self.mirroring_folder_text,
                       self.mirror_checkBox,
                       self.select_microscope_comboBox,
                       self.custom_ownership_checkbox,
                       self.projectID_field,
                       self.project_name_field,
                       self.responsible_field
                       ]
        for widget in widget_list:
            widget.blockSignals(sleep)

    def _load_experiment(self, path):
        config = autotools.safe_configread(path)
        self.experiment_filename = str(path)
        self.config = config
        autotools.init(config)
        self._sleep_input(True)
        self.protocol_folder_text.setText(str(Path(config['GUI']['src_path'])))
        if config['GUI']['mirror_path']:
            self.mirroring_folder_text.setText(str(Path(config['GUI']['mirror_path'])))
        else:
            self.mirroring_folder_text.clear()
        self.mirror_checkBox.setChecked(config.getboolean('GUI', 'mirror'))
        self.is_mirroring_requested = self.mirror_checkBox.isChecked()
        self.mirroring_folder_text.setEnabled(self.mirror_checkBox.isChecked())
        self.select_microscope_comboBox.setCurrentText(config['GUI']['microscope'])
        self.custom_ownership_checkbox.setChecked(config.getboolean('GUI', 'custom_ownership', fallback=False))
        self.is_custom_ownership_requested = self.custom_ownership_checkbox.isChecked()
        self.projectID_field.setEnabled(self.custom_ownership_checkbox.isChecked())
        self.project_name_field.setEnabled(self.custom_ownership_checkbox.isChecked())
        self.responsible_field.setEnabled(self.custom_ownership_checkbox.isChecked())
        self.projectID_field.setText(config.get('GUI', 'projectID', fallback=''))
        self.project_name_field.setText(config.get('GUI', 'project_name', fallback=''))
        self.responsible_field.setText(config.get('GUI', 'responsible', fallback=''))
        log.info('Loaded experiment %s and updated configuration' % str(Path(path)))
        self.are_user_credentials_checked = False
        self.last_loaded_gui_content = MainWindow.GUIContent.from_main_window(self)
        self.validate_inputs(force_validation=True)

        self.watchdog_pushbutton.setFocus()
        self._sleep_input(False)
        self.experiment_need_save = False
        if self.windowTitle().endswith(self.title_modifier):
            self.setWindowTitle(self.windowTitle().rstrip(self.title_modifier))
        self.set_current_experiment_file(path)

    def set_current_experiment_file(self, path):
        if isinstance(path, Path):
            path = str(path)

        settings = QSettings('ecjrc', 'autologbook')
        files = settings.value('recent_file_list', [])

        try:
            files.remove(path)
        except ValueError:
            pass

        files.insert(0, path)
        del files[len(self.recent_file_actions):]

        settings.setValue('recent_file_list', files)
        self.update_recent_file_actions()

    def save_experiment(self):
        """
        Save the experiment file.

        An experiment file is a modified version of a configuration file with a
        dedicated section to the GUI. In this way, all GUI fields are preset
        to the values stored in the file.

        Returns
        -------
        None.

        """
        if self.experiment_filename:
            directory = self.experiment_filename
        else:
            directory = Path.home() / 'Documents'
            # let's try to see if from the protocol parameters we can build up the experiment filename. the three
            # protocol customization fields contain their values even if they are not active. we need to check if
            # they are not empty, because maybe the user is saving the file before having set the path.
            custom_projects_info = [self.projectID_field.text(), self.project_name_field.text(),
                                    self.responsible_field.text()]

            if all(custom_projects_info):
                filename = '-'.join(custom_projects_info) + '.exp'
                directory = directory / Path(filename)

        returnpath = QFileDialog.getSaveFileName(self, 'Save experiment file',
                                                 directory=str(directory), filter='Experiments (*.exp)')
        if returnpath[0]:
            self._save_experiment_file(returnpath[0])
            log.info('Experiment file save to %s' % str(Path(returnpath[0])))
            self.set_current_experiment_file(returnpath[0])
            self.experiment_filename = Path(returnpath[0])
            self.experiment_need_save = False
            if self.windowTitle().endswith(self.title_modifier):
                self.setWindowTitle(self.windowTitle().rstrip(self.title_modifier))

            self.update_remote_experiment_file()

    def _save_experiment_file(self, filename):
        self.current_gui_content.transfer_to_config(self.config)
        autotools.write_conffile(self.config, filename)

    def update_remote_experiment_file(self):

        elog_instance = elog_handle_factory.get_logbook_handle(autoconfig.PROTOCOL_LIST_LOGBOOK)
        # search if there is an entry with exactly this protocol id
        try:
            msg_id = elog_instance.get_msg_id(self.projectID_field.text())
            if msg_id:
                message, attributes, attachments = elog_instance.read(msg_id, timeout=autoconfig.ELOG_TIMEOUT)
                attachments = [str(self.experiment_filename), ]
                elog_instance.post(message, msg_id=msg_id, attributes=attributes, attachments=attachments,
                                   timeout=autoconfig.ELOG_TIMEOUT)
        except autoerror.ProtocolListError:
            log.warning('Problem with the microscopy protocol list')

    def check_threads_status(self):
        """
        Check the status of the various threads.

        When called, this method will check if the expected threads are alive or
        not and change the icon of a label in the GUI.
        """
        red_led = QtGui.QPixmap(":/resources/icons8-red-circle-48.png")
        green_led = QtGui.QPixmap(":/resources/icons8-green-circle-48.png")
        thread_names = [t.name for t in threading.enumerate()]
        thread_name_to_check = {'GUIThread': self.gui_thread_status,
                                'WatchThread': self.auto_thread_status,
                                'WatchThreadObs': self.auto_obs_status,
                                'WatchThreadEmi0': self.auto_emi_status}
        for name, label in thread_name_to_check.items():
            if name in thread_names:
                label.setPixmap(green_led)
            else:
                label.setPixmap(red_led)

    def hide_debug_elements(self, switch: bool):
        """
        Hide debug elements from the GUI.

        Parameters
        ----------
        switch: bool
            If True, the debug elements will be set hidden.
        """
        debug_elements = [self.gui_thread_status,
                          self.auto_thread_status,
                          self.auto_obs_status,
                          self.auto_emi_status,
                          self.GUIThreadLabel,
                          self.AutoThreadLabel
                          ]
        for element in debug_elements:
            element.setHidden(switch)


def override_credentials(args, config):
    """
    Override configuration file provided user credentials.

    If the user provides username and/or password from the command line,
    these have the priority over credentials stored in configuration files.

    **NOTE**
    Credentials saved in experiment files are **NOT** overridden!

    Parameters
    ----------
    args : namespace
        The namespace of command line arguments as obtained from the
        parse_arguments.
    config : dictionary
        The configuration dictionary as provided by the configuration parser.

    Returns
    -------
    None.

    """
    if args.username:
        config['elog']['elog_user'] = args.username
        # if username is provided, check if password is provided as well.
        # if no password is provided, set it to None so that the dialog window
        # will show up
        if args.password:
            config['elog']['elog_password'] = autotools.encrypt_pass(args.password)
        else:
            config['elog']['elog_password'] = ''
    else:
        # this is strange but possible: the user just wants to override the password,
        # but not the username.
        if args.password:
            config['elog']['elog_password'] = autotools.encrypt_pass(args.password)


def main_gui(args):
    """
    Open the main window and start the Qt Event loop.

    Parameters
    ----------
    args : system arguments
        The system arguments can be provided when starting the app.

    Returns
    -------
    None.

    """
    # give a name at the main thread
    threading.current_thread().name = 'GUIThread'

    # prepare the logging machinery
    loglevel = autoconfig.LEVELS.get(args.loglevel.lower())
    log.setLevel(level=loglevel)

    # check if the specified configuration file exists and loaded
    if not args.conffile.exists():
        # it looks like that the specified configuration file doesn't exist,
        # so we need to create one
        autotools.write_default_conffile(args.conffile)
    config = autotools.safe_configread(args.conffile)

    # if user provided username and password from the command line,
    # they must override the configuration file ones.
    override_credentials(args, config)

    # configure the whole package
    autotools.init(config)

    # start the Qt App
    if args.noapp:
        app = QApplication.instance()
    else:
        app = QApplication(sys.argv)
    win = MainWindow(app, config)

    # if the user preloaded an experiment file, then do it here
    if args.expfile:
        try:
            win._load_experiment(args.expfile)
            # if the user wants to start the watchdog right away,
            # do it, but before check that it is ok to do it.
            if win.is_watchdog_enabled and args.autoexec:
                timer = QtCore.QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(win.watchdog_pushbutton.clicked.emit)
                timer.start(100)
        except elog.LogbookServerProblem as err:
            log.critical('Logbook server problem')
            log.exception(err)
        except elog.LogbookAuthenticationError:
            log.error('Wrong user name and password.')
            log.error(
                'Use Settings/Change User credentials to correct the problem and continue.')

    # show the main window
    win.show(loglevel=loglevel)
    if args.noapp and args.autoexec and win.is_watchdog_enabled:
        win.watchdog_pushbutton.clicked.emit()

    # execute the main window and eventually exit when done!
    if not args.noapp:
        sys.exit(app.exec())


def main():
    parser = autotools.main_parser()
    parser.prog = 'autologbook-gui'
    args = parser.parse_args(sys.argv[1:])

    # to set the icon on the window task bar
    myappid = u'ecjrc.autologook.gui.v0.0.1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    main_gui(args)
