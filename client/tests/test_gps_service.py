"""
Unit tests for GPSService
"""

from unittest.mock import MagicMock, patch, PropertyMock

from vtms_client.gps_service import GPSService


class TestGPSServiceInit:
    """Test GPSService initialisation."""

    def test_defaults(self):
        publisher = MagicMock()
        svc = GPSService(publisher=publisher)

        assert svc.publisher is publisher
        assert svc.gps_serial is None


class TestGPSServiceDiscoverPorts:
    """Test port discovery."""

    @patch("vtms_client.gps_service.GPS_AVAILABLE", False)
    def test_discover_returns_empty_when_unavailable(self):
        result = GPSService.discover_ports()
        assert result == []

    @patch("vtms_client.gps_service.GPS_AVAILABLE", True)
    @patch("vtms_client.gps_service.serial")
    def test_discover_finds_matching_ports(self, mock_serial):
        port1 = MagicMock()
        port1.device = "/dev/ttyACM0"
        port1.description = "GPS Receiver"

        port2 = MagicMock()
        port2.device = "/dev/ttyUSB0"
        port2.description = "USB-Serial"

        mock_serial.tools.list_ports.comports.return_value = [port1, port2]

        result = GPSService.discover_ports()

        assert len(result) == 1
        assert "/dev/ttyACM0" in result


class TestGPSServiceUpdateLast:
    """Test _update_last static method (NMEA parsing helper)."""

    def test_updates_lat_lon(self):
        last = {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "speed": None,
            "track": None,
            "timestamp": None,
        }

        msg = MagicMock()
        msg.latitude = 40.7128
        msg.longitude = -74.006
        del msg.altitude
        del msg.spd_over_grnd
        del msg.true_course

        GPSService._update_last(last, msg)

        assert last["latitude"] == 40.7128
        assert last["longitude"] == -74.006
        assert last["timestamp"] is not None

    def test_updates_altitude(self):
        last = {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "speed": None,
            "track": None,
            "timestamp": None,
        }

        msg = MagicMock(spec=[])
        msg.altitude = 150.5
        # Add only the attribute we need
        type(msg).altitude = PropertyMock(return_value=150.5)

        GPSService._update_last(last, msg)

        assert last["altitude"] == 150.5

    def test_updates_speed_knots_to_ms(self):
        last = {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "speed": None,
            "track": None,
            "timestamp": None,
        }

        msg = MagicMock(spec=[])
        type(msg).spd_over_grnd = PropertyMock(return_value=10.0)

        GPSService._update_last(last, msg)

        expected = 10.0 * 0.514444
        assert abs(last["speed"] - expected) < 0.001


class TestGPSServicePublishPosition:
    """Test _publish_position helper."""

    def test_no_publish_without_fix(self):
        publisher = MagicMock()
        svc = GPSService(publisher=publisher)

        last = {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "speed": None,
            "track": None,
            "timestamp": None,
        }

        svc._publish_position(last)

        publisher.assert_not_called()

    @patch("vtms_client.gps_service.pygeohash")
    def test_publishes_position_topics(self, mock_geohash):
        mock_geohash.encode.return_value = "dr5regw3pp6g"

        publisher = MagicMock()
        svc = GPSService(publisher=publisher)

        last = {
            "latitude": 40.7128,
            "longitude": -74.006,
            "altitude": 100.0,
            "speed": 5.0,
            "track": 180.0,
            "timestamp": 1000,
        }

        svc._publish_position(last)

        # Should publish lat, lon, pos, geohash, speed, altitude, track
        assert publisher.call_count == 7

        # Check some specific topics
        topics = [call.args[0] for call in publisher.call_args_list]
        assert "lemons/gps/pos" in topics
        assert "lemons/gps/latitude" in topics
        assert "lemons/gps/longitude" in topics
        assert "lemons/gps/geohash" in topics
        assert "lemons/gps/speed" in topics
        assert "lemons/gps/altitude" in topics
        assert "lemons/gps/track" in topics


class TestGPSServiceClose:
    """Test close method."""

    def test_close_open_serial(self):
        publisher = MagicMock()
        svc = GPSService(publisher=publisher)

        mock_serial = MagicMock()
        mock_serial.is_open = True
        svc.gps_serial = mock_serial

        svc.close()

        mock_serial.close.assert_called_once()

    def test_close_no_serial(self):
        publisher = MagicMock()
        svc = GPSService(publisher=publisher)
        # Should not raise
        svc.close()
