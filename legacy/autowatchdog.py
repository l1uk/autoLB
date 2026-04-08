# -*- coding: utf-8 -*-
"""
Created on Tue Jun 28 10:33:35 2022

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
import filecmp
import logging
import math
import os
import pickle
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import piexif
import PIL
import watchdog.events
import watchdog.observers
from tenacity import (
    RetryError,
    Retrying,
    after_log,
    before_sleep_log,
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_fixed,
    wait_incrementing,
)

from autologbook import autoconfig, autoerror, autotools
from autologbook.attachment import attachment_factory
from autologbook.autoprotocol import Protocol
from autologbook.file_type_guesser import ElementTypeGuesser, regexp_repository
from autologbook.protocol_editor_models import ElementType
from autologbook.microscope_picture import VegaJPEGPicture, microscope_picture_factory
from autologbook.optical_image import optical_image_factory
from autologbook.sample import Sample
from autologbook.video import Video

log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class ModRegexMatchingEventHandler(watchdog.events.FileSystemEventHandler):
    """
    Matches given regexes with file paths associated with occurring events.
    """

    def __init__(self, regexes=None, ignore_regexes=None,
                 ignore_directories=False, case_sensitive=False):
        super().__init__()

        if regexes is None:
            regexes = [r".*"]
        elif isinstance(regexes, str):
            regexes = [regexes]
        if ignore_regexes is None:
            ignore_regexes = []
        if case_sensitive:
            self._regexes = [re.compile(r) for r in regexes]
            self._ignore_regexes = [re.compile(r) for r in ignore_regexes]
        else:
            self._regexes = [re.compile(r, re.I) for r in regexes]
            self._ignore_regexes = [re.compile(r, re.I) for r in ignore_regexes]
        self._ignore_directories = ignore_directories
        self._case_sensitive = case_sensitive

    @property
    def regexes(self):
        """
        (Read-only)
        Regexes to allow matching event paths.
        """
        return self._regexes

    @property
    def ignore_regexes(self):
        """
        (Read-only)
        Regexes to ignore matching event paths.
        """
        return self._ignore_regexes

    @property
    def ignore_directories(self):
        """
        (Read-only)
        ``True`` if directories should be ignored; ``False`` otherwise.
        """
        return self._ignore_directories

    @property
    def case_sensitive(self):
        """
        (Read-only)
        ``True`` if path names should be matched sensitive to case; ``False``
        otherwise.
        """
        return self._case_sensitive

    def dispatch(self, event):
        """Dispatches events to the appropriate methods.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`FileSystemEvent`
        """
        if self.ignore_directories and event.is_directory:
            return

        paths = []
        if hasattr(event, 'dest_path'):
            paths.append(os.fsdecode(event.dest_path))
        if event.src_path:
            paths.append(os.fsdecode(event.src_path))

        if any(r.match(p) for r in self.ignore_regexes for p in paths):
            # if the event is a movefile and the destination is an interesting file, then we have to dispatch it
            # otherwise, just stop here
            if hasattr(event, 'dest_path'):
                if any(r.match(os.fsdecode(event.dest_path)) for r in self.regexes):
                    super().dispatch(event)
                    return
            else:
                return

        if any(r.match(p) for r in self.regexes for p in paths) or any(Path(p).is_dir() for p in paths):
            super().dispatch(event)


class MirrorEventHandler(ModRegexMatchingEventHandler):
    """
    The mirror event handler class.

    This class has the task to deliver and process file system events occurring in the monitored directory in order to
    mirror its content on the destination path.

    Its constructor takes indeed two paths, the origin path and the destination one where the file system has to be
    mirrored.

    This event handler can be used as standalone for mirroring purposes, or it can be used as a class member in other
    event handlers to extend the capability of such event handler to mirroring.

    """

    def __init__(self, original_path: str | Path, destination_path: str | Path, **kwargs):
        """
        Dunder init method.

        Parameters
        ----------
        original_path: str | Path
            The origin path of the mirroring handler. This folder is corresponding to the directory being monitored
            by the watchdog observer.

        destination_path: str | Path
            The destination directory where the original path must be mirrored.

        kwargs: Any
            Keywords parameters. No other parameters are used, but this generic is here so that the same parameter
            dictionary of the extended handler can be passed.

        """
        regexes = regexp_repository.get_all_matching()
        ignore_regexes = regexp_repository.get_exclude('GENERIC')

        super().__init__(regexes=regexes, ignore_regexes=ignore_regexes, case_sensitive=False, ignore_directories=False)

        # original path
        self.original_path = original_path

        # destination path
        self.destination_path = destination_path

        # a copy of the previous event. This is to avoid to dispatch and process duplicated events.
        self.previous_event = None

    def dispatch(self, event):
        """
        Overload the dispatch method.

        This overload if recording the last dispatched event and avoid the dispatchment of the modified event
        just after the creation event.

        TODO: check that in normal operation (image generated by the microscope software) only one modified event
        is generated after the creation. If more than one event is generated, then we need to filter out all of them.

        Parameters
        ----------
        event:
            The file system event to be dispatched.
        """

        if self.previous_event is None:
            super().dispatch(event)
        else:
            old_key = self.previous_event.key
            new_key = event.key
            if old_key[1:] == new_key[1:] and old_key[0] == watchdog.events.EVENT_TYPE_CREATED \
                    and new_key[0] == watchdog.events.EVENT_TYPE_MODIFIED:
                # the two events are one after the other and the second one is just a
                # file modification of the first one.
                # then we don't dispatch the event, but we have to patch the event with the mirror_path.
                log.debug('Modified event not dispatched!')
                self.patch_event(event)

            else:
                super().dispatch(event)

        self.previous_event = event

    def patch_event(self, event):
        event.mirror_path = self.actual_dest(event.src_path)
        if event.event_type == watchdog.events.EVENT_TYPE_MOVED:
            event.mirror_path_2 = self.actual_dest(event.dest_path)

    def on_any_event(self, event):
        """
        React on every event just before dispatching.

        Add the mirror_path attribute to the event and let the event be further dispatched.

        """
        self.patch_event(event)

    def on_created(self, event: watchdog.events.FileSystemEvent):
        """React to a file or directory creation"""
        log.debug('Mirror event %s, event %s' % (event.event_type, str(event.key)))
        try:
            self.process_on_created(event)
        except OSError as e:
            log.error('Error copying file %s to %s, skipping it.' %
                      (event.src_path, event.mirror_path))
            log.exception(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def on_deleted(self, event):
        """React to a file or directory removal"""
        log.debug('mirror event %s, event %s' % (event.event_type, str(event.key)))
        try:
            self.process_on_deleted(event)
        except FileNotFoundError as e:
            log.error('Error removing file %s' % event.mirror_path)
            log.error('Was the file already removed?')
            log.exception(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def on_modified(self, event):
        """React to a file modification"""
        if event.event_type != watchdog.events.EVENT_TYPE_MODIFIED and not event.directory:
            log.debug('mirror event %s, event %s' % (event.event_type, str(event.key)))
        try:
            self.process_on_modified(event)
        except OSError as e:
            log.error('Error copying file %s to %s, skipping it.' %
                      (event.src_path, event.mirror_path))
            log.exception(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def on_moved(self, event):
        """React to a file or directory move / rename"""
        log.debug('mirror event %s, event %s' % (event.event_type, str(event.key)))
        try:
            self.process_on_moved(event)
        except (PermissionError, FileExistsError) as e:
            log.error('Permission error while renaming %s in %s' %
                      (event.dest_path, event.mirror_path))
            log.exception(e, exc_info=True)
        except FileNotFoundError as e:
            log.error('File %s not found' % event.dest_path)
            log.exception(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def get_extra_path(self, actual_path: Path | str) -> Path:
        """
        Calculate the extra path with respect to the root path.

        In normal circumstances the root path is either the so-called original path. But, there is only one specific
        case in which this is the destination_path:

        - During the preprocessing of existing files, one image failed to open and the ForceRemirroring is raised.
        - Then, and only in this specific case, the actual path is referred to the destination path.

        In order to handle this specificity, the actual path is checked against both the original and the destination
        path. Only in one case it can return an extra_path! So we will start from the original path that is by far
        the most likely, if it successful then, we go ahead, otherwise we check also the destination path. If both
        are failing (it should not happen) then an empty string is returned and the file is mirrored in the root folder.

        Parameters
        ----------
        actual_path : path
            The actual path.

        Returns
        -------
        extra_path : path
            The extra path of actual_path relative to the src_path.

        """
        if not isinstance(actual_path, Path):
            actual_path = Path(actual_path)

        for path in [self.original_path, self.destination_path]:
            try:
                # in normal circumstances, the actual path will be referring to the original path, but when doing
                # preprocessing of existing elements and mirroring is activated, then the actual_path is relative to
                # the destination path.
                extra_path = actual_path.relative_to(path)
            except ValueError:
                # log.exception(ValueError)
                extra_path = None
            if extra_path:
                break

        if extra_path is None:
            log.warning('Error in finding the relative path of %s, mirroring may fail' % actual_path)
            extra_path = ''

        return extra_path

    def actual_dest(self, actual_src: Path | str) -> Path:
        """
        Calculate the resource destination.

        Parameters
        ----------
        actual_src : path
            Source path of a resource.

        Returns
        -------
        actual_dest : path
            The destination path calculated from the actual_src.

        """
        if not isinstance(actual_src, Path):
            actual_src = Path(actual_src)
        return Path(self.destination_path) / self.get_extra_path(actual_src)

    @retry(reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS),
           wait=wait_fixed(autoconfig.AUTOLOGBOOK_MIRRORING_WAIT),
           after=after_log(log, logging.WARNING))
    def process_on_created(self, event: watchdog.events.FileSystemEvent):
        """
        Process a creation event.

        If the event is corresponding to a directory, then a directory with the same name and same parents is created
        in the destination folder.

        If the event is corresponding to a file, then it will be passed on to the process_on_modified method.

        This method is decorated with retry, so that in case of problems it will be executed again.

        Parameters
        ----------
        event:
            The file system event being processed.

        """
        if event.is_directory:
            # if it is a directory, make it on the destination
            actual_dest_path = Path(self.actual_dest(event.src_path))
            actual_dest_path.mkdir(parents=True, exist_ok=True)
            log.info('Created directory %s' % event.mirror_path)
        else:
            self.process_on_modified(event)

    @retry(reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS),
           wait=wait_fixed(autoconfig.AUTOLOGBOOK_MIRRORING_WAIT),
           after=after_log(log, logging.WARNING))
    def process_on_deleted(self, event: watchdog.events):
        """
        Process a deletion event.

        If the event is corresponding to a directory, the corresponding folder in the destination folder is removed
        using the shutil.rmtree with ignore_errors=True.

        If the event is corresponding to a file, the corresponding file in the destination folder is unlinked without
        complaining if it is already not existing.

        This method is decorated with retry, so that in case of problems it will be executed again.

        Parameters
        ----------
        event:
            The file system event to be processed.

        """
        if event.mirror_path.is_file():
            event.mirror_path.unlink(missing_ok=True)
            log.info('Deleted file %s' % event.mirror_path)
        elif event.is_directory:
            shutil.rmtree(event.mirror_path, ignore_errors=True)
            log.info('Deleted directory %s' % event.mirror_path)

    @retry(reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS),
           wait=wait_fixed(autoconfig.AUTOLOGBOOK_MIRRORING_WAIT),
           after=after_log(log, logging.WARNING))
    def process_on_modified(self, event: watchdog.events):
        """
        Process a modification event.

        A modification event is emitted by the observer whenever a file is changed or the content of a directory is
        changed.

        If the case of a directory, this event is actually not processed because there is nothing to do.

        In case of a file, then it copied again to the destination.

        This method is decorated with retry, so that in case of problems it will be executed again.

        Parameters
        ----------
        event:
            The filesystem event to be processed.

        """
        if event.is_directory:
            # this occurs every time a file in a directory is modified
            # do not do anything and simply return
            return
        else:
            # if it is a file, we copy it again
            # be sure that the file is closed
            self.wait_until_file_is_closed(event.src_path)

            # start the copy procedure stabilized with tenacity.
            # we copy the file and check if the mirror and the local one are byte-to-byte equal.
            # otherwise make another copy attempt.
            mirror_check = False

            if mirror_check:
                max_attempts = 5
                wait_interval = 3
                try:
                    for attempt in Retrying(stop=stop_after_attempt(max_attempts), wait=wait_fixed(wait_interval),
                                            retry=retry_if_not_exception_type(
                                                autoerror.MirroredFileDifferFromOriginal)):
                        with attempt:
                            shutil.copy2(event.src_path, event.mirror_path)
                            self.wait_until_file_is_closed(event.mirror_path)
                            if not filecmp.cmp(event.src_path, event.mirror_path, shallow=False):
                                msg = f'Mirrored file {Path(event.mirror_path).name} is different from the original one. ' \
                                      f'Recopy it.'
                                log.warning(msg)
                                raise autoerror.MirroredFileDifferFromOriginal(msg)
                except RetryError:
                    msg = f'Unable to copy {event.src_path} to {event.mirror_path}'
                    log.error(msg)
                    raise autoerror.WatchdogError(msg)
            else:
                shutil.copy2(event.src_path, event.mirror_path)

            log.info('Mirrored file %s to %s' % (event.src_path, event.mirror_path))

    @retry(reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_MIRRORING_MAX_ATTEMPTS),
           wait=wait_fixed(autoconfig.AUTOLOGBOOK_MIRRORING_WAIT),
           after=after_log(log, logging.WARNING))
    def process_on_moved(self, event):
        """
        Process a moved event.

        A moved event is emitted when the location of a file or directory is changed or when it is renamed.
        In the case of a directory, also all move events corresponding to the contained files will be emitted.

        Every moved event will be treated as a copy event followed by a delete event.

        This method is decorated with retry, so that in case of problems it will be executed again.

        Parameters
        ----------
        event:
            The file system event to be processed.

        """

        original_dest_path = event.dest_path
        actual_dest_path = self.actual_dest(original_dest_path)
        if Path(original_dest_path).is_dir():
            # this case should never happen... but in case
            actual_dest_path.mkdir(parents=True, exist_ok=True)
        else:
            self.wait_until_file_is_closed(event.dest_path)
            if not os.path.exists(actual_dest_path):
                actual_dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original_dest_path, actual_dest_path)
                log.info('Mirrored %s to %s' %
                         (str(original_dest_path), str(actual_dest_path)))

        actual_dest_path = self.actual_dest(event.src_path)
        if actual_dest_path.is_file():
            actual_dest_path.unlink(missing_ok=True)
        else:
            shutil.rmtree(actual_dest_path, ignore_errors=True)
        log.info("Removed %s" % actual_dest_path)

    def process_all_existing(self):
        """
        Process all existing files / directories.

        This method is called just before the observer is started so that all already present files/directories are
        processed.

        """
        all_mirrored_files = self.destination_path.glob('**/*')
        log.info('Mirroring all existing items in %s' % self.original_path)
        for file in self.original_path.glob('**/*'):
            actual_dest = self.actual_dest(file)
            if actual_dest not in all_mirrored_files:
                if file.is_dir():
                    actual_dest.mkdir(parents=True, exist_ok=True)
                else:
                    if not actual_dest.exists():
                        actual_dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, actual_dest)
                        log.info('Mirrored %s to %s' % (str(file), str(actual_dest)))

    @staticmethod
    def wait_until_file_is_closed(file_path: Path):
        """
        Wait until the copy of the file in the event is finished.

        This method is monitoring the size of the newly added file. If it keeps
        on changing it means that is still being copied.

        The size of the file is polled with an adaptive delay. Very fast at the
        beginning and more slowly later on. The maximum polling delay is 1 sec.
        Normally only 1 interaction is necessary for a standard size TIFF file
        corresponding to a delay of 0.06s.

        Parameters
        ----------
        file_path : Path
            This is the file being transferred.

        Returns
        -------
        None.

        """

        old_size = -1
        i = 0.
        while old_size != Path(file_path).stat().st_size:
            old_size = Path(file_path).stat().st_size
            delay = 2 / math.pi * math.atan(i / 6 + 0.1)
            i += 1
            time.sleep(delay)


class ProtocolEventHandler(ModRegexMatchingEventHandler):
    """
    The base implementation of the protocol event handler.

    For each microscope a specific subclass of this class is envisaged.

    It includes a mirroring event handler that can be activated.
    When mirroring is requested, every filesystem event will be dispatched to the mirroring handler first and then
    to the protocol handler.

    """

    def __init__(self, autoprotocol_instance, **kwargs):

        self.matching_patterns = regexp_repository.get_all_matching()

        # We have to exclude whatever was excluded by the mirroring event handler. This means only the GENERIC
        # exclude patterns that are temporary files.
        self.excluded_patterns = regexp_repository.get_exclude('GENERIC')
        # set the protocol instance
        self.autoprotocol_instance = autoprotocol_instance

        # set the queue reference
        self.queue = None

        # a copy of the previous event. This is to avoid to dispatch and process duplicated events.
        self.previous_event = None

        # prepare a set of dictionaries. all these dictionaries are filled by the add_element_type method.
        # be careful that item order is important!!!
        #
        # the type guessers will contain all type guesser used to discriminate the various file types.
        self.type_guessers = {}
        # the following three dictionaries will distribute event to specific methods depending on the typ
        self.creation_distributor = {}
        self.modification_distributor = {}
        self.deletion_distributor = {}

        self.prepare_element_types()

        required_arguments = [
            'original_path',  # the path to be monitored
            'destination_path',  # this is where the mirroring component has to copy the files
            'is_mirroring_requested',  # a flag to specify whether the mirroring is required or not
            'microscope',  # this is the microscope type
            'projectID',  # this is the project ID aka protocol number
            'project_name',  # this is the project name
            'responsible'  # this is the project responsible
        ]
        self.params = dict()
        for param in required_arguments:
            if param in kwargs:
                self.params[param] = kwargs[param]
            else:
                log.error('Missing %s. Cannot update worker parameters' % param)
                raise autoerror.MissingWorkerParameter(f'Missing {param}.')

        # this parameter contains a timestamp referring to the time when the
        # elog was updated. we initialize to one hour ago.
        self.last_update = datetime.fromtimestamp(datetime.now().timestamp() - 3600)

        super().__init__(regexes=self.matching_patterns, ignore_directories=True, case_sensitive=False,
                         ignore_regexes=self.excluded_patterns)

        # prepare a mirroring event handler
        self.mirror_maker = MirrorEventHandler(parent=self, **self.params)

        # prepare a flag to store the status of the logbook changes
        self.logbook_changed = False

        # prepare a flag to store the intention of the user to skip elog updates
        self.skip_elog_update = False

        # designate a class for the microscope image
        # for the ProtocolEventHandler this is None, but it must be defined for all its subclass
        self.microscope_picture_class = None

    def add_element_type(self, element_type: autotools.ElementType,
                         creation_slot: Callable[[watchdog.events.FileSystemEvent], None],
                         deletion_slot: Callable[[watchdog.events.FileSystemEvent], None],
                         modification_slot: Callable[[watchdog.events.FileSystemEvent], None],
                         regexp_matching_pattern: str | re.Pattern | list[str],
                         regexp_exclude_pattern: str | re.Pattern | list[str] | None = None):

        self.creation_distributor[element_type] = creation_slot
        self.deletion_distributor[element_type] = deletion_slot
        self.modification_distributor[element_type] = modification_slot

        type_guesser = ElementTypeGuesser(regexp_matching_pattern, regexp_exclude_pattern)
        self.type_guessers[str(element_type)] = (type_guesser, element_type)

    def modify_element_type(self, element_type: autotools.ElementType,
                            creation_slot: Callable[[watchdog.events.FileSystemEvent], None],
                            deletion_slot: Callable[[watchdog.events.FileSystemEvent], None],
                            modification_slot: Callable[[watchdog.events.FileSystemEvent], None],
                            regexp_matching_pattern: str | re.Pattern | list[str],
                            regexp_exclude_pattern: str | re.Pattern | list[str] | None = None):

        if not (element_type in self.creation_distributor.keys() and element_type in self.deletion_distributor.keys()
                and element_type in self.deletion_distributor.keys() and str(
                    element_type) in self.type_guessers.keys()):
            log.warning('Attempt to modify an element type not defined for this protocol')
            return

        self.creation_distributor[element_type] = creation_slot
        self.deletion_distributor[element_type] = deletion_slot
        self.modification_distributor[element_type] = modification_slot
        type_guesser = ElementTypeGuesser(regexp_matching_pattern, regexp_exclude_pattern)
        self.type_guessers[str(element_type)] = (type_guesser, element_type)

    def remove_element_type(self, element_type: autotools.ElementType):
        if not (element_type in self.creation_distributor.keys() and element_type in self.deletion_distributor.keys()
                and element_type in self.deletion_distributor.keys() and str(
                    element_type) in self.type_guessers.keys()):
            log.warning('Attempt to remove an element type not defined for this protocol')
            return

        del self.type_guessers[str(element_type)]
        del self.creation_distributor[element_type]
        del self.modification_distributor[element_type]
        del self.deletion_distributor[element_type]

    def reset_all_element_types(self):
        self.type_guessers.clear()
        self.creation_distributor.clear()
        self.modification_distributor.clear()
        self.deletion_distributor.clear()

    def prepare_element_types(self):
        # 1. Microscope picture. This must be before the optical picture to avoid conflicts in protocol event
        #    handlers like VEGA where jpg files can be microscope picture and also optical picture.
        self.add_element_type(
            element_type=ElementType.MICROSCOPE_PIC,
            creation_slot=self.create_microscope_picture,
            modification_slot=self.modify_microscope_picture,
            deletion_slot=self.delete_microscope_picture,
            regexp_matching_pattern=regexp_repository.get_matching('IMAGEFILE'),
            regexp_exclude_pattern=regexp_repository.get_exclude('IMAGEFILE')
        )

        # 2. Optical image
        self.add_element_type(
            element_type=ElementType.OPTICAL_PIC,
            creation_slot=self.create_optical_image,
            modification_slot=self.modify_optical_image,
            deletion_slot=self.delete_optical_image,
            regexp_matching_pattern=regexp_repository.get_matching('OPTICAL_IMAGE'),
            regexp_exclude_pattern=regexp_repository.get_exclude('OPTICAL_IMAGE')
        )

        # 3. Attachment file (order not relevant)
        self.add_element_type(
            element_type=ElementType.ATTACHMENT_FILE,
            creation_slot=self.create_attachment_file,
            modification_slot=self.modify_attachment_file,
            deletion_slot=self.delete_attachment_file,
            regexp_matching_pattern=regexp_repository.get_matching('ATTACHMENT'),
            regexp_exclude_pattern=regexp_repository.get_exclude('ATTACHMENT')
        )

        # 4. YAML file (order not relevant)
        self.add_element_type(
            element_type=ElementType.YAML_FILE,
            creation_slot=self.create_yaml_file,
            modification_slot=self.modify_yaml_file,
            deletion_slot=self.delete_yaml_file,
            regexp_matching_pattern=regexp_repository.get_matching('YAMLFILE'),
            regexp_exclude_pattern=regexp_repository.get_exclude('YAMLFILE')
        )

        # 5. Video file (order not relevant)
        self.add_element_type(
            element_type=ElementType.VIDEO_FILE,
            creation_slot=self.create_video_file,
            modification_slot=self.modify_video_file,
            deletion_slot=self.delete_video_file,
            regexp_matching_pattern=regexp_repository.get_matching('VIDEO'),
            regexp_exclude_pattern=regexp_repository.get_exclude('VIDEO')
        )

    @retry(retry=retry_if_not_exception_type(autoerror.ReadOnlyEntry),
           reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS),
           wait=wait_incrementing(autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT,
                                  autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MIN,
                                  autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MAX),
           before_sleep=before_sleep_log(log, logging.WARNING, True),
           after=after_log(log, logging.WARNING))
    def process_on_created(self, event: watchdog.events.FileSystemEvent):
        """
        Stub of the process on created method. To be overloaded.

        Parameters
        ----------
        event: watchdog.events.FileSystemEvent
            Filesystem event to be processed.
        """
        # be sure that the copy is finished.
        self.wait_until_file_is_closed(event)

        # reset the logbook changed flag
        self.logbook_changed = False

        # what has been created?
        element_type = self.guess_element_type(event.mirror_path)

        # element_type can also be None, if no ElementTypeGuesser was returning with a positive answer.
        # in this case we don't dispatch the process any further.
        if element_type:
            # the guess for an element type was successful. Process the event by
            # dispatching it to the responsible slot.
            self.creation_distributor[element_type](event)

        if self.logbook_changed and not self.skip_elog_update:
            self.update_logbook(skip_attachments=True)

    def create_attachment_file(self, event: watchdog.events.FileSystemEvent):

        # check and eventually add parents samples.
        self.check_and_add_parents(event.mirror_path)
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:  # the attachment is inside a sample folder
            self.autoprotocol_instance.samples[sample_full_name].add_attachment(
                attachment_factory.create_object(event.mirror_path))
        else:  # the attachment is at the protocol level.
            self.autoprotocol_instance.add_attachment(
                attachment_factory.create_object(event.mirror_path))

        self.logbook_changed = True

    def create_yaml_file(self, event: watchdog.events.FileSystemEvent):

        self.autoprotocol_instance.initialize_yaml(self.autoprotocol_instance.yamlFilename)
        self.logbook_changed = True

    def create_microscope_picture(self, event: watchdog.events.FileSystemEvent):

        # we have a new image, and we need to check if its sample and samples
        # parents already exists
        self.check_and_add_parents(event.mirror_path)

        # we know that sample_name already exists because it is checked
        # in the check_and_add_parents
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            try:
                self.autoprotocol_instance.samples[sample_full_name].add_microscope_picture(
                    microscope_picture_factory.create_object(event.mirror_path)
                )
                self.logbook_changed = True
            except (PIL.UnidentifiedImageError, autoerror.UnableToOpenMicroscopePicture, autoerror.ForceRemirroring,
                    OSError) as e:
                log.error('Cannot identify or open image %s ' % str(event.mirror_path))
                # log.exception(e, exc_info=True)
                # if mirroring is required, then try to recopy it
                if self.params['is_mirroring_requested']:
                    # just dispatch once again the event
                    log.error('Trying to recopy the file from original folder')
                    self.mirror_maker.dispatch(event)
                raise e  # this will force the tenacity decorator to repeat the whole method.
        else:
            # if we get here, it is because the user saved a tif file in the protocol
            # base folder, and we don't know what to do with this. Just ignore it.
            log.debug('Found a TIFF file in the protocol base folder. Doing nothing')

    def create_video_file(self, event: watchdog.events.FileSystemEvent):

        self.check_and_add_parents(event.mirror_path)
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            self.autoprotocol_instance.samples[sample_full_name].add_video(Video(event.mirror_path))
            self.logbook_changed = True
        else:
            log.debug('Found a video file in the protocol base folder. Doing nothing')

    def create_optical_image(self, event: watchdog.events.FileSystemEvent):

        # check and eventually add parents samples.
        self.check_and_add_parents(event.mirror_path)
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        try:
            if sample_full_name:  # the optical image is inside a sample folder
                self.autoprotocol_instance.samples[sample_full_name].add_optical_image(event.mirror_path)
            else:
                self.autoprotocol_instance.add_optical_image(event.mirror_path)
        except (PIL.UnidentifiedImageError, OSError) as e:
            log.error('Cannot identify or open image %s' % str(event.mirror_path))
            # if mirroring is required, then try to recopy it
            if self.params['is_mirroring_requested']:
                # just dispatch once again the event
                log.error('Trying to recopy the file from original folder')
                self.mirror_maker.dispatch(event)
            raise e  # this will force the tenacity decorator to repeat the whole method.
        except autoerror.InvalidOpticalImageError:
            log.warning('Image %s is a microscope picture and not an optical image.' % event.mirror_path)
            log.warning('Rerouting the processing...')
            self.create_microscope_picture(event)

        self.logbook_changed = True

    @retry(retry=retry_if_not_exception_type(autoerror.ReadOnlyEntry),
           reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS),
           wait=wait_incrementing(autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT,
                                  autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MIN,
                                  autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MAX),
           before_sleep=before_sleep_log(log, logging.WARNING, True),
           after=after_log(log, logging.WARNING))
    def process_on_deleted(self, event: watchdog.events.FileSystemEvent):
        """
        Stub of the process on deleted method. To be overloaded.

        Parameters
        ----------
        event:
            Filesystem event to be processed.
        """
        # reset the logbook changed flag
        self.logbook_changed = False

        # what has been deleted?
        element_type = self.guess_element_type(event.mirror_path)

        # element_type can also be None, if no ElementTypeGuesser was returning with a positive answer.
        # in this case we don't dispatch the process any further.
        if element_type:
            # the guess for an element type was successful. Process the event by
            # dispatching it to the responsible slot.
            self.deletion_distributor[element_type](event)

        # update the logbook if needed
        if self.logbook_changed and not self.skip_elog_update:
            self.update_logbook(skip_attachments=True)

    def delete_attachment_file(self, event: watchdog.events.FileSystemEvent) -> None:

        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            self.autoprotocol_instance.samples[sample_full_name].remove_attachment(event.mirror_path)
            self.check_and_remove_parents(event.mirror_path)
        else:
            self.autoprotocol_instance.remove_attachment(event.mirror_path)
        self.autoprotocol_instance.remove_from_yaml(str(event.mirror_path))
        self.logbook_changed = True

    def delete_yaml_file(self, event: watchdog.events.FileSystemEvent):
        self.create_yaml_file(event)

    def delete_microscope_picture(self, event: watchdog.events.FileSystemEvent):

        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            # the tif image is in a sample folder

            # first we remove the yaml section if existing.
            # the picture id is used as a key for that dictionary.
            pic_id = self.autoprotocol_instance.samples[sample_full_name].images[str(event.mirror_path)].getID()
            self.autoprotocol_instance.remove_from_yaml(pic_id)

            # now remove the picture from the sample
            self.autoprotocol_instance.samples[sample_full_name].remove_microscope_picture_path(event.mirror_path)
            self.logbook_changed = True
            log.debug('Removing image (%s) from an existing sample (%s)' % (event.mirror_path, sample_full_name))
            self.check_and_remove_parents(event.mirror_path)

        else:
            # the tif image is in the protocol folder.
            # we just ignore it.
            log.debug('Found a TIFF file in the protocol base folder. Doing nothing')

    def delete_video_file(self, event: watchdog.events.FileSystemEvent):

        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:

            # first we remove the yaml section if existing.
            # the video path is used as a key for that dictionary.
            self.autoprotocol_instance.remove_from_yaml(event.mirror_path)

            # now remove the picture from the sample
            self.autoprotocol_instance.samples[sample_full_name].remove_video(event.mirror_path)
            self.logbook_changed = True
            log.debug('Removing video (%s) from an existing sample (%s)' % (event.mirror_path, sample_full_name))
            self.check_and_remove_parents(event.mirror_path)

        else:
            # the video is in the protocol folder.
            # we just ignore it.
            log.debug('Found a video file in the protocol base folder. Doing nothing')

    def delete_optical_image(self, event: watchdog.events.FileSystemEvent):
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            self.autoprotocol_instance.samples[sample_full_name].remove_optical_image(event.mirror_path)
            self.check_and_remove_parents(event.mirror_path)
        else:
            self.autoprotocol_instance.remove_optical_image(event.mirror_path)
        self.autoprotocol_instance.remove_from_yaml(str(event.mirror_path))
        self.logbook_changed = True

    @retry(retry=retry_if_not_exception_type(autoerror.ReadOnlyEntry),
           reraise=True, stop=stop_after_attempt(autoconfig.AUTOLOGBOOK_WATCHDOG_MAX_ATTEMPTS),
           wait=wait_incrementing(autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_INCREMENT,
                                  autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MIN,
                                  autoconfig.AUTOLOGBOOK_WATCHDOG_WAIT_MAX),
           before_sleep=before_sleep_log(log, logging.WARNING, True),
           after=after_log(log, logging.WARNING))
    def process_on_modified(self, event: watchdog.events.FileSystemEvent):
        """
        Stub of the process on modified method. To be overloaded.

        Parameters
        ----------
        event:
            Filesystem event to be processed.
        """
        # be sure that the copy is finished.
        self.wait_until_file_is_closed(event)

        # reset the logbook changed flag
        self.logbook_changed = False

        # what has been modified?
        element_type = self.guess_element_type(event.mirror_path)

        # element_type can also be None, if no ElementTypeGuesser was returning with a positive answer.
        # in this case we don't dispatch the process any further.
        if element_type:
            # the guess for an element type was successful. Process the event by
            # dispatching it to the responsible slot.
            self.modification_distributor[element_type](event)

        if self.logbook_changed and not self.skip_elog_update:
            self.update_logbook(skip_attachments=True)

    def modify_attachment_file(self, event: watchdog.events.FileSystemEvent):
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            self.autoprotocol_instance.samples[sample_full_name].attachments[str(event.mirror_path)].update()
        else:
            self.autoprotocol_instance.attachments[str(event.mirror_path)].update()
        self.logbook_changed = True

    def modify_yaml_file(self, event: watchdog.events.FileSystemEvent):
        self.create_yaml_file(event)

    def modify_microscope_picture(self, event: watchdog.events.FileSystemEvent):
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        # it is possible that the modified microscope picture has a different type
        old_type = self.autoprotocol_instance.samples[sample_full_name].images[str(event.mirror_path)].get_type()
        new_type = microscope_picture_factory.guess_type(event.mirror_path)
        if old_type == new_type:
            self.autoprotocol_instance.samples[sample_full_name].images[str(event.mirror_path)].update()
        else:
            self.autoprotocol_instance.samples[sample_full_name].images[str(event.mirror_path)] = \
                microscope_picture_factory.create_object(event.mirror_path, new_type)
        self.logbook_changed = True

    def modify_video_file(self, event: watchdog.events.FileSystemEvent):
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        self.autoprotocol_instance.samples[sample_full_name].videos[str(event.mirror_path)].update()
        self.logbook_changed = True

    def modify_optical_image(self, event: watchdog.events.FileSystemEvent):
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            self.autoprotocol_instance.samples[sample_full_name].optical_images[str(event.mirror_path)].update()
        else:
            self.autoprotocol_instance.optical_images[str(event.mirror_path)].update()
        self.logbook_changed = True

    def process_on_moved(self, event: watchdog.events.DirMovedEvent | watchdog.events.FileMovedEvent):
        """
        Stub of the process on moved method.

        It is like a process_on_created followed by a process_on_deleted.

        Parameters
        ----------
        event:
            Filesystem event to be processed.
        """

        if event.is_directory:
            created_event = watchdog.events.DirCreatedEvent(event.mirror_path_2)
            deleted_event = watchdog.events.DirDeletedEvent(event.mirror_path)
        else:
            created_event = watchdog.events.FileCreatedEvent(event.mirror_path_2)
            deleted_event = watchdog.events.FileDeletedEvent(event.mirror_path)

        # we need to patch the events with the mirror path.
        # In the case of a move event, we have two mirror paths, one for the src and one for the dest path.
        created_event.mirror_path = event.mirror_path_2
        deleted_event.mirror_path = event.mirror_path

        self.process_on_created(created_event)
        self.process_on_deleted(deleted_event)

    def dispatch(self, event: watchdog.events.FileSystemEvent):
        """
        Overload of the dispatch method.

        This overload is calling the Mirroring Event Handler member class to dispatch (and process) the event before
        dispatching it to the Protocol Event Handler if mirroring is requested.

        In case mirroring is not requested, the filesystem event is patched adding the mirror_path attribute in order
        to maintain the compatibility with the mirroring requested case.

        Parameters
        ----------
        event:
            The filesystem event being dispatched.
        """

        # BUGGGG!!!!
        if event.event_type == watchdog.events.EVENT_TYPE_DELETED and \
                event.is_directory and \
                event.src_path == str(self.params['original_path']):
            log.critical('Suspicious event not dispatched. Is the emitter thread still alive?')
            return

        if self.params['is_mirroring_requested']:
            self.mirror_maker.dispatch(event)
            # this can happen in the case the mirror maker was not dispatching the event for example because it was
            # excluded (*.tmp file)
            if not hasattr(event, 'mirror_path'):
                self.mirror_maker.patch_event(event)
        else:
            event.mirror_path = event.src_path
            if event.event_type == watchdog.events.EVENT_TYPE_MOVED:
                event.mirror_path_2 = event.dest_path

        # due to a known limitation of watchdog, this cannot tell us if a removed object is a file or directory.
        # it will always generate FileDeletedEvents even if it was a directory. We can actually know it because we can
        # check if such a path is a sample.
        if event.event_type == watchdog.events.EVENT_TYPE_DELETED:
            sample_full_name = str(Path(event.mirror_path).relative_to(self.autoprotocol_instance.path)).replace('\\',
                                                                                                                 '/')
            if sample_full_name in self.autoprotocol_instance.samples:
                # this event is actually manually dispatched because of the limitation above
                self.process_on_removed_sample(event)
                self.previous_event = event
                # return here, because there is nothing else to dispatch
                return

        if self.previous_event is None:
            super().dispatch(event)
        else:
            old_key = self.previous_event.key
            new_key = event.key
            if old_key[1:] == new_key[1:] and old_key[0] == watchdog.events.EVENT_TYPE_CREATED \
                    and new_key[0] == watchdog.events.EVENT_TYPE_MODIFIED:
                # the two events are one after the other and the second one is just a
                # file modification of the first one.
                log.debug('Modified event not dispatched!')
            else:
                super().dispatch(event)

        self.previous_event = event

    def process_on_removed_sample(self, event: watchdog.events.FileSystemEvent, skip_elog_update: bool = False):
        sample_full_name = str(event.mirror_path.relative_to(self.autoprotocol_instance.path)).replace('\\', '/')
        self.autoprotocol_instance.remove_sample(sample_full_name)
        self.check_and_remove_parents(event.mirror_path)
        if not skip_elog_update:
            self.update_logbook(skip_attachments=True)

    def guess_element_type(self, path):
        """
        Guess the type of element.

        Starting from the full path retrieved from the FS event, all available
        ElementTypeGuessers are checked. As soon as one is returning a valid element
        the corresponding element type is returned.

        Parameters
        ----------
        path : str, Path
            The path of the FS event.

        Returns
        -------
        etype : autotools.ElementType
            The ElementType as guessed by the given path.

        """
        for (guesser, etype) in self.type_guessers.values():
            if guesser.is_ok(path):
                return etype

    @staticmethod
    def wait_until_file_is_closed(event):
        """
        Wait until the copy of the file in the event is finished.

        This method is monitoring the size of the newly added file. If it keeps
        on changing it means that is still being copied.

        The size of the file is polled with an adaptive delay. Very fast at the
        beginning and more slowly later on. The maximum polling delay is 1 sec.
        Normally only 1 interaction is necessary for a standard size TIFF file
        corresponding to a delay of 0.06s.

        Parameters
        ----------
        event : filesystem event
            This is the file system event generated by the file being
            copied.

        Returns
        -------
        None.

        """
        if isinstance(event, watchdog.events.FileCreatedEvent):
            old_size = -1
            i = 0.
            while old_size != Path(event.src_path).stat().st_size:
                old_size = Path(event.src_path).stat().st_size
                delay = 2 / math.pi * math.atan(i / 6 + 0.1)
                i += 1
                time.sleep(delay)

    def get_full_sample_name(self, new_pic_path: str | Path) -> str | None:
        r"""
        Get the sample full name from the picture path.

        For example, if a protocol is based in:
            R:\Results\2022\1234-project-resp\
        and a picture is created with the following path:
            R:\Results\2022\1234-project-resp\Sample1\Sample1.2\Sample1.2.1\image.tif

        then the sample full name will be:
            Sample1/Sample1.2/Sample1.2.1

        Parameters
        ----------
        new_pic_path : str | Path
            The full path of the newly added picture.

        Returns
        -------
        sample_full_name: str | None
            The sample full name or Nane if the object does not belong to a sample

        """
        if not isinstance(new_pic_path, Path):
            new_pic_path = Path(new_pic_path)

        sample_full_name = str(new_pic_path.relative_to(Path(self.params.get('destination_path'))).parent).replace('\\',
                                                                                                                   '/')
        if sample_full_name == '.':
            sample_full_name = None
        return sample_full_name

    def check_and_add_parents(self, new_pic_path):
        """
        Check if the parent samples of the new pictures are all existing.

        From the path of the new pictures, the list of all sample parents is
        calculated and the protocol is checked to verify that they are all there.
        If not, they are added.

        Parameters
        ----------
        new_pic_path : string or path
            The path of the newly added picture.

        Returns
        -------
        None.

        """
        if not isinstance(new_pic_path, Path):
            new_pic_path = Path(new_pic_path)

        # we need to add samples using their full_name
        # the parent lists returns something like:
        #
        #      ['SampleA', 'SampleA/SubSampleB', 'SampleA/SubSampleB/SubSampleC']
        for sample_full_name in autotools.parents_list(new_pic_path, self.autoprotocol_instance.path):
            if sample_full_name not in self.autoprotocol_instance.samples and sample_full_name != '.':
                self.autoprotocol_instance.add_sample(Sample(sample_full_name))

    def check_and_remove_parents(self, removed_pic_path):
        """
        Check if the parents are not needed anymore and remove them.

        From the path of the newly removed picture check if the parents samples
        are still needed. If they are emtpy, they are removed.

        Parameters
        ----------
        removed_pic_path : string or path
            The path of the newly removed picture.

        Returns
        -------
        None.

        """
        if not isinstance(removed_pic_path, Path):
            removed_pic_path = Path(removed_pic_path)

        # we need to remove samples using their full_name
        # the parent lists returns something like:
        #
        #      ['SampleA', 'SampleA/SubSampleB', 'SampleA/SubSampleB/SubSampleC']
        for sample_full_name in reversed(autotools.parents_list(removed_pic_path,
                                                                self.params.get('destination_path'))):
            if self.autoprotocol_instance.samples[sample_full_name].is_empty():
                log.debug('Sample %s is empty. Remove it' % sample_full_name)
                self.autoprotocol_instance.remove_sample(sample_full_name)
            else:
                log.debug('Sample %s is not empty. Leave it' % sample_full_name)
                break

    def on_created(self, event):
        """
        Handle an on_created event.

        Parameters
        ----------
        event : watchdog.event

        Returns
        -------
        None.

        """
        try:
            self.process_on_created(event)
        except FileNotFoundError as e:
            log.debug(e, exc_info=True)
            log.error('File %s not found. Was it already deleted? Skipping it.' % event.mirror_path)
        except PIL.UnidentifiedImageError as e:
            log.debug(e, exc_info=True)
            log.error('Impossible to open image %s. Skipping it.' % event.mirror_path)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def on_deleted(self, event):
        """
        Handle an on_delete event.

        It calls the remove_resource function.

        Parameters
        ----------
        event : watchdog.events

        Returns
        -------
        None.

        """
        try:
            self.process_on_deleted(event)
        except Exception as e:
            log.error('Error removing file %s, skipping it.' % event.mirror_path)
            log.exception(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def on_modified(self, event):
        try:
            self.process_on_modified(event)
        except FileNotFoundError as e:
            log.error(
                'File %s not found. Was it already deleted? Skipping it.' % event.mirror_path)
            log.debug(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def on_moved(self, event):
        """
        Handle an on_moved event.

        It calls the move_resource function.

        Parameters
        ----------
        event : watchdog.events

        Returns
        -------
        None.

        """
        try:
            self.process_on_moved(event)
        except Exception as e:
            log.error('Error moving %s to %s, skipping it.' % (event.src_path, event.dest_path))
            log.debug(e, exc_info=True)
        except Exception as e:
            log.exception(e, exc_info=True)
            log.error('Error encountered with processing of event %s.' % str(event.key))

    def set_queue_reference(self, queue):
        """
        Set the reference of the Observer queue.

        It is intended to offer the possibility to the user of performing some
        tasks depending on the amount of events in the queue waiting to be
        processed.

        Parameters
        ----------
        queue : Queue
            The event queue of the observer.

        Returns
        -------
        None.

        """
        self.queue = queue

    def update_logbook(self, skip_attachments=True):
        """
        Update the logbook entry.

        Generate the HTML code of the whole protocol and post it to the
        server.

        The posting will actually take place if the observer queue is 'almost empty' and if the last update was not
        too recent.

        Almost empty means that the size is below 2. In fact every time a creation event is generated there is at least
        one modified event for the file and also one for the directory coming along.

        Parameters
        ----------
        skip_attachments : bool, optional
            Allows to skip the attachments in order to reduce the network_path traffic.
            The default is True.

        """
        c = self.queue.qsize() < 2
        d = datetime.now().timestamp() - self.last_update.timestamp() > autoconfig.AUTOLOGBOOK_WATCHDOG_MIN_DELAY
        if c and d:

            self.autoprotocol_instance.post_elog_message(skip_attachments)
            self.last_update = datetime.now()

        else:
            if not c and not d:
                why = 'Not empty queue and too recent update'
            else:
                if not c:
                    why = 'Not empty queue'
                if not d:
                    why = 'Too recent update'
            log.info('Skipping ELOG updates (%s)' % why)

    def process_already_existing_items(self):
        """
        Process all existing items.

        This function is processing all existing items found in the protocol
        folder when the watchdog is started.

        Returns
        -------
        None.

        """

        if self.params['is_mirroring_requested']:
            self.mirror_maker.process_all_existing()

        log.info('Processing existing files in folder %s' % self.autoprotocol_instance.path)

        # in the case of the preprocessing it makes sense to exclude some patterns. For example, all thumbs / png /
        # cropped / excluded images. If we don't exclude them, their corresponding synthetic event will be anyhow
        # generated and the file type will be guessed. For a sample with 15 images, there will be something like 30
        # additional events to be guessed each of them requiring some time (0.075 sec on average) for a total 2.25
        # seconds wasted time.
        self.skip_elog_update = True
        for filename in sorted(autotools.reglob(path=os.path.join(self.autoprotocol_instance.path),
                                                matching_regexes=self.matching_patterns,
                                                ignore_regexes=regexp_repository.get_exclude('PRE_PROCESS'),
                                                recursive=True)):
            log.debug('Preprocess file %s' % filename)
            event = watchdog.events.FileCreatedEvent(os.path.join(filename))
            event.mirror_path = os.path.join(filename)
            # we are using the process_on_created even if the files are already existing.
            self.process_on_created(event)
        self.skip_elog_update = False
        self.update_logbook(skip_attachments=True)


class VersaELOGProtocolEventHandler(ProtocolEventHandler):
    """
    The VersaELOGProtocolEventHandler.

    This is a subclass of the general ProtocolEventHandler customized for the
    Versa microscope.

    """
    pass


class QuattroELOGProtocolEventHandler(ProtocolEventHandler):
    """
    The QuattroELOGProtocolEventHandler.

    This is a subclass of the general ProtocolEventHandler including customized behavior specific for the Quattro
    Microscope.
    """

    def __init__(self, autoprotocol_instance: Protocol, **kwargs):
        super().__init__(autoprotocol_instance, **kwargs)

        self.add_element_type(
            element_type=ElementType.NAVIGATION_PIC,
            creation_slot=self.create_navigation_picture,
            modification_slot=self.modify_navigation_picture,
            deletion_slot=self.delete_navigation_picture,
            regexp_matching_pattern=regexp_repository.get_matching('NAVIGATION'),
            regexp_exclude_pattern=regexp_repository.get_exclude('NAVIGATION')
        )

    def create_navigation_picture(self, event: watchdog.events.FileSystemEvent):
        # a navigation image can only be placed in the base folder. if a navcam picture is saved in a sample folder
        # inform the user about the problem
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if sample_full_name:
            log.warning('A navigation picture has been saved into a sample folder.')
            log.warning('It will be mirrored, but not added to the protocol.')
            log.warning('Navigation pictures must be saved in the protocol base folder.')
        else:
            self.autoprotocol_instance.add_navigation_camera_image(event.mirror_path)
            self.logbook_changed = True

    def modify_navigation_picture(self, event: watchdog.events.FileSystemEvent):
        pass

    def delete_navigation_picture(self, event: watchdog.events.FileSystemEvent):
        # a navigation image can only be placed in the base folder.
        sample_full_name = self.get_full_sample_name(event.mirror_path)
        if not sample_full_name:
            self.autoprotocol_instance.remove_navigation_camera_image(event.mirror_path)
            self.autoprotocol_instance.remove_from_yaml(event.mirror_path)
            self.logbook_changed = True


class VegaELOGProtocolEventHandler(ProtocolEventHandler):
    """
    The VegaELOGProtocolEventHandler.

    This is a subclass of the general ProtocolEventHandler customized for the Vega microscope.

    The specificities of this event handlers are the fact that very often microscope pictures are saved in JPEG format
    and that in such a case the metadata are stored in a separate file.
    """

    @staticmethod
    def get_picture_key_from_header_file(hdr_file_path: str | Path) -> str:
        r"""
        Return the picture key given an header filename.

        For example if hdr_file_path = C:\path\mypic-012-tif.hdr, this function will return:
        c:\path\mypic-012.tif

        Parameters
        ----------
        hdr_file_path: str | Path
            The header file full path

        Returns
        -------
        The microscope picture key.
        """
        if not isinstance(hdr_file_path, Path):
            hdr_file_path = Path(hdr_file_path)

        folder = hdr_file_path.parent
        hdr_stem = hdr_file_path.stem
        picture_filename = hdr_stem[::-1].replace('-'[::-1], '.'[::-1], 1)[::-1]
        return str(Path(folder) / Path(picture_filename))

    @staticmethod
    def get_hdr_file_from_picture_file(picture_path: str | Path) -> str:
        """Return the expected header file starting from the microscope picture path."""

        if not isinstance(picture_path, Path):
            picture_path = Path(picture_path)

        pic_base_path = picture_path.parent
        pic_stem = picture_path.stem
        pic_suffix = picture_path.suffix.replace('.', '-')
        hdr_suffix = '.hdr'
        hdr_path = pic_base_path / Path(pic_stem + pic_suffix + hdr_suffix)
        return str(hdr_path)

    def __init__(self, autoprotocol_instance: Protocol, **kwargs):
        # start with the super method
        super().__init__(autoprotocol_instance, **kwargs)

        # prepare a jpeg guesser to be used to internally reroute some callbacks
        self.jpeg_guesser = ElementTypeGuesser(regexp_repository.get_matching('JPEG'),
                                               regexp_repository.get_exclude('JPEG'))

    def prepare_element_types(self):
        super().prepare_element_types()

        # add the header file type to the guesser dictionary
        self.add_element_type(
            element_type=ElementType.HEADER_FILE,
            creation_slot=self.create_header_file,
            modification_slot=self.modify_header_file,
            deletion_slot=self.delete_header_file,
            regexp_matching_pattern=regexp_repository.get_matching('HEADERFILE'),
            regexp_exclude_pattern=regexp_repository.get_matching('HEADERFILE')
        )

        # we need to extend the Microscope Picture guesser to include jpeg
        include_pattern = regexp_repository.get_matching('IMAGEFILE')
        include_pattern.extend(regexp_repository.get_matching('JPEG'))
        exclude_pattern = None
        if regexp_repository.get_exclude('IMAGEFILE') is not None:
            exclude_pattern = regexp_repository.get_exclude('IMAGEFILE')
        if regexp_repository.get_exclude('JPEG') is not None:
            if exclude_pattern is not None:
                exclude_pattern.extend(regexp_repository.get_exclude('JPEG'))

        # modify the existing microscope picture guesser.
        # the modify element type is not changing the guesser order.
        self.modify_element_type(
            element_type=ElementType.MICROSCOPE_PIC,
            creation_slot=self.create_microscope_picture,
            modification_slot=self.modify_microscope_picture,
            deletion_slot=self.delete_microscope_picture,
            regexp_matching_pattern=include_pattern,
            regexp_exclude_pattern=exclude_pattern
        )

    def create_header_file(self, event: watchdog.events.FileSystemEvent):
        """
        React to the creation event of a header file.

        The header file contains the metadata of the microscope picture. It is particularly useful in case of JPEG
        microscope pictures because they don't have metadata at all.

        In case the header file corresponds to a JPEG picture, then this method is checking if the corresponding image
        has the metadata. If not, the metadata are embedded.

        In all cases (JPEG or TIFF) an update of the corresponding image is triggered.

        Parameters
        ----------
        event: watchdog.events.FileSystemEvent
            The event being handled.
        """
        # we got a header file.
        # we need to check if the corresponding original picture in the local folder has already embedded metadata
        local_picture = self.get_picture_key_from_header_file(event.src_path)
        if self.jpeg_guesser.is_ok(local_picture):
            if not self.has_jpeg_picture_metadata(local_picture):
                # no embedded metadata, then try to add them
                self.embed_metadata_into_jpeg(local_picture)

        # just to be sure trigger an update of the corresponding picture in the protocol
        picture_key = self.get_picture_key_from_header_file(event.mirror_path)

        sample_full_name = self.get_full_sample_name(picture_key)
        if sample_full_name:
            # the image is in a sample folder
            # does the sample exists already?
            if sample_full_name in self.autoprotocol_instance.samples.keys():
                # yes!
                # and is the picture existing?
                if picture_key in self.autoprotocol_instance.samples[sample_full_name].images.keys():
                    # yes!
                    # then force an update of the picture
                    self.autoprotocol_instance.samples[sample_full_name].images[picture_key].update()
                    self.logbook_changed = True
                else:
                    # the picture was not found in the microscope picture dictionary, but if it is a jpeg it is
                    # possible that it was wrongly assigned as an optical image. we need to check this option.
                    if picture_key in self.autoprotocol_instance.samples[sample_full_name].optical_images.keys() \
                            and self.jpeg_guesser.is_ok(local_picture):
                        # yes we did a mistake in the categorization.
                        # we have to remove it from the optical image dictionary in the first place and
                        # reassign it to the microscope picture.
                        self.autoprotocol_instance.samples[sample_full_name].remove_optical_image(picture_key)
                        self.autoprotocol_instance.samples[sample_full_name].add_microscope_picture(picture_key)
                        self.logbook_changed = True
        # in all other cases, the image corresponding to the header file was not found. then just let it go

    def modify_header_file(self, event: watchdog.events.FileSystemEvent):
        """
        React to a modification of the header file.

        Header files are not stored. If one is modified, then the creation callback is invoked.

        Parameters
        ----------
        event: watchdog.events.FileSystemEvent
            The event being handled
        """
        self.create_header_file(event)

    def delete_header_file(self, event: watchdog.events.FileSystemEvent):
        """
        React to the removal of an header file.

        Actually do nothing.

        Parameters
        ----------
        event: watchdog.events.FileSystemEvent
            The event being handled
        """
        pass

    def create_microscope_picture(self, event: watchdog.events.FileSystemEvent):
        """
        Overload of the microscope picture creation.

        This method needs to reroute the event handling depending if the microscope picture is JPG or TIFF.

        In case of a JPG file, the event handling is rerouted somewhere else, while for the TIFF files the super method
        is invoked.

        Parameters
        ----------
        event: watchdog.events.FileSystemEvent
            The event being handled
        """

        # let's check if the picture is a JPEG
        if self.jpeg_guesser.is_ok(event.mirror_path):
            # it is a jpeg, we need to check if it is really a microscope picture or an optical one.
            self.reroute_jpeg_picture(event, self.create_jpeg_microscope_picture, self.create_optical_image)
        elif self.jpeg_guesser._is_matching(event.mirror_path) \
                and self.jpeg_guesser._is_excluded(event.mirror_path):
            try:
                optical_image_type = optical_image_factory.guess_type(event.mirror_path)
                if optical_image_type == autotools.OpticalImageType.INVALID_OPTICAL_IMAGE:
                    # this is a very specific case. it is jpeg file containing Vega Metadata but the user put by
                    # mistake an opti string in its name. we reroute it to the jpeg microscope picture processor
                    self.create_jpeg_microscope_picture(event)
            except (PIL.UnidentifiedImageError, OSError) as e:
                log.error('Cannot identify or open image %s ' % str(event.mirror_path))
                # log.exception(e, exc_info=True)
                # if mirroring is required, then try to recopy it
                if self.params['is_mirroring_requested']:
                    # just dispatch once again the event
                    log.error('Trying to recopy the file from original folder')
                    self.mirror_maker.dispatch(event)
                raise e  # this will force the tenacity decorator to repeat the whole method.
        else:
            # it is a tif. let's go ahead as usual
            super().create_microscope_picture(event)

    def create_jpeg_microscope_picture(self, event: watchdog.events.FileSystemEvent):
        """
        Create a microscope picture in JPEG format.

        This method is not called directly by the creation distributor, but rather from the rerouting for JPEG pictures.

        Parameters
        ----------
        event: watchdog.events.FileSystemEvent
            The event being handled
        """
        # we have a new image, and we need to check if its sample and samples
        # parents already exists
        self.check_and_add_parents(event.mirror_path)

        # we know that sample_name already exists because it is checked
        # in the check_and_add_parents
        sample_full_name = self.get_full_sample_name(event.mirror_path)

        # as usual, we take care of pictures only if inside a sample folder
        if sample_full_name:
            # does the picture have already embedded metadata?
            #
            # ATTENTION: usually the protocol event handler acts on the mirror_path, but not here.
            #            we want to check if the file in the original folder has the metadata and in
            #            case we add them there. This modification of the original file will generate a new
            #            modification event that will force the original file to be copied to the mirror path.
            if not self.has_jpeg_picture_metadata(event.src_path):
                # it's a jpeg image, and it has no metadata. try to add them
                self.embed_metadata_into_jpeg(event.src_path)

            try:
                # add it to the project using the VegaJPEGPicture class
                self.autoprotocol_instance.samples[sample_full_name].add_microscope_picture(
                    VegaJPEGPicture(str(event.mirror_path)))
                self.logbook_changed = True
            except (PIL.UnidentifiedImageError, OSError) as e:
                log.error('Cannot identify or open image %s ' % str(event.mirror_path))
                # if mirroring is required, then try to recopy it
                if self.params['is_mirroring_requested']:
                    # just dispatch once again the event
                    log.error('Trying to recopy the file from original folder')
                    self.mirror_maker.dispatch(event)
                raise e  # this will force the tenacity decorator to repeat the whole method.

    def modify_microscope_picture(self, event: watchdog.events.FileSystemEvent):
        if self.jpeg_guesser.is_ok(event.mirror_path):
            self.reroute_jpeg_picture(event, self.modify_jpeg_microscope_picture, self.modify_optical_image)
        else:
            super().modify_microscope_picture(event)

    def delete_microscope_picture(self, event: watchdog.events.FileSystemEvent):
        if self.jpeg_guesser.is_ok(event.mirror_path):
            # it is a jpeg, but we cannot open the file because it has been deleted
            sample_full_name = self.get_full_sample_name(event.mirror_path)
            if sample_full_name:
                sample = self.autoprotocol_instance.samples[sample_full_name]
                if str(event.mirror_path) in sample.images:
                    sample.remove_microscope_picture_path(event.mirror_path)
                elif str(event.mirror_path) in sample.optical_images:
                    sample.remove_optical_image(str(event.mirror_path))
            else:
                if str(event.mirror_path) in self.autoprotocol_instance.optical_images:
                    self.autoprotocol_instance.remove_optical_image(event.mirror_path)
        else:
            super().delete_microscope_picture(event)

    def modify_jpeg_microscope_picture(self, event: watchdog.events.FileSystemEvent):
        # we got modifications to a microscope picture
        sample_full_name = self.get_full_sample_name(event.mirror_path)

        if not self.has_jpeg_picture_metadata(event.src_path):
            self.embed_metadata_into_jpeg(event.src_path)

        self.autoprotocol_instance.samples[sample_full_name].images[str(event.mirror_path)].update()
        self.logbook_changed = True

    def modify_optical_image(self, event: watchdog.events.FileSystemEvent):
        # we have to overload this function because of a peculiarity.
        # if the image has the pattern _opti.jpg is very likely an optical image, but it is not necessarily true.
        # in that case we need to be careful from where we delete the object.
        if self.jpeg_guesser._is_matching(event.mirror_path) and self.jpeg_guesser._is_excluded(event.mirror_path):
            # it is a jpeg and it has the opti pattern
            sample_full_name = self.get_full_sample_name(event.mirror_path)
            if sample_full_name:
                sample = self.autoprotocol_instance.samples[sample_full_name]
                if str(event.mirror_path) in sample.images:
                    sample.images[str(event.mirror_path)].update()
                    self.logbook_changed = True
                elif str(event.mirror_path) in sample.optical_images:
                    sample.optical_images[str(event.mirror_path)].update()
                    self.logbook_changed = True
            else:
                # in the base folder there are only optical images, but to be sure we protect the removal
                if str(event.mirror_path) in self.autoprotocol_instance.optical_images:
                    self.autoprotocol_instance.optical_images[str(event.mirror_path)].update()
                    self.logbook_changed = True

        else:
            super().modify_optical_image(event)

    def delete_optical_image(self, event: watchdog.events.FileSystemEvent):
        # we have to overload this function because of a peculiarity.
        # if the image has the pattern _opti.jpg is very likely an optical image, but it is not necessarily true.
        # in that case we need to be careful from where we delete the object.
        if self.jpeg_guesser._is_matching(event.mirror_path) and self.jpeg_guesser._is_excluded(event.mirror_path):
            # it is a jpeg and it has the opti pattern
            sample_full_name = self.get_full_sample_name(event.mirror_path)
            if sample_full_name:
                sample = self.autoprotocol_instance.samples[sample_full_name]
                if str(event.mirror_path) in sample.images:
                    sample.remove_microscope_picture_path(str(event.mirror_path))
                    self.logbook_changed = True
                elif str(event.mirror_path) in sample.optical_images:
                    sample.remove_optical_image(str(event.mirror_path))
                    self.logbook_changed = True
                if self.logbook_changed:
                    self.check_and_remove_parents(event.mirror_path)
            else:
                # in the base folder there are only optical images, but to be sure we protect the removal
                if str(event.mirror_path) in self.autoprotocol_instance.optical_images:
                    self.autoprotocol_instance.remove_optical_image(event.mirror_path)
                    self.logbook_changed = True

        else:
            super().delete_optical_image(event)

    @staticmethod
    def has_jpeg_picture_metadata(src_path) -> bool:
        if not Path(src_path).exists():
            return False
        exif_dict = piexif.load(str(src_path))
        if '0th' in exif_dict:
            if piexif.ImageIFD.ProcessingSoftware in exif_dict['0th']:
                if b'autologbook' in exif_dict['0th'][piexif.ImageIFD.ProcessingSoftware]:
                    return True

        # in all other cases return false
        return False

    @staticmethod
    def embed_metadata_into_jpeg(src_path) -> bool:

        successful = False

        if not Path(src_path).exists():
            return False

        # to embed the metadata, we need to have the HDR file.
        # check if it already there:
        hdr_file = Path(VegaELOGProtocolEventHandler.get_hdr_file_from_picture_file(src_path))
        if hdr_file.exists():
            # the file exists already, then we read it in as a configuration file
            hdr_metadata = configparser.ConfigParser(allow_no_value=True)
            hdr_metadata.optionxform = str
            hdr_metadata.read(hdr_file)

            x_size = hdr_metadata.getfloat('MAIN', 'PixelSizeX', fallback=0)
            y_size = hdr_metadata.getfloat('MAIN', 'PixelSizeY', fallback=0)
            if all([x_size, y_size]):
                xres = (int(0.01 / float(hdr_metadata['MAIN']['PixelSizeX'])), 1)
                yres = (int(0.01 / float(hdr_metadata['MAIN']['PixelSizeY'])), 1)
                ures = autotools.ResolutionUnit.CM
            else:
                xres = (72, 1)
                yres = (72, 1)
                ures = autotools.ResolutionUnit.INCH

            zeroth = {
                piexif.ImageIFD.ProcessingSoftware: f'autologbook-v{autoconfig.VERSION}',
                piexif.ImageIFD.ResolutionUnit: ures,
                piexif.ImageIFD.XResolution: xres,
                piexif.ImageIFD.YResolution: yres,
                piexif.ImageIFD.Make: 'TESCAN',
                piexif.ImageIFD.Model: hdr_metadata.get('MAIN', 'Device', fallback='Unknown'),
            }

            # now prepare our metadata structure:
            my_metadata = {
                'metadata_version': 1,
                'microscope': 'VEGA',
            }
            for section in hdr_metadata.sections():
                section_dict = {}
                for option in hdr_metadata.options(section):
                    section_dict[option] = hdr_metadata.get(section, option)
                my_metadata[section] = section_dict

            exif_id = {piexif.ExifIFD.MakerNote: pickle.dumps(my_metadata)}
            exif_dict = {'0th': zeroth, 'Exif': exif_id}
            exif_bytes = piexif.dump(exif_dict)
            with PIL.Image.open(src_path) as jpg:
                jpg.save(src_path, exif=exif_bytes)
            jpg.close()
            successful = True

        return successful

    def reroute_jpeg_picture(self, event: watchdog.events.FileSystemEvent,
                             microscope_picture_callback: Callable[[watchdog.events.FileSystemEvent], None],
                             optical_picture_callback: Callable[[watchdog.events.FileSystemEvent], None]):
        try:
            optical_image_type = optical_image_factory.guess_type(event.mirror_path)
            if optical_image_type in [
                autotools.OpticalImageType.INVALID_OPTICAL_IMAGE,  # it is for sure a microscope picture
                autotools.OpticalImageType.GENERIC_OPTICAL_IMAGE,  # it could be a microscope picture
            ]:
                microscope_picture_callback(event)
            else:
                optical_picture_callback(event)
        except (PIL.UnidentifiedImageError, OSError) as e:
            log.error('Cannot identify or open image %s ' % str(event.mirror_path))
            # log.exception(e, exc_info=True)
            # if mirroring is required, then try to recopy it
            if self.params['is_mirroring_requested']:
                # just dispatch once again the event
                log.error('Trying to recopy the file from original folder')
                self.mirror_maker.dispatch(event)
            raise e  # this will force the tenacity decorator to repeat the whole method.


class XL40ELOGProtocolEventHandler(ProtocolEventHandler):
    """
    The XL40ELOGProtocolEventHandler.

    This is a subclass of the general ProtocolEventHandler customized for the
    XL40 microscope.
    """
    pass


class MultiMicroscopeELOGProtocolEventHandler(VegaELOGProtocolEventHandler, QuattroELOGProtocolEventHandler):

    def prepare_element_types(self):
        super().prepare_element_types()

        self.add_element_type(
            element_type=ElementType.NAVIGATION_PIC,
            creation_slot=self.create_navigation_picture,
            modification_slot=self.modify_navigation_picture,
            deletion_slot=self.delete_navigation_picture,
            regexp_matching_pattern=regexp_repository.get_matching('NAVIGATION'),
            regexp_exclude_pattern=regexp_repository.get_exclude('NAVIGATION')
        )
