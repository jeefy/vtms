"""
Unit tests for OBDService
"""

from functools import partial
from unittest.mock import MagicMock, patch, call

import pytest
import obd
from obd import OBDStatus

from vtms_client.obd_service import OBDService
from tests.conftest import MockOBDAsync


class TestOBDServiceInit:
    """Test OBDService initialisation."""

    def test_defaults(self):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        assert svc.publisher is publisher
        assert svc.connection is None


class TestOBDServiceSetupWatches:
    """Test watch registration."""

    def test_setup_watches_no_connection(self):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        # Should not raise
        svc.setup_watches()

    @patch("vtms_client.obd_service.obd")
    @patch("vtms_client.obd_service.myobd")
    def test_setup_watches_registers_supported_commands(self, mock_myobd, mock_obd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_myobd.metric_commands = ["RPM", "SPEED"]
        mock_myobd.monitor_commands = ["MONITOR_MISFIRE_GENERAL"]

        # Create a mock connection
        mock_conn = MagicMock()
        mock_conn.supports.return_value = True
        svc.connection = mock_conn

        svc.setup_watches()

        # Should watch RPM, SPEED, MONITOR_MISFIRE_GENERAL, and GET_DTC
        assert mock_conn.watch.call_count == 4  # 2 metrics + 1 monitor + 1 DTC

    @patch("vtms_client.obd_service.obd")
    @patch("vtms_client.obd_service.myobd")
    def test_setup_watches_skips_unsupported(self, mock_myobd, mock_obd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_myobd.metric_commands = ["RPM", "SPEED"]
        mock_myobd.monitor_commands = []

        mock_conn = MagicMock()
        mock_conn.supports.return_value = False
        svc.connection = mock_conn

        svc.setup_watches()

        # Only DTC watch (always added regardless of supports())
        assert mock_conn.watch.call_count == 1


class TestOBDServiceHandleMessage:
    """Test MQTT message routing into OBD commands."""

    def test_handle_message_no_connection(self):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)
        # Should not raise
        svc.handle_message("lemons/obd2/watch", "RPM")

    @patch("vtms_client.obd_service.obd")
    @patch("vtms_client.obd_service.myobd")
    def test_handle_watch(self, mock_myobd, mock_obd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_conn = MagicMock()
        svc.connection = mock_conn

        # Make the command lookup work
        mock_obd.commands.__contains__ = MagicMock(return_value=True)
        mock_obd.commands.__getitem__ = MagicMock(return_value=MagicMock())

        svc.handle_message("lemons/obd2/watch", "RPM")

        mock_conn.watch.assert_called_once()

    @patch("vtms_client.obd_service.obd")
    def test_handle_unwatch(self, mock_obd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_conn = MagicMock()
        svc.connection = mock_conn

        mock_obd.commands.__contains__ = MagicMock(return_value=True)
        mock_obd.commands.__getitem__ = MagicMock(return_value=MagicMock())

        svc.handle_message("lemons/obd2/unwatch", "RPM")

        mock_conn.unwatch.assert_called_once()

    @patch("vtms_client.obd_service.obd")
    @patch("vtms_client.obd_service.myobd")
    def test_handle_query(self, mock_myobd, mock_obd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_conn = MagicMock()
        svc.connection = mock_conn

        mock_obd.commands.__contains__ = MagicMock(return_value=True)
        mock_cmd = MagicMock()
        mock_obd.commands.__getitem__ = MagicMock(return_value=mock_cmd)

        mock_myobd.metric_commands = ["RPM"]
        mock_myobd.monitor_commands = []

        svc.handle_message("lemons/obd2/query", "RPM")

        mock_conn.query.assert_called_once_with(mock_cmd)


class TestOBDServiceProcessResponse:
    """Test _process_response dispatching."""

    @patch("vtms_client.obd_service.myobd")
    def test_metric_response(self, mock_myobd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_myobd.metric_commands = ["RPM"]
        mock_myobd.monitor_commands = []

        mock_response = MagicMock()
        svc._process_response("RPM", mock_response)

        mock_myobd.new_metric.assert_called_once_with(mock_response, publish=publisher)

    @patch("vtms_client.obd_service.myobd")
    def test_monitor_response(self, mock_myobd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_myobd.metric_commands = []
        mock_myobd.monitor_commands = ["MONITOR_MISFIRE_GENERAL"]

        mock_response = MagicMock()
        svc._process_response("MONITOR_MISFIRE_GENERAL", mock_response)

        mock_myobd.new_monitor.assert_called_once_with(mock_response, publish=publisher)

    @patch("vtms_client.obd_service.myobd")
    def test_dtc_response(self, mock_myobd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_myobd.metric_commands = []
        mock_myobd.monitor_commands = []

        mock_response = MagicMock()
        svc._process_response("GET_DTC", mock_response)

        mock_myobd.new_dtc.assert_called_once_with(mock_response, publish=publisher)

    @patch("vtms_client.obd_service.myobd")
    def test_unknown_command_defaults_to_metric(self, mock_myobd):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)

        mock_myobd.metric_commands = []
        mock_myobd.monitor_commands = []

        mock_response = MagicMock()
        svc._process_response("UNKNOWN_CMD", mock_response)

        mock_myobd.new_metric.assert_called_once_with(mock_response, publish=publisher)


class TestOBDServiceStop:
    """Test stop method."""

    def test_stop_with_connection(self):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)
        mock_conn = MagicMock()
        svc.connection = mock_conn

        svc.stop()

        mock_conn.stop.assert_called_once()

    def test_stop_without_connection(self):
        publisher = MagicMock()
        svc = OBDService(publisher=publisher)
        # Should not raise
        svc.stop()
