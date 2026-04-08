# -*- coding: utf-8 -*-
"""
A module containing Qt Workers to execute operations in detached threads.

Communication between workers can be obtained using the Signal / Slot mechanism.
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
import logging
import re
import threading
from pathlib import Path

import watchdog.events
import watchdog.observers
from PyQt5 import QtCore

from autologbook import autoconfig, autoerror, autoprotocol, autotools, autowatchdog
from autologbook.elog_interface import ELOGConnectionParameters

Signal = QtCore.pyqtSignal
Slot = QtCore.pyqtSlot
log = logging.getLogger('__main__')

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'


class Worker(QtCore.QObject):
    """
    A Worker class derived from QObject.

    This class will be performing the real job.
    It will be moved to a separate Thread in order to leave the original thread responsible only of the user interface.

    """

    # signal informing about the worker running status
    worker_is_running = Signal(bool, name='work_is_running')

    def __init__(self, parent=None):
        """
        Build an instance of a generic worker.

        It sets its parent and call the super constructor

        Parameters
        ----------
        parent : Object, optional
            The parent object.

        Returns
        -------
        None.

        """
        # The parent is the main window
        self.parent = parent

        self.running = False

        # a list with the required parameters
        self.required_parameters = []

        # a dictionary with the actual parameters
        self.params = {}

        super().__init__(parent=parent)

    def update_parameters(self, *args, **kwargs):
        """
        Transfer the execution parameters from the GUI to the worker Thread.

        All keyword arguments are already provided in the code but can be overridden here

        Keyword arguments
        ------------------

        elog_hostname: STRING
            The FQDN of the elog server including the protocol. For example https://10 .166.16.24

        elog_port: INTEGER
            The numeric value of the port where there elog server is listening.

        elog_user: STRING
            The username connecting to the logbook.

        elog_password: STRING
            The password to connect to the logbook in plain text

        Returns
        -------
        None.

        """
        # check if all required parameters are transmitted
        for param in self.required_parameters:
            if param in kwargs:
                self.params[param] = kwargs[param]
            else:
                log.error('Missing %s. Cannot update worker parameters' % param)
                raise autoerror.MissingWorkerParameter(f'Missing {param}.')

    @Slot()
    def toggle(self):
        """
        Toggle the status of the watchdog.

        The watchdog pushbutton on the GUI should have a toggle mechanical
        function instead of a pushbutton one.

        Using this slot we are mimicking the same mechanical behaviour.

        This is actually the only slot that should be connected to the GUIThread
        receiving the start/stop signal.

        Returns
        -------
        None.

        """
        if self.running:
            self.running = False
            self.stop()
        else:
            self.running = True
            self.start()

    def start(self):
        """Abstract start method. """
        pass

    def stop(self):
        """Abstract stop method. """
        pass


class SingleWatchdogWorker(Worker):
    """
    Specialized worker taking care of mirroring and logbook generation.

    The mirroring function is only optional.
    """

    def __init__(self, parent=None):
        """
        Build an instance of a FSWatchdogWorker.

        Parameters
        ----------
        parent : Object, optional
            The parent object. The default is None.
            In normal circumstances this is the Main Window

        Returns
        -------
        None.
        """

        # call the worker init
        super().__init__(parent=parent)

        # list of required parameters
        self.required_parameters.extend([
            'original_path',  # this the where the microscope software is saving the images.
            'destination_path',  # this is where the mirroring component has to copy the files
            'is_mirroring_requested',  # a flag to specify whether the mirroring is required or not
            'microscope',  # this is the microscope type
            'projectID',  # this is the project ID aka protocol number
            'project_name',  # this is the project name
            'responsible'  # this is the project responsible
        ])

        # this is the reference to the protocol instance
        self.autoprotocol_instance = None

        # this is the reference to the event handler
        self.autologbook_event_handler = None

        # this is the reference to the watchdog observer
        self.watchdog_observer = None

    def update_parameters(self, *args, **kwargs):
        """
        Transfer the execution parameters from the GUI to the SingleWatchdogWorker.

        Keywords parameter
        ------------------
        original_path : Path-like or string
            The source path of the mirroring

        destination_path : Path-like or string
            The destination path of the mirroring

        is_mirroring_requested : Bool
            A boolean flag to ask for mirroring or not

        microscope : string
            The name of the microscope. This will affect the subclass of ELOGProtocol and
            ELOGProtocolEventHandler. Possible values are:
                Quattro : for the Thermofisher Quattro S.
                Versa : for the Thermofisher Versa 3D FIB
                Vega : for the Tescan VEGA
                XL40-Cold and XL40-GB: for the Philips XL40 family
        projectID : string or None
            The customized protocol ID. Use None if you want to have it guessed from the
            folder name.

        project_name : string or None
            The project name for the protocol. Use None if you want to have it guessed from the
            folder name.

        responsible : string or None
            The name of the responsible for the experiment. Use None if you want to have it guessed from the
            folder name.

        Those parameters are sent to the worker everytime the enable_watchdog is set,
        and this is happening if and only if the validate_inputs is returning true

        Raises:
        -------
        MissingWorkerParameter if a parameter is missing in the kwargs.

        Returns
        -------
        None.

        """
        # call the super method
        # the super method will loop over all required parameters and transfer their
        # value from the kwargs to the params dictionary.
        super().update_parameters(*args, **kwargs)

        # if mirroring is requested we need to apply a trick to have the right folder where the yaml_filename is-
        if self.params['is_mirroring_requested']:
            where = 'original_path'
        else:
            where = 'destination_path'

        if self.params['projectID'] is None:
            # if the projectID is None, it means that it will be guessed afterwards, but we have to do it now for the
            # yaml_filename
            folder = self.params['destination_path'].parts[-1]
            pattern = '^#*([\\d]+)\\s*[-_]\\s*([\\w\\W]+)\\s*[-_]\\s*([\\w\\W]+)$'
            match = re.search(pattern, folder)
            if match:
                project_id = match.group(1)
            else:
                project_id = 'unknown'
        else:
            project_id = self.params['projectID']

        yaml_filename = self.params[where] / Path(f'protocol-{project_id}.yaml')

        microscope_logbook_lut: dict[str, str] = {
            'Quattro': autoconfig.QUATTRO_LOGBOOK,
            'Versa': autoconfig.VERSA_LOGBOOK,
            'Vega': autoconfig.VEGA_LOGBOOK,
            'XL40-GB': autoconfig.XL40GB_LOGBOOK,
            'XL40-Cold': autoconfig.XL40COLD_LOGBOOK

        }

        self.autoprotocol_instance = autoprotocol.MultiMicroscopeELOGProtocol(
            path=self.params['destination_path'],  # REMEMBER: the destination_path is on the image server
            elog_connection_parameters=ELOGConnectionParameters.from_config_module(),
            elog_logbook=microscope_logbook_lut[self.params['microscope']],
            protocol=self.params['projectID'],
            project=self.params['project_name'],
            responsible=self.params['responsible'],
            yaml_filename=yaml_filename
        )
        self.autologbook_event_handler = autowatchdog.MultiMicroscopeELOGProtocolEventHandler(
            autoprotocol_instance=self.autoprotocol_instance, **self.params)

        # connect the autoprotocol_instance signal_dispatcher to the main window proxy signals
        self.autoprotocol_instance.signal_dispatcher.added_element.connect(
            self.parent.added_element.emit)
        self.autoprotocol_instance.signal_dispatcher.removed_element.connect(
            self.parent.removed_element.emit)
        # we are ready to start. Just wait the start signal!

    @Slot()
    def start(self):
        """
        Start the SingleWatchdogWorker.

        A new Observer instance is generated everytime this slot is called,
        scheduled to work with an autologbookEventHandler and started.

        All the already existing items in the monitored path are also processed.

        IMPORTANT NOTE
        --------------
        Never call this slot directly, but always pass via the toggle slot to
        transform the start watchdog push button in a start/stop toggle switch.

        Returns
        -------
        None.

        """
        # inform the GUI that we have started working
        self.worker_is_running.emit(True)

        # rename the thread
        threading.current_thread().name = autotools.ctname()
        log.info('Starting protocol watchdog')

        # it's time to have an observer. It is important that a fresh observer is
        # created every time the worker is started, because otherwise the observer
        # won't be able to restart.
        self.watchdog_observer = watchdog.observers.Observer(autoconfig.AUTOLOGBOOK_WATCHDOG_TIMEOUT)
        self.watchdog_observer.schedule(self.autologbook_event_handler,
                                        path=self.params['original_path'], recursive=True)

        # get a reference of the observer.event_queue attached to the handler.
        # it is useful for advance operations.
        self.autologbook_event_handler.set_queue_reference(self.watchdog_observer.event_queue)
        # Append Obs to the thread name
        self.watchdog_observer.name = f'{autotools.ctname()}Obs'

        # remember to reset the MicroscopePicture IDs
        autoprotocol.MicroscopePicture._reset_ids()

        # reset the protocol content. this is useful if we are just restarting a watchdog
        # without having changed any worker parameters. After that emit the reset content signal
        # from the MainWindow so that the ProtocolEditor will refresh its view.
        self.autoprotocol_instance.clear_resettable_content()
        self.parent.reset_content.emit()

        # process existing items
        self.autologbook_event_handler.process_already_existing_items()

        # ask the main window to update the protocol list
        self.parent.update_microscopy_protocol_list(status='On going')

        # now start to look for new files
        self.watchdog_observer.start()

        # this will start the observer thread and also one or more event emitter threads.
        # for the sake of clarity, I'm renaming the emitter threads to something more
        # understandable
        for count, emitter in enumerate(list(self.watchdog_observer.emitters)):
            emitter.name = f'{autotools.ctname()}Emi{count}'

    @Slot()
    def stop(self):
        """
        Stop the SingleWatchdog.

        A stop signal is sent to the observer so that is not queuing any more
        events.

        The join statement assures that all currently present event in the queue
        are still dispatched.

        The HTML content of the autologbook is generated for the last time and
        since the queue is empty it will also be posted to the ELOG server this
        time with all attachments.

        Finally, a signal is sent back to the GUIThread to inform it that the
        watchdog process is finished and the status of the inputs can be changed.

        IMPORTANT NOTE
        --------------
        Never call this slot directly, but always pass via the toggle slot to
        transform the start watchdog push button in a start/stop toggle switch.

        Returns
        -------
        None.

        """
        # stop the observer
        self.watchdog_observer.stop()

        # wait until the observer is finished
        self.watchdog_observer.join()

        # for the last time generate the HTML and post it with all the attachments
        self.autoprotocol_instance.post_elog_message(skip_attachments=False)

        # inform the GUI that we have finished our task.
        self.worker_is_running.emit(False)

        # ask the main window to update the protocol list
        self.parent.update_microscopy_protocol_list(status='Finished')
