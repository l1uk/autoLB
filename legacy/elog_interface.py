from __future__ import annotations
"""ELOG integration layer for SEM session logbook operations.

This module encapsulates connection parameter handling, logbook handle
construction/caching, and higher-level helpers for querying and validating
message structures in ELOG instances used by autologbook.

Main exported classes:
    ELOGConnectionParameters: Value object for ELOG connection settings.
    ELOGHandleFactory: Factory/cache for microscope-specific logbook handles.
    AdvLogbook: Extended ``elog.Logbook`` with protocol-oriented helpers.
    AnalysisLogbook: ``AdvLogbook`` specialization for analysis entries.
    ListLogbook: ``AdvLogbook`` specialization for protocol list entries.

Relevant dependencies:
    - py_elog (imported as ``elog``): communication with ELOG servers.
    - PyQt5 ``QSettings``: extraction of persisted GUI connection settings.
    - ``autologbook.autoconfig``: static project configuration defaults.
    - ``autologbook.autoerror``: project-specific exception types.
"""

import elog
import configparser
from PyQt5.QtCore import QSettings
from autologbook import autoconfig, autoerror
import logging

log = logging.getLogger('__main__')


class ELOGConnectionParameters:
    """Container for ELOG connection settings.

    Inheritance:
        Direct subclass of ``object`` used as a plain data container.

    Attributes:
        elog_hostname (str): ELOG server hostname.
        elog_port (int): ELOG server port.
        elog_user (str): ELOG username.
        elog_password (str): ELOG password.
        elog_use_ssl (bool): Whether SSL is enabled.
        elog_encrypt_pwd (bool): Whether password encryption is requested.

    Example:
        >>> params = ELOGConnectionParameters(
        ...     hostname="elog.example.org",
        ...     port=8080,
        ...     user="operator",
        ...     password="secret",
        ...     use_ssl=True,
        ... )
        >>> params.to_dict()["hostname"]
        'elog.example.org'
    """

    def __init__(self, hostname: str, port: int, user: str, password: str, use_ssl: bool,
                 encrypt_pwd: bool = False, *args, **kwargs):
        """Initialize connection parameters.

        Args:
            hostname (str): ELOG server hostname.
            port (int): ELOG server port.
            user (str): ELOG username.
            password (str): ELOG password.
            use_ssl (bool): Whether to use SSL.
            encrypt_pwd (bool): Whether to request encrypted password handling.
                Defaults to ``False``.
            *args: Ignored positional arguments for compatibility.
            **kwargs: Ignored keyword arguments for compatibility.

        Returns:
            None

        Raises:
            None

        Example:
            >>> ELOGConnectionParameters("host", 8080, "u", "p", False)
            <autologbook.elog_interface.ELOGConnectionParameters object ...>
        """
        self.elog_hostname = hostname
        self.elog_port = port
        self.elog_user = user
        self.elog_password = password
        self.elog_use_ssl = use_ssl
        self.elog_encrypt_pwd = encrypt_pwd

    @classmethod
    def from_configuration(cls, config: configparser.ConfigParser) -> ELOGConnectionParameters:
        """Build parameters from a ``ConfigParser`` instance.

        Args:
            config (configparser.ConfigParser): Configuration with an ``elog``
                section containing connection keys.

        Returns:
            ELOGConnectionParameters: New parameter instance from configuration.

        Raises:
            KeyError: If required keys in the ``elog`` section are missing.
            ValueError: If typed conversion for configured values fails.

        Example:
            >>> import configparser
            >>> cfg = configparser.ConfigParser()
            >>> cfg.read_dict({"elog": {
            ...     "elog_hostname": "host",
            ...     "elog_port": "8080",
            ...     "elog_user": "u",
            ...     "elog_password": "p",
            ...     "use_ssl": "false",
            ... }})
            >>> ELOGConnectionParameters.from_configuration(cfg).elog_port
            8080
        """
        return cls(
            hostname=config['elog']['elog_hostname'],
            port=config.getint('elog', 'elog_port'),
            user=config['elog']['elog_user'],
            password=config['elog']['elog_password'],
            use_ssl=config.getboolean('elog', 'use_ssl'),
            encrypt_pwd=False)

    @classmethod
    def from_qsettings(cls, settings: QSettings) -> ELOGConnectionParameters:
        """Build parameters from persisted Qt settings.

        Args:
            settings (QSettings): Qt settings object containing ELOG fields.

        Returns:
            ELOGConnectionParameters: New parameter instance from QSettings.

        Raises:
            TypeError: If values cannot be converted to expected types.
            ValueError: If numeric conversion (for example, port) fails.

        Example:
            >>> from PyQt5.QtCore import QSettings
            >>> s = QSettings("org", "app")
            >>> _ = s.setValue("elog_port", 8080)
            >>> isinstance(ELOGConnectionParameters.from_qsettings(s), ELOGConnectionParameters)
            True
        """
        return cls(
            hostname=settings.value('elog_hostname'),
            port=int(settings.value('elog_port', defaultValue=8080)),
            user=settings.value('elog_user_name'),
            password=settings.value('elog_password'),
            use_ssl=bool(settings.value('elog_use_ssl')),
            encrypt_pwd=False
        )

    @classmethod
    def from_config_module(cls) -> ELOGConnectionParameters:
        """Build parameters from values in ``autoconfig``.

        Args:
            None

        Returns:
            ELOGConnectionParameters: New parameter instance from module-level
            project configuration constants.

        Raises:
            AttributeError: If expected constants are missing in
                ``autologbook.autoconfig``.

        Example:
            >>> params = ELOGConnectionParameters.from_config_module()
            >>> isinstance(params.elog_hostname, str)
            True
        """
        return cls(
            hostname=autoconfig.ELOG_HOSTNAME,
            port=autoconfig.ELOG_PORT,
            user=autoconfig.ELOG_USER,
            password=autoconfig.ELOG_PASSWORD,
            use_ssl=autoconfig.USE_SSL,
            encrypt_pwd=False
        )

    def to_dict(self) -> dict:
        """Return parameters as keyword-argument dictionary.

        Args:
            None

        Returns:
            dict: Mapping consumable by ``elog.Logbook`` constructors.

        Raises:
            None

        Example:
            >>> ELOGConnectionParameters("h", 8080, "u", "p", False).to_dict()["port"]
            8080
        """
        return {
            'hostname': self.elog_hostname,
            'port': self.elog_port,
            'user': self.elog_user,
            'password': self.elog_password,
            'use_ssl': self.elog_use_ssl,
            'encrypt_pwd': self.elog_encrypt_pwd
        }

    def __eq__(self, other):
        """Compare two parameter objects by stored fields.

        Args:
            other (Any): Object to compare against.

        Returns:
            bool: ``True`` when all stored fields are identical.

        Raises:
            AttributeError: If ``other`` does not expose a compatible
                ``__dict__`` layout.

        Example:
            >>> a = ELOGConnectionParameters("h", 8080, "u", "p", False)
            >>> b = ELOGConnectionParameters("h", 8080, "u", "p", False)
            >>> a == b
            True
        """
        identical = True
        for key in self.__dict__:
            identical = identical and self.__dict__[key] == other.__dict__[key]
        return identical


