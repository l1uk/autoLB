# -*- coding: utf-8 -*-
"""Module to implement simple file system command"""
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
from enum import Enum, auto
import logging
from pathlib import Path
import shutil

from PyQt5.QtCore import QObject

log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class FSCommandType(Enum):
    """ All supported FS commands """

    DELETE_FILE = auto()
    DELETE_DIR = auto()
    RENAME_FILE = auto()
    RENAME_DIR = auto()
    MOVE_FILE = auto()


class FileSystemCommand:
    """
    A simple file system command.

    This class represents the basic implementation of a filesystem command, and it is part of the infrastructure to
    modify a protocol. In normal situation the user adds and removes protocol elements in an independent way, just by
    saving a new image in a sample folder. But similarly, one can decide to remove, rename or move an element while
    editing the protocol from the protocol editor.

    When (s)he does so a FileSystemCommand is generated and dispatched to a file system command that is taking care of
    executing the command.

    In other words, when the user asks for the removal of a picture from the ProtocolEditor, a delete file command is
    generated and processed. As a result, the watchdog is reacting to a file removal (including removing the mirror copy
    if any) and the corresponding element is removed from the protocol.
    """

    def __init__(self, command: FSCommandType, input_path: Path | str, output_path: Path | str = None):
        """
        Initialize a file system command.

        The simple file system commands already implemented are operating on one, maximum two paths.
        Those must be provided during the instance initialization.

        Parameters
        ----------
        command: FSCommandType
            enumerator with all existing and implemented file system commands.
        input_path: Path | str
            the input path on which the command is acting. The parameter is stored in the class member as a Path object.
        output_path: Path | str
            the output path on which the command is acting. The parameter is stored in the class member as a Path
            object.
        """
        if not isinstance(command, FSCommandType):
            log.error('Unable to process filesystem command. Command %s not available' % command)
            return
        self.command = command
        self.input_path = Path(input_path)
        self.output_path = None if output_path is None else Path(output_path)

    def __str__(self):
        """
        Represent the command as a string.

        Returns
        -------
        The string representation of the class.
        """
        if self.output_path is None:
            return f'Processing {self.command} on {self.input_path}'
        else:
            return f'Processing {self.command} from {self.input_path} to {self.output_path}'


class FileSystemCommander(QObject):
    def __init__(self):
        super().__init__()

    def execute(self, command: FileSystemCommand):
        self.on_any_command(command)
        {
            FSCommandType.DELETE_FILE: self.on_delete_file,
            FSCommandType.DELETE_DIR: self.on_delete_dir,
            FSCommandType.RENAME_FILE: self.on_rename_file,
            FSCommandType.RENAME_DIR: self.on_rename_dir,
            FSCommandType.MOVE_FILE: self.on_move_file,
        }[command.command](command)

    @staticmethod
    def on_any_command(command):
        # log.vipdebug(str(command))
        pass

    @staticmethod
    def on_rename_file(command):
        try:
            command.input_path.rename(command.output_path)
        except FileExistsError:
            log.error('A file with name %s already exists. Delete this first!' % command.input_path.name)

    @staticmethod
    def on_rename_dir(command):
        try:
            command.input_path.rename(command.output_path)
        except FileExistsError:
            log.error('A directory with name %s already exists. Delete this first!' % command.input_path.name)

    @staticmethod
    def on_delete_file(command):
        command.input_path.unlink()
        log.info('Removed file %s' % str(command.input_path))

    @staticmethod
    def on_delete_dir(command):
        shutil.rmtree(command.input_path, ignore_errors=True)
        log.info('Removed directory %s' % str(command.input_path))

    @staticmethod
    def on_move_file(command):
        # be sure that the destination folder exists.
        command.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            command.input_path.rename(command.output_path)
        except FileExistsError:
            log.error('A file with name %s already exists. Delete this first!' % command.input_path.name)
