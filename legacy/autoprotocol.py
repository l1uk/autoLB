# -*- coding: utf-8 -*-
"""Protocol models and ELOG integration for SEM logbook generation.

This module defines the protocol object hierarchy used by autologbook to collect
analysis elements (samples, microscope images, navigation images, optical images,
and attachments), render HTML pages with Jinja2 templates, and publish entries to
an ELOG server.

Main exported classes:
    Protocol: Base in-memory container model for a microscopy analysis session.
    ELOGProtocol: Protocol subclass adding ELOG connectivity and posting logic.
    QuattroELOGProtocol: ELOGProtocol specialization with navigation camera support.
    MultiMicroscopeELOGProtocol: Quattro specialization for mixed-microscope sessions.
    VersaELOGProtocol: ELOGProtocol specialization for Versa workflows.
    VegaELOGProtocol: ELOGProtocol specialization for Vega workflows.
    XL40ELOGProtocol: ELOGProtocol specialization for XL40 workflows.

Relevant dependencies:
    PyQt5: Signal/slot communication through a dispatcher proxy.
    Jinja2: HTML rendering from protocol templates.
    py_elog (elog): ELOG server communication and posting.
    watchdog ecosystem: used by surrounding project components to feed this model.
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
import os
import re
from datetime import datetime
from pathlib import Path

import elog
import urllib3
import yaml
from elog.logbook_exceptions import LogbookServerTimeout
from PyQt5 import QtCore
from tenacity import after_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from autologbook import autoconfig, autoerror, autotools
from autologbook.attachment import Attachment, AttachmentDict
from autologbook.containers import ContainerHelperMixin, ResettableList
from autologbook.elog_interface import ELOGConnectionParameters, elog_handle_factory
from autologbook.elog_post_splitter import ELOGPageType, ELOGPostSplitter, is_splitting_required
from autologbook.html_helpers import HTMLHelperMixin
from autologbook.jinja_integration import jinja_env
from autologbook.microscope_picture import MicroscopePicture
from autologbook.navigation_image import NavigationImagesList
from autologbook.optical_image import GenericOpticalImage, OpticalImageDict, optical_image_factory
from autologbook.protocol_editor_models import ElementType
from autologbook.qt_signal_dispatcher import SignalDispatcher
from autologbook.sample import Sample, SampleDict

urllib3.disable_warnings()
Signal = QtCore.pyqtSignal
Slot = QtCore.pyqtSlot
log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class Protocol(ContainerHelperMixin):
    """Base protocol model storing analysis content and metadata.

    Subclass of `ContainerHelperMixin` specialized for in-memory protocol content
    management (samples, attachments, images) and Qt signal forwarding via
    `SignalDispatcher`.

    Attributes:
        path (Path): Root folder containing protocol files.
        protocol (int | str): Protocol identifier used for logbook entries.
        project (str): Project name extracted from folder naming or provided by user.
        responsible (str): Responsible person for the analysis session.
        attachments (AttachmentDict): Project-level attachments.
        optical_images (OpticalImageDict): Project-level optical images.
        samples (SampleDict): Sample objects keyed by full sample names.
        ordered_sample_list (ResettableList): Flattened sample order for rendering.
        signal_dispatcher (SignalDispatcher): Proxy object for Qt signals.
        yamlDict (dict | None): YAML customization key-value store.
        yamlFilename (Path | None): Path to YAML customization file.
        protocol_type (str): Logical protocol type for templates.
        template (str): Jinja template filename used for HTML rendering.
        last_update (str): Last HTML render timestamp.
    """

    def __init__(self, path: str | Path, protocol: int | str = None, project: str = None, responsible: str = None):
        r"""
        Generate an instance of Protocol.

        It creates and initialize all instance variables of a Protocol,
        in particular the path that is where the all files will be living,
        and the three *ownership* variables, i.e. the protocol number,
        the project name and the responsible person.

        The *ownership variables* are normally retrieved from the path if it
        follows the standard naming convention (see path for the regular
        expression pattern), but they can also be overwritten if explicitly
        specified here.

        Parameters
        ----------
        path : str or path object
            The full path where the protocol is living.
            In order to retrieve the *ownership* variable automatically the path
            should look like these two examples:
                12458-Project-Responsible
                12458_Project_Responsible
            The regular expression pattern being used is the following:
                '^#*([\\d]+)\\s*[-_]\\s*([\\w\\W]+)\\s*[-_]\\s*([\\w\\W]+)$'
        protocol : int or string, optional
            The protocol number. This field is used to identy the analysis inside
            the logbook and of course it must unique. There is no unicity test
            performed here, but it should be done somewhere else.
            When the user wants to have the protocol number guessed from the path
            then, set this variable to None.
            The default is None.
            TODO: Implement a unicity check on the protocol number.
        project : string, optional
            The project name. As for the protocol number (see above), this is
            generally provided with the path.
            The default is None.
        responsible : string, optional
            The name of the responsible person. As for the protocol number (see above),
            this is generally provided with the path.
            The default is None.


        Raises
        ------
        autoerror.MissingProtocolInformation
            This exception is raised if the user did not provided customized
            ownership variables and the automatic guessing from the path
            was failing.

        Returns
        -------
        None.

        """
        super().__init__()

        if not isinstance(path, Path):
            path = Path(path)
        self.path = path

        skip_guessing = False
        if protocol is not None and project is not None and responsible is not None:
            # the user wants to use its own variables
            skip_guessing = True
            self.protocol = protocol
            self.project = project
            self.responsible = responsible

        if not skip_guessing:
            # the user didn't provide his custom ownership variables.
            # we need to guess them from the path.
            folder = self.path.parts[-1]
            pattern = '^#*([\\d]+)\\s*[-_]\\s*([\\w\\W]+)\\s*[-_]\\s*([\\w\\W]+)$'
            match = re.search(pattern, folder)

            if match:
                self.protocol = match.group(1)
                self.project = match.group(2)
                self.responsible = match.group(3)
            else:
                err_msg = '''
                Ownership variables not provided and not available in the path
                '''
                raise autoerror.MissingProtocolInformation(err_msg)

        log.info('Created a new Protocol (#=%s, Project=%s, Responsible=%s)' %
                 (self.protocol, self.project, self.responsible))

        # all containers for images, samples and everything must be of resettable types
        # initialize empty container for attachments
        self.attachments = AttachmentDict()

        # initialize an empty container for project wide optical images
        self.optical_images = OpticalImageDict()

        # initialize empty container for samples
        self.samples = SampleDict()
        # ordered sample list
        self.ordered_sample_list = ResettableList()

        # a signal dispatcher
        self.signal_dispatcher = SignalDispatcher()

        # initialize yaml_dict and its filename
        self.yamlDict = None
        self.yamlFilename = None

        # jinja2
        self.protocol_type = 'Generic'
        self.template = 'protocol_base_template.yammy'
        self.last_update = f'{datetime.now():%Y-%m-%d %H:%M:%S}'

        # reset the picture ID list
        MicroscopePicture._reset_ids()

    def __str__(self) -> str:
        """Return basic string representation of a Protocol."""
        msg = (f'Protocol #{self.protocol} - {self.project} - {self.responsible}\n')
        if len(self.samples) == 0:
            msg += 'with no samples\n'
        elif len(self.samples) == 1:
            msg += 'with 1 sample\n'
        else:
            f'with {len(self.samples)}.\n'
        if len(self.samples):
            msg += '\nSample list:\n\n'
        for sample in self.samples:
            msg += self.samples[sample].__str__()
            msg += '\n'

        return msg

    def emit_added(self, element_type: ElementType, element_name: str, parent_name: str):
        """
        Emit a signal for the addition of a given element to the protocol.

        This method implements an interface to the Qt Signal / Slot mechanism.
        Every time a new element is added to the protocol, this method should be
        called in order to make the GUI aware of the changes, in particular
        the TreeViewModel where the whole protocol is described.

        Parameters
        ----------
        element_type : autotools.ElementType
            This enumerator contains all possible element types
        element_name : String
            In the case of ElementType.MICROSCOPE_PIC, ElementType.NAVIGATION_PIC, ElementType.OPTICAL_PIC
            and ElementType.ATTACHMENT the element_name must be the full path of
            the newly added element.
            In the case of ElementType.SAMPLE, the element_name is exactly the
            sample full name
        parent_name : String
            In the case of ElementType.NAVIGATION_PIC, the parent_name is totally
            optional because all navigation images will be added to the
            'Navigation Images' section.
            For ElementType.ATTACHMENT the parent can be 'Attachments' for project wide attachments
            and the sample full name for sample attachment.
            For ElementType.OPTICAL_PIC the parent can be 'OpticalImages' for project wide attachments
            and the sample full name for sample attachment.
            In the case of ElementType.MICROSCOPE_PIC, the parent_name is the
            sample full name.
            In the case of ElementType.SAMPLE, the parent_name the name of the
            parent full sample or 'Samples' if it is a top level sample.

        Returns
        -------
        None.

        """
        self.signal_dispatcher.added_element.emit(element_type, element_name, parent_name)

    def emit_removed(self, element_type: ElementType, element_name: str, parent_name: str):
        """
        Emit a signal for the removal of a given element from the protocol.

        This method implements an interface to the Qt Signal / Slot mechanism.
        Every time an element is removed from the protocol, this method should be
        called in order to make the GUI aware of the changes, in particular
        the TreeViewModel where the whole protocol is described.

        Parameters
        ----------
        element_type : autotools.ElementType
            This enumerator contains all possible element types
        element_name : String
            In the case of ElementType.MICROSCOPE_PIC, ELementType.Attachment, ElementType.Optical_Pic and
            ElementType.NAVIGATION_PIC, the element_name must be the full path
            of the removed element.
            In the case of Sample, the element_name is exactly the sample name
        parent_name : String
            In the case of NavPic, the parent_name is totally optional because
            all navigation images are located in the 'Navigation Images' section.
            In the case of Attachment, the parent_name is either 'Attachments' for project wide attachments or
            the sample full name for sample attachments.
            In the case of optical images, the parent_name is either 'Optical images' for project wide images or
            the sample full name for sample images.
            In the case of MicroPic, the parent_name is the sample name.
            In the case of ElementType.SAMPLE, the parent_name the name of the
            parent full sample or 'Samples' if it is a top level sample.

        Returns
        -------
        None.

        """
        self.signal_dispatcher.removed_element.emit(element_type, element_name, parent_name)

    def add_attachment(self, attachment: Path | str | Attachment):
        """
        Add an attachment at the Protocol.

        The user must use this method to add an attachment and not add it directly to the attachment container to be
        sure that the corresponding 'add signal' is emitted.

        Parameters
        ----------
        attachment : PATH | string
            The path of the attachment file.

        Returns
        -------
        None.

        """
        try:
            if not isinstance(attachment, Attachment):
                attachment = Attachment(attachment)

            self.attachments.add(attachment)
            attachment.params['anchor'] = attachment.get('filename')
            self.emit_added(ElementType.ATTACHMENT_FILE, attachment.key, 'Attachments')
            log.info('Added %s to the attachment list' % attachment.get('filename'))
        except autoerror.DuplicatedKey as e:
            log.warning(e)

    def remove_attachment(self, attachment_path: str | Path):
        """
        Remove one attachment.

        Parameters
        ----------
        attachment_path : Path | String
            The path of the attachment file

        Returns
        -------
        None.

        """
        self.attachments.remove(attachment_path)
        self.emit_removed(ElementType.ATTACHMENT_FILE, str(attachment_path), 'Attachments')
        log.info('Removed %s from the attachment list' % os.path.split(attachment_path)[-1])

    def add_optical_image(self, image: GenericOpticalImage | str | Path):
        if not isinstance(image, GenericOpticalImage):
            image = optical_image_factory.get_optical_image(image)
        try:
            self.optical_images.add(image)
            image.params['anchor'] = image.key
            self.emit_added(ElementType.OPTICAL_PIC, str(image.key), 'Optical images')
            log.info('Added %s to the optical images' % image.path.name)
        except autoerror.DuplicatedKey as e:
            log.warning(e)

    def remove_optical_image(self, image: str | Path):
        self.optical_images.remove(image)
        self.emit_removed(ElementType.OPTICAL_PIC, str(image), 'Optical images')
        log.info('Removed %s from the optical images' % Path(image).name)

    def add_sample(self, sample: Sample | str):
        """
        Add a new sample to the protocol.

        The sample name is guessed from the folder


        Parameters
        ----------
        sample : autologbook.Sample | str
            This is an instance of the autologbook.Sample or the full name of a new sample.

        Returns
        -------
        None.

        """
        # this is adding the sample to the sample dictionary.
        # the used key is the full name and should avoid problems with subsamples.
        # the add method of the sample dictionary will transform the string in a sample
        # object if need it.
        self.samples.add(sample)

        if isinstance(sample, str):
            # get the sample object back if we had a string as input
            sample = self.samples[sample]

        # the parent name is again a full_name or None if the current sample
        # is a top level sample.
        #
        # for the protocol editor we need to pass Samples in case of a top level
        # sample or the whole hierarchy.
        parent = sample.parent
        if parent is None:
            parent_name = 'Samples'
        else:
            parent_name = parent
            # make the parent sample aware that he got a child!
            if parent_name in self.samples:
                self.samples[parent_name].add_subsample(sample.full_name)
            else:
                self.samples.remove(sample)
                raise autoerror.ParentSampleError(f'Sample {sample.full_name} has a parent ({parent_name})'
                                                  ' not existing in protocol sample list.')

        self.emit_added(ElementType.SAMPLE, sample.full_name, parent_name)
        sample.signal_dispatcher.added_element.connect(
            self.signal_dispatcher.added_element)
        sample.signal_dispatcher.removed_element.connect(
            self.signal_dispatcher.removed_element)
        if parent is None:
            log.info('Added %s to the sample list' % sample.full_name)
        else:
            log.info('Added %s to the sample list under %s' %
                     (sample.last_name, parent_name))
        log.debug('At the moment there are %s samples in the list' % (
            len(self.samples)))

    def remove_sample(self, sample_full_name: str):
        """
        Remove one sample.

        Parameters
        ----------
        sample_full_name : str
            This is the sample full name

        Returns
        -------
        None.

        """
        if sample_full_name in self.samples:
            # check if this sample is a subsample of another one. if so remove it from its hierarchy.
            if self.samples[sample_full_name].parent:
                parent_name = self.samples[sample_full_name].parent
                log.debug('Removing subsample %s from its parent %s' % (sample_full_name, parent_name))
                if parent_name in self.samples:
                    self.samples[parent_name].remove_subsample(sample_full_name)
                    log.debug('Those are the remaining subsamples of %s' % parent_name)
                    for ssample in self.samples[parent_name].subsamples:
                        log.debug('-> %s' % ssample)
                else:
                    log.warning('Could not find parent sample (%s) for %s' %
                                (parent_name, self.samples[sample_full_name].last_name))
            else:
                parent_name = 'Samples'

            # now check if this sample has subsamples, if so, we need to remove these as well.
            for ssample in self.samples[sample_full_name].subsamples:
                self.remove_sample(ssample)

            # now remove all its items (pictures and videos)
            self.samples[sample_full_name].remove_all_microscope_pictures()
            self.samples[sample_full_name].remove_all_videos()
            self.samples[sample_full_name].remove_all_attachments()

            del self.samples[sample_full_name]
            self.emit_removed(ElementType.SAMPLE, sample_full_name, parent_name)

            log.info('Removed %s from the sample list' % sample_full_name)
            log.debug('At the moment there are %s samples in the list' % len(self.samples))
        else:
            log.warning('Attempt to remove %s from the sample list, but it was not there' % sample_full_name)

    def render_html(self):
        log.info('Rendering HTML code for protocol %s' % self.protocol)
        jinja_template = jinja_env.get_template(self.template)
        self.last_update = f'{datetime.now():%Y-%m-%d %H:%M:%S}'
        html_output = jinja_template.render(protocol=self)
        return html_output

    def recursive_append(self, sample_list: ResettableList):
        for sample in sample_list:
            self.ordered_sample_list.append(sample)
            self.recursive_append(self.samples[sample].subsamples)

    def get_ordered_sample_list(self) -> ResettableList:

        self.ordered_sample_list.clear()
        # first prepare a list with the top level samples
        top_level_sample_list = []
        for key, sample in self.samples.items():
            if sample.parent is None:
                top_level_sample_list.append(key)

        for sample in top_level_sample_list:
            self.ordered_sample_list.append(sample)
            self.recursive_append(self.samples[sample].subsamples)

        return self.ordered_sample_list

    def sanity_check(self):
        """
        Perform a sanity check on the protocol.

        When several images are added and removed quickly it is possible that
        the sample, subsample structure gets corrupted.

        This method along with the private _check_subsamples goes through all
        registered samples and sub-samples.

        TODO: this method can be improved.

        Returns
        -------
        None.

        """
        for full_name, sample in self.samples.items():
            if sample.parent is None:
                self._check_subsamples(sample.subsamples, sample)

    def _check_subsamples(self, sample_list: list, parent: Sample):
        for full_name in sample_list:
            if full_name not in self.samples:
                parent.subsamples.remove(full_name)
            else:
                if len(self.samples[full_name].subsamples) != 0:
                    self._check_subsamples(
                        self.samples[full_name].subsamples, self.samples[full_name])

    def print_html(self) -> str:
        """
        Print the HTML content.

        Returns
        -------
        Return a string of HTML

        """
        return self.render_html()

    def save_html_to_file(self, filename: str | Path):
        """
        Save th HTML to a file.

        Parameters
        ----------
        filename : str | Path
            The target file name

        Returns
        -------
        None.

        """
        log.debug('Saving HTML to file %s' % filename)
        with open(filename, 'w', encoding='utf-8') as fp:
            fp.write(self.print_html())


class ELOGProtocol(HTMLHelperMixin, Protocol):
    """Subclass of Protocol having information about ELOG."""

    def __init__(self, path: str | Path,
                 elog_connection_parameters: ELOGConnectionParameters = ELOGConnectionParameters.from_config_module(),
                 elog_logbook: str = None,
                 protocol: int | str = None,
                 project: str = None,
                 responsible: str = None,
                 yaml_filename: str | Path | None = None):

        super().__init__(path, protocol, project, responsible)

        # store the name of the logbook. it is used to retrieve a fresh elog handle from the factory and also for the
        # generation of the HTML page.
        self.elog_logbook = elog_logbook

        # elog interface
        elog_handle_factory.set_connection_parameters(elog_connection_parameters)

        # store the elog base url
        elog_handle = elog_handle_factory.get_logbook_handle(self.elog_logbook)
        self.elog_base_url = elog_handle.get_base_url()

        # store the connection parameters
        self.connection_parameters = elog_connection_parameters

        # store the msg_ids for the protocol. This list is either with a single entry for single page protocol, or a
        # list with all the message ids for multipage posts.
        # we will know these numbers only when the connection will be established
        self.elog_msg_id = []

        # initialize an empty dictionary for the ELOG attributes
        self.attributes = {
            'Protocol ID': self.protocol,
            'Project': self.project,
            'Customer': self.responsible,
            'Operator': elog_connection_parameters.elog_user,
            'Creation date': datetime.today().timestamp(),
            'Edit Lock': 'Unprotected'
        }

        self.template = 'protocol_base_template.yammy'

        # initialize the yaml engine for HTML customization
        self.initialize_yaml(yaml_filename)

    def get_protocol_url(self) -> str:
        """
        Get the ELOG protocol URL.

        If the protocol already got a message IDs, the parent page id is included in the URL,
        otherwise just the base path is returned

        Returns
        -------
        The ELOG protocol URL as a string.
        """
        if len(self.elog_msg_id):
            return f'{self.elog_base_url}/{self.elog_msg_id[0]}'
        return self.elog_base_url

    def initialize_yaml(self, yaml_filename):
        """
        Initialize the YAML customization tool.

        It looks for a yaml file in the protocol folder named according to the
        rule protocol-xxxxx.yaml where xxxxx is the protocol-id.

        If none is found than a new empty one is created, otherwise it is safely
        loaded and its content transferred to the yaml_dict

        Returns
        -------
        None.

        """
        # initialize the yaml_dict
        self.yamlDict = {}

        if yaml_filename is not None:
            if isinstance(yaml_filename, str):
                yaml_filename = Path(yaml_filename)

        if self.yamlFilename is None and yaml_filename is None:
            # the user didn't specify a custom yaml_filename and we didn't have any one before
            # so we need to assign the default one.
            self.yamlFilename = Path(self.path) / \
                                Path(f'protocol-{self.protocol}.yaml')

        if yaml_filename is not None:
            # if we are here it means that the user specified a yaml_filename to be used
            # then we have to use it.
            self.yamlFilename = yaml_filename

        if not self.yamlFilename.exists():
            log.info('No yaml file found, copying an empty one')
            with open(self.yamlFilename, 'w', encoding='utf-8') as file:
                file.write('#empty yaml file')

        with open(self.yamlFilename, 'rt', encoding='utf-8') as file:
            self.yamlDict = yaml.safe_load(file)
            if not self.yamlDict:
                # the file might be empty, then we need to set is as a dictionary
                self.yamlDict = {}
        log.info('Loaded yaml file %s' % self.yamlFilename.name)

        self.signal_dispatcher.added_element.emit(ElementType.YAML_FILE, '', '')

    def remove_from_yaml(self, key: str, force_dump: bool = False) -> None:
        """
        Remove an element from the YAML customization dictionary.

        This method looks if element is present in the YAML dictionary.
        If so, it deletes it, otherwise simply return

        Parameters
        ----------
        key : string
            The key of the element to be removed from the yaml dictionary

        force_dump : bool, optional
            If True, the yaml dictionary will be dumped to the file.
            The default is false.

        Returns
        -------
        None.

        """
        if key in self.yamlDict:
            del (self.yamlDict[key])
            log.debug('Removed %s from the yaml dictionary' % key)
            if force_dump:
                autotools.dump_yaml_file(self.yamlDict, self.yamlFilename)

    def remove_sample(self, sample: str):
        """
        Remove Sample overload.

        This overload method just implement the removal from the yaml
        customization dictionary.

        Parameters
        ----------
        sample : string
            Sample name to be removed.

        Returns
        -------
        None.

        """
        super().remove_sample(sample)
        self.remove_from_yaml(sample)

    @retry(retry=retry_if_exception_type(LogbookServerTimeout),
           reraise=True, stop=stop_after_attempt(autoconfig.ELOG_TIMEOUT_MAX_RETRY),
           wait=wait_fixed(autoconfig.ELOG_TIMEOUT_WAIT),
           after=after_log(log, logging.WARNING))
    def connect_to_elog(self):
        """
        Check the connection to the elog
        """
        elog_handle = elog_handle_factory.get_logbook_handle(self.elog_logbook)
        if not elog_handle.connection_verified:
            log.info('Checking connection to the ELOG server')
            try:
                elog_handle.check_connection()
                log.info('Connection to the eLOG server successfully established')
                elog_handle.connection_verified = True
            except LogbookServerTimeout as e:
                log.warning('Attempt to connect to the ELOG server failed due to timeout (%d s).'
                            ' New attempt in a few seconds' % autoconfig.ELOG_TIMEOUT)
                log.exception(e)
                raise LogbookServerTimeout
            except elog.LogbookAuthenticationError:
                log.critical('Logbook Authentication Error')
            except Exception as err:
                log.critical(
                    'Unable to establish a connection with the eLOG server. Here is the returned error message.')
                log.exception(err)

    @retry(retry=retry_if_exception_type(LogbookServerTimeout),
           reraise=True, stop=stop_after_attempt(autoconfig.ELOG_TIMEOUT_MAX_RETRY),
           wait=wait_fixed(autoconfig.ELOG_TIMEOUT_WAIT),
           after=after_log(log, logging.WARNING))
    def post_elog_message(self, skip_attachments: bool = False):  # noqa: C901
        """
        Post the protocol to the ELOG server.

        This method will do the following:
            1. Attempt a connection to the elog server
            2. Check if other entries with the same protocol number exist.
                2.1 If yes and if it is one, just delete it.
                2.2 If no, just go ahead.
                2.3 If yes and they are many, then raise an exception.
            3. Post a new entry with all the required attributes and the HTML
               content.


        Parameters
        ----------
        skip_attachments : Bool, optional
            Decide whether to post also attachment or not.
            Posting attachments maybe bandwidth heavy and it makes no sense
            while updating the protocol during the analysis. It is only meaningful
            at the end of the analysis.
            The default is False.

        Raises
        ------
        NameError
            Exception raised when more than one entry with the same protocol
            number is found already existing in the elog.

        Returns
        -------
        None.

        """
        elog_handle = elog_handle_factory.get_logbook_handle(self.elog_logbook)
        elog_handle.check_connection()
        # check if an entry with the same protocol id already exists
        protocol_ids = elog_handle.get_msg_ids(self.protocol)
        # render the protocol
        html_content = self.render_html()
        splitting_required = is_splitting_required(html_content)

        # empty page template
        empty_page_template = 'empty_page_template.yammy'

        if len(protocol_ids) > 1:
            hierarchy_ok, sorted_ids = elog_handle.verify_message_hierarchy(protocol_ids)
            if not hierarchy_ok:
                log.warning('An inconsistency has been found with the message hierarchy of %s' % self.protocol)
                log.warning('The following messages are involved %s' % protocol_ids)
                log.warning('Fix this problem manually before continuing.')
                raise autoerror.InvalidHierarchy
            else:
                protocol_ids = sorted_ids

            for msg_id in protocol_ids[1:]:
                elog_handle.post(jinja_env.get_template(empty_page_template).render(protocol=self),
                                 msg_id=msg_id, reply=False, attributes=self.attributes, attachments=[],
                                 encoding='HTML', timeout=autoconfig.ELOG_TIMEOUT)

        attachments = []
        if skip_attachments:
            attachments = []
        else:
            # please load only not empty attachments.
            # first project wide attachments
            for att in self.attachments.get_upload_attachments():
                if os.stat(att).st_size:
                    attachments.append(att)

            # then sample specific attachments
            for sample in self.samples.values():
                for att in sample.attachments.get_upload_attachments():
                    if os.stat(att).st_size:
                        attachments.append(att)

            if len(attachments) > autoconfig.MAX_ATTACHMENTS:
                attachments = attachments[:autoconfig.MAX_ATTACHMENTS]
                log.warning('ELOG allows a maximum of %s attachments for entry. Appending only the first ones')

        if not splitting_required:
            msg_id = None
            self.elog_msg_id = []
            if protocol_ids:
                msg_id = protocol_ids[0]
            try:
                self.elog_msg_id.append(elog_handle.post(html_content, msg_id=msg_id, reply=False,
                                                         attributes=self.attributes,
                                                         attachments=attachments,
                                                         encoding='HTML',
                                                         timeout=autoconfig.ELOG_TIMEOUT))
                log.info('Successfully posted ELOG entry for protocol %s' % self.protocol)
            except elog.LogbookAuthenticationError as e:
                log.exception('Logbook error', e)
            except elog.LogbookMessageRejected as e:
                # this exception used to be thrown in case of a too large message. Now it should not happen anymore,
                # but it is wise to catch it here and inform the user.
                log.critical('ELOG Message was rejected!')
        else:
            # ok split the post
            log.info('Splitting original post in subpages')
            elog_post_splitter = ELOGPostSplitter(html_content)
            if elog_post_splitter.num_of_pages == len(protocol_ids):
                # we have just enough post
                pass
            elif elog_post_splitter.num_of_pages > len(protocol_ids):
                # we have more pages than already existing posts.
                # we need to create more
                while len(protocol_ids) < elog_post_splitter.num_of_pages:
                    try:
                        protocol_ids.append(
                            elog_handle.post(jinja_env.get_template(empty_page_template).render(protocol=self),
                                             reply=True, msg_id=protocol_ids[0],
                                             attributes=self.attributes, encoding='HTML',
                                             timeout=autoconfig.ELOG_TIMEOUT))
                    except elog.LogbookAuthenticationError as e:
                        log.exception('Logbook error', e)

            else:  # elog_post_splitter.num_of_pages < len(protocol_ids)
                # we have more existing posts than required pages.
                # the extra posts have been already reset to empty message,
                # we just need to limit the size of real_ids, and we leave the empty messages
                protocol_ids = protocol_ids[:elog_post_splitter.num_of_pages]

            # rebuild the index of the post splitter
            elog_post_splitter.rebuild_index(base_url=self.elog_base_url, logbook=self.elog_logbook,
                                             port=elog_handle.get_connection_parameters().elog_port,
                                             msg_ids=protocol_ids)
            # now we are ready to post
            self.elog_msg_id = []
            for i, page in enumerate(elog_post_splitter.get_all_pages()):
                attachments = []
                if page._type in [ELOGPageType.ELOGIntroConclusionType, ELOGPageType.ELOGIntroOpticalConclusionType,
                                  ELOGPageType.ELOGConclusionPageType]:
                    if not skip_attachments:
                        # we attach generic attachments here:
                        for att in self.attachments.get_upload_attachments():
                            if os.stat(att).st_size:
                                attachments.append(att)
                elif page._type in [ELOGPageType.ELOGSamplePageType, ELOGPageType.ELOGCombinedSamplePageType]:
                    if not skip_attachments:
                        # we attach here sample specific attachments.
                        if page._type == ELOGPageType.ELOGSamplePageType:
                            sample_name_list = [page.sample_name]
                        else:
                            sample_name_list = page.sample_name_list

                        for sample_name in sample_name_list:
                            sample = self.samples[sample_name]
                            for att in sample.attachments.get_upload_attachments():
                                if os.stat(att).st_size:
                                    attachments.append(att)

                try:
                    self.elog_msg_id.append(
                        elog_handle.post(page.get_html(), msg_id=page._message_id, reply=False,
                                         attributes=self.attributes,
                                         attachments=attachments, encoding='HTML',
                                         timeout=autoconfig.ELOG_TIMEOUT))
                    log.info('Successfully posted eLog entry for protocol %s page %s of %s' %
                             (self.protocol, i + 1, elog_post_splitter.num_of_pages))

                except elog.LogbookMessageRejected:
                    log.critical('ELOG Message too large, the attempt of splitting the post failed.')
                    log.critical('Page number %s of type %s is too big. Fix the content manually and try again' %
                                 (page.page_number + 1, page._type))
                    log.critical('Failed to post eLOG entry for protocol %s page %s of %s' %
                                 (self.protocol, i + 1, elog_post_splitter.num_of_pages))
                except elog.LogbookAuthenticationError as e:
                    log.exception('Logbook error', e)
        self.write_url_file()

    def write_url_file(self):
        p = r'.*[\d]{8}T[\d]{6}_elog_webpage.url'
        for url_file in autotools.reglob(self.path, matching_regexes=p, ignore_regexes=None):
            Path(url_file).unlink(missing_ok=True)

        if len(self.elog_msg_id):
            filename = self.path / Path(f'{datetime.now():%Y%m%dT%H%M%S}_elog_webpage.url')
            with open(filename, 'w', newline='\r\n') as url_file:
                url_file.write(f'[InternetShortcut]\nURL={self.get_protocol_url()}')


class QuattroELOGProtocol(ELOGProtocol):
    """
    Subclass of the ELOGProtocol dedicated to the Quattro Microscope.

    This subclass implements all the specificities of the Quattro in particular
    the presence of navigation camera images.

    """

    def __init__(self, path: str | Path,
                 elog_connection_parameters: ELOGConnectionParameters = ELOGConnectionParameters.from_config_module(),
                 elog_logbook: str = autoconfig.QUATTRO_LOGBOOK,
                 protocol: int | str = None,
                 project: str = None,
                 responsible: str = None,
                 yaml_filename: str | Path | None = None):

        super().__init__(path, elog_connection_parameters, elog_logbook, protocol, project, responsible, yaml_filename)

        # initialize the navigation camera image list
        self.navcamimages = NavigationImagesList()
        self.navcam_thumb_max_width = autoconfig.IMAGE_NAVIGATION_MAX_WIDTH

        self.protocol_type = 'QuattroProtocol'
        self.template = 'quattro_protocol_template.yammy'

    def add_navigation_camera_image(self, path: Path | str):
        """
        Add a navigation camera image at the Protocol.

        Parameters
        ----------
        path : path-like | string
            The path of the navigation image file.

        Returns
        -------
        None.

        """
        self.navcamimages.append(path)
        log.info('Added %s to the navcam list' % path)
        log.debug('At the moment there are %s pictures in the navcam list' % len(self.navcamimages))
        self.emit_added(ElementType.NAVIGATION_PIC, str(path), 'Navigation Images')

    def remove_navigation_camera_image(self, path: Path | str):
        """
        Remove one navigation camera image file.

        The navigation camera is also removed from the YAML customization
        dictionary if it was present.

        Parameters
        ----------
        path : Path | String
            The path of the navigation image file.

        Returns
        -------
        None.

        """
        if isinstance(path, Path):
            path = str(path)
        if path in self.navcamimages:
            self.navcamimages.remove(path)
            log.info('Removed %s to the navcam list' % path)
            log.debug('At the moment there are %s pictures in the navcam list' % len(self.navcamimages))
            self.emit_removed(ElementType.NAVIGATION_PIC, path, 'Navigation Images')
            self.remove_from_yaml(path)
        else:
            log.warning('Attempt to remove %s from the navcam list, but it was not there' % path)


class MultiMicroscopeELOGProtocol(QuattroELOGProtocol):
    def __init__(self, path: str | Path,
                 elog_connection_parameters: ELOGConnectionParameters = ELOGConnectionParameters.from_config_module(),
                 elog_logbook: str = autoconfig.QUATTRO_LOGBOOK,
                 protocol: int | str = None,
                 project: str = None,
                 responsible: str = None,
                 yaml_filename: str | Path | None = None):
        super().__init__(path, elog_connection_parameters, elog_logbook, protocol, project, responsible, yaml_filename)

        self.protocol_type = 'MultiMicroscopeProtocol'
        self.template = 'multi_microscope_protocol_template.yammy'


class VersaELOGProtocol(ELOGProtocol):
    """
    Subclass of the ELOGProtocol dedicated to the Versa Microscope.

    This subclass implements all the specificities of the Versa.
    """

    def __init__(self, path: str | Path,
                 elog_connection_parameters: ELOGConnectionParameters = ELOGConnectionParameters.from_config_module(),
                 elog_logbook: str = autoconfig.VERSA_LOGBOOK,
                 protocol: int | str = None,
                 project: str = None,
                 responsible: str = None,
                 yaml_filename: str | Path | None = None):
        super().__init__(path, elog_connection_parameters, elog_logbook, protocol, project, responsible, yaml_filename)
        self.protocol_type = 'VersaProtocol'


class VegaELOGProtocol(ELOGProtocol):
    """
    Subclass of the ELOGProtocol dedicated to the Vega Microscope.

    This subclass implements all the specificities of the Vega microscope.

    """

    def __init__(self, path: str | Path,
                 elog_connection_parameters: ELOGConnectionParameters = ELOGConnectionParameters.from_config_module(),
                 elog_logbook: str = autoconfig.VEGA_LOGBOOK,
                 protocol: int | str = None,
                 project: str = None,
                 responsible: str = None,
                 yaml_filename: str | Path | None = None):
        super().__init__(path, elog_connection_parameters, elog_logbook, protocol, project, responsible, yaml_filename)
        self.protocol_type = 'VegaProtocol'


class XL40ELOGProtocol(ELOGProtocol):
    """
    Subclass of the ELOGProtocol dedicated to the XL40 Microscope.

    This subclass implements all the specificities of the XL40 microscope.

    """

    def __init__(self, path: str | Path,
                 elog_connection_parameters: ELOGConnectionParameters = ELOGConnectionParameters.from_config_module(),
                 elog_logbook: str = autoconfig.XL40GB_LOGBOOK,
                 protocol: int | str = None,
                 project: str = None,
                 responsible: str = None,
                 yaml_filename: str | Path | None = None):
        super().__init__(path, elog_connection_parameters, elog_logbook, protocol, project, responsible, yaml_filename)
        self.protocol_type = 'XL40Protocol'