class ELOGHandleFactory:
    """Factory and cache for ELOG logbook handles.

    Inheritance:
        Direct subclass of ``object`` managing ``AdvLogbook`` instances.

    Attributes:
        _elog_connection_parameters (ELOGConnectionParameters | None): Active
            connection settings used for newly created handles.
        _existing_handles (dict[str, AdvLogbook]): Cache of handles per logbook
            name.

    Example:
        >>> factory = ELOGHandleFactory(ELOGConnectionParameters.from_config_module())
        >>> handle = factory.get_logbook_handle("analysis")
        >>> isinstance(handle, AdvLogbook)
        True
    """

    def __init__(self, connection_parameters: ELOGConnectionParameters = None):
        """Initialize the handle factory.

        Args:
            connection_parameters (ELOGConnectionParameters, optional): Initial
                ELOG connection parameters. Defaults to ``None``.

        Returns:
            None

        Raises:
            None

        Example:
            >>> ELOGHandleFactory()
            <autologbook.elog_interface.ELOGHandleFactory object ...>
        """
        self._elog_connection_parameters = connection_parameters
        self._existing_handles = dict()

    def set_connection_parameters(self, connection_parameters: ELOGConnectionParameters):
        """Update connection parameters and invalidate cached handles.

        Args:
            connection_parameters (ELOGConnectionParameters): New connection
                parameters.

        Returns:
            None

        Raises:
            None

        Example:
            >>> f = ELOGHandleFactory()
            >>> f.set_connection_parameters(ELOGConnectionParameters("h", 8080, "u", "p", False))
        """
        if self._elog_connection_parameters != connection_parameters:
            self._elog_connection_parameters = connection_parameters
            self._existing_handles.clear()

    def get_logbook_handle(self, logbook: str) -> AdvLogbook:
        """Return a cached or newly constructed logbook handle.

        Args:
            logbook (str): Target logbook name.

        Returns:
            AdvLogbook: ``ListLogbook`` for protocol list logbook, otherwise
            ``AnalysisLogbook``.

        Raises:
            AttributeError: If connection parameters are not set.

        Example:
            >>> f = ELOGHandleFactory(ELOGConnectionParameters.from_config_module())
            >>> h = f.get_logbook_handle("my-logbook")
            >>> isinstance(h, AdvLogbook)
            True
        """
        if logbook in self._existing_handles:
            return self._existing_handles[logbook]
        else:
            if logbook == autoconfig.PROTOCOL_LIST_LOGBOOK:
                class_ = ListLogbook
            else:
                class_ = AnalysisLogbook
            new_handle = class_(**self._elog_connection_parameters.to_dict(), logbook=logbook)
            self._existing_handles[logbook] = new_handle
            return new_handle


elog_handle_factory = ELOGHandleFactory(ELOGConnectionParameters.from_config_module())


class AdvLogbook(elog.Logbook):
    """Extended ELOG logbook with protocol-centric helper operations.

    Inheritance:
        Subclass of ``elog.Logbook`` adding connection state tracking and
        project-specific utility methods.

    Attributes:
        timeout (int | float): Default timeout used for ELOG API calls.
        protocol_id_key (str): Attribute key used to identify protocol IDs.
        _connection_verified (bool): Flag indicating successful connection
            validation.
        _connection_parameters (ELOGConnectionParameters): Parameters used to
            build this handle.

    Example:
        >>> params = ELOGConnectionParameters.from_config_module()
        >>> lb = AdvLogbook(logbook="analysis", **params.to_dict())
        >>> isinstance(lb.get_connection_parameters(), ELOGConnectionParameters)
        True
    """

    timeout = autoconfig.ELOG_TIMEOUT
    protocol_id_key = ''

    def __init__(self, hostname: str, port: int, user: str, password: str, use_ssl: bool, encrypt_pwd: bool,
                 logbook: str = None, *args, **kwargs):
        """Initialize an advanced logbook handle.

        Args:
            hostname (str): ELOG server hostname.
            port (int): ELOG server port.
            user (str): ELOG username.
            password (str): ELOG password.
            use_ssl (bool): Whether SSL is enabled.
            encrypt_pwd (bool): Whether to encrypt the password in transport.
            logbook (str, optional): Target logbook name.
            *args: Forwarded positional arguments for ``elog.Logbook``.
            **kwargs: Forwarded keyword arguments for ``elog.Logbook``.

        Returns:
            None

        Raises:
            elog.LogbookError: Propagated from the base class constructor.

        Example:
            >>> p = ELOGConnectionParameters.from_config_module()
            >>> AdvLogbook(logbook="analysis", **p.to_dict())
            <autologbook.elog_interface.AdvLogbook object ...>
        """
        super().__init__(hostname=hostname, logbook=logbook, port=port, user=user, password=password, use_ssl=use_ssl,
                         encrypt_pwd=encrypt_pwd, *args, **kwargs)
        self._connection_verified = False
        self._connection_parameters = ELOGConnectionParameters(hostname, port, user, password, use_ssl, encrypt_pwd)

    def get_connection_parameters(self) -> ELOGConnectionParameters:
        """Return connection parameters used by this handle."""
        return self._connection_parameters

    @property
    def connection_verified(self) -> bool:
        """bool: Whether the connection was validated successfully."""
        return self._connection_verified

    @connection_verified.setter
    def connection_verified(self, status: bool):
        """Set connection verification status."""
        self._connection_verified = status

    def get_base_url(self) -> str:
        """Return the base ELOG URL without a trailing slash."""
        return self._url.rstrip('/')

    def get_msg_ids(self, protocol_id: int | str) -> list[int]:
        """Return all message IDs matching an exact protocol identifier.

        Args:
            protocol_id (int | str): Protocol identifier to match.

        Returns:
            list[int]: Message IDs whose ``protocol_id_key`` attribute equals
            ``protocol_id``.

        Raises:
            elog.LogbookError: If ELOG search/read operations fail.
            KeyError: If expected protocol attribute is missing in a message.

        Example:
            >>> lb = elog_handle_factory.get_logbook_handle("analysis")
            >>> isinstance(lb.get_msg_ids("42"), list)
            True
        """

        log.info('Getting message IDs for this protocol entry')
        msg_ids = self.search({self.protocol_id_key: protocol_id}, timeout=self.timeout)
        real_ids = list()

        for msg_id in msg_ids:
            _, attributes, __ = self.read(msg_id, timeout=self.timeout)

            if attributes[self.protocol_id_key] == protocol_id:
                real_ids.append(msg_id)

        return real_ids

    def check_connection(self):
        """Validate server access by requesting the latest message ID.

        Args:
            None

        Returns:
            None

        Raises:
            elog.LogbookError: If the connectivity check fails.

        Example:
            >>> lb = elog_handle_factory.get_logbook_handle("analysis")
            >>> lb.check_connection()
        """
        try:
            self.get_last_message_id(timeout=self.timeout)
            self._connection_verified = True
        except elog.LogbookError as e:
            self._connection_verified = False
            raise e

    def refresh(self) -> AdvLogbook:
        """Return a refreshed handle for the same logbook name.

        Args:
            None

        Returns:
            AdvLogbook: Current factory-managed handle for ``self.logbook``.

        Raises:
            AttributeError: If no valid factory connection parameters are set.

        Example:
            >>> lb = elog_handle_factory.get_logbook_handle("analysis")
            >>> isinstance(lb.refresh(), AdvLogbook)
            True
        """
        return elog_handle_factory.get_logbook_handle(self.logbook)



class AnalysisLogbook(AdvLogbook):
    """Advanced logbook implementation for SEM analysis entries.

    Inheritance:
        Subclass of ``AdvLogbook`` specialized for analysis logbooks where
        protocol references are stored under ``Protocol ID``.

    Attributes:
        protocol_id_key (str): Fixed to ``'Protocol ID'``.

    Example:
        >>> params = ELOGConnectionParameters.from_config_module()
        >>> lb = AnalysisLogbook(logbook="analysis", **params.to_dict())
        >>> lb.protocol_id_key
        'Protocol ID'
    """

    protocol_id_key = 'Protocol ID'

    def get_parent_msg_id(self, protocol_id: int | str) -> int:
        """Return the unique parent message ID for a protocol.

        Args:
            protocol_id (int | str): Protocol identifier.

        Returns:
            int: Parent message ID.

        Raises:
            autoerror.InvalidParent: If no unique parent can be determined.
            elog.LogbookError: If ELOG queries fail.

        Example:
            >>> lb = elog_handle_factory.get_logbook_handle("analysis")
            >>> isinstance(lb.get_parent_msg_id("42"), int)
            True
        """
        msg_ids = self.get_msg_ids(protocol_id)
        parents = list()
        for msg_id in msg_ids:
            parent = self.get_parent(msg_id, timeout=self.timeout)
            if parent:
                parents.append(parent)

        if len(parents) == 1:
            return parents[0]
        else:
            raise autoerror.InvalidParent

    def verify_message_hierarchy(self, ids: list[int]) -> tuple[bool, list[int]]:
        """Verify whether IDs form a parent-with-children hierarchy.

        Args:
            ids (list[int]): Candidate message IDs.

        Returns:
            tuple[bool, list[int]]: A tuple ``(hierarchy_ok, ordered_ids)`` where
            ``hierarchy_ok`` indicates validity and ``ordered_ids`` contains the
            parent followed by its children when valid.

        Raises:
            elog.LogbookError: If parent/child retrieval fails.

        Example:
            >>> lb = elog_handle_factory.get_logbook_handle("analysis")
            >>> ok, ordered = lb.verify_message_hierarchy([10, 11, 12])
            >>> isinstance(ok, bool) and isinstance(ordered, list)
            True
        """
        # we expect to have one top level id and all the other should be its children.
        # the top level should have the lowest id, that's why we sort it

        # the hierarchy is ok if
        # 1. there is one parent
        # 2. all children are in the list
        # 3. there are no other id in the list (in other words, the size of ids is 1 bigger than the children

        hierarchy_ok = False
        ordered_id = list()
        for msg_id in sorted(ids):
            if self.get_parent(msg_id, timeout=self.timeout) is None:
                # then this msg_id is the parent.
                # get all its children
                children = self.get_children(msg_id, timeout=self.timeout)
                hierarchy_ok = all(i in ids for i in children) and len(children) == len(ids) - 1
                if hierarchy_ok:
                    ordered_id = [msg_id, *children]
                break
        return hierarchy_ok, ordered_id


class ListLogbook(AdvLogbook):
    """Advanced logbook implementation for protocol list entries.

    Inheritance:
        Subclass of ``AdvLogbook`` specialized for the protocol list logbook
        using ``Protocol number`` as identifier key.

    Attributes:
        protocol_id_key (str): Fixed to ``'Protocol number'``.

    Example:
        >>> params = ELOGConnectionParameters.from_config_module()
        >>> lb = ListLogbook(logbook="protocol-list", **params.to_dict())
        >>> lb.protocol_id_key
        'Protocol number'
    """

    protocol_id_key = 'Protocol number'

    def get_msg_id(self, protocol_id: int | str) -> int | None:
        """Return the first message ID for a protocol number, if any.

        Args:
            protocol_id (int | str): Protocol identifier.

        Returns:
            int | None: First matching message ID or ``None``.

        Raises:
            elog.LogbookError: If ELOG retrieval fails.

        Example:
            >>> lb = elog_handle_factory.get_logbook_handle("protocol-list")
            >>> result = lb.get_msg_id("42")
            >>> result is None or isinstance(result, int)
            True
        """
        l = self.get_msg_ids(protocol_id)
        if len(l):
            return l[0]
        else:
            return None
