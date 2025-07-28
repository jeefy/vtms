#!/usr/bin/env python3
"""
Vehicle Telemetry Management System (VTMS) Client
Handles OBD2 and GPS data collection and MQTT communication
"""

import asyncio
import logging
import sys
import time
from functools import partial
from typing import Optional
from collections import deque
import json

try:
    import pynmea2
    import serial
    GPS_AVAILABLE = True
except ImportError:
    pynmea2 = None
    serial = None
    GPS_AVAILABLE = False
    logging.warning("pynmea2 or pyserial not available - GPS functionality will be disabled")

import obd
import paho.mqtt.client as mqtt
from obd import OBDStatus

from src import config, myobd
from src.mqtt_handlers import (
    MQTTMessageRouter, 
    create_debug_handler,
    create_flag_handler, 
    create_pit_handler,
    create_message_handler
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VTMSClient:
    """Main VTMS client for handling OBD2, GPS, and MQTT communication"""
    
    def __init__(self):
        self.mqttc: Optional[mqtt.Client] = None
        self.obd_connection: Optional[obd.Async] = None
        self.is_pi = config.is_raspberrypi()
        self.led_handler = None
        
        # GPS connection
        self.gps_serial = None  # Will be serial.Serial object when connected
        self.gps_port = config.config.gps_port
        self.gps_baudrate = config.config.gps_baudrate
        
        # MQTT connection state and buffering
        self.mqtt_connected = False
        self.message_buffer = deque(maxlen=1000)  # Buffer up to 1000 messages
        self.max_buffer_size = 1000  # Maximum number of messages to buffer
        self.mqtt_retry_count = 0
        self.max_mqtt_retries = 10
        self.mqtt_retry_delay = 5  # seconds
        
        # Initialize message router
        self.message_router = MQTTMessageRouter()
        self._setup_message_handlers()
        
        # Create MQTT wrapper for OBD2 functions
        self.mqtt_wrapper = MQTTWrapper(self)
        
        if self.is_pi:
            try:
                from src import led
                self.led_handler = led
                logger.info("LED support enabled for Raspberry Pi")
            except ImportError:
                logger.warning("LED module not available")
    
    def _setup_message_handlers(self):
        """Setup MQTT message handlers"""
        self.message_router.register_handler('lemons/debug', create_debug_handler())
        self.message_router.register_handler('lemons/message', create_message_handler())
        self.message_router.register_pattern_handler('lemons/flag/', create_flag_handler())
        
        pit_handler = create_pit_handler()
        self.message_router.register_handler('lemons/pit', pit_handler)
        self.message_router.register_handler('lemons/box', pit_handler)
    
    def setup_mqtt(self) -> bool:
        """Initialize MQTT client and connection"""
        try:
            self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.mqttc.on_connect = self._on_connect
            self.mqttc.on_message = self._on_message
            self.mqttc.on_disconnect = self._on_disconnect
            self.mqttc.on_publish = self._on_publish
            
            # Enable automatic reconnection
            self.mqttc.reconnect_delay_set(min_delay=1, max_delay=120)
            
            self.mqttc.connect(config.mqtt_server, config.config.mqtt_port, config.config.mqtt_keepalive)
            # Don't start loop here - we'll handle it in the run method
            logger.info(f"MQTT client connected to {config.mqtt_server}")
            return True
        except Exception as e:
            logger.error(f"Failed to setup MQTT: {e}")
            return False
    
    def discover_gps_ports(self):
        """Discover available GPS serial ports"""
        if not GPS_AVAILABLE:
            return []
            
        import serial.tools.list_ports
        
        # Common GPS device patterns
        gps_patterns = [
            #'ttyUSB',    # USB GPS devices
            'ttyACM',    # USB GPS devices with CDC-ACM drivers
            #'ttyAMA',    # Raspberry Pi GPIO UART
            #'ttyS',      # Traditional serial ports
        ]
        
        possible_ports = []
        ports = serial.tools.list_ports.comports()
        
        for port in ports:
            for pattern in gps_patterns:
                if pattern in port.device:
                    possible_ports.append(port.device)
                    logger.info(f"Found potential GPS port: {port.device} - {port.description}")
        
        return possible_ports
    
    async def setup_gps_connection(self) -> bool:
        """Establish GPS serial connection"""
        if not GPS_AVAILABLE:
            logger.warning("GPS functionality disabled - pynmea2 or pyserial not available")
            return False
            
        logger.info("Setting up GPS connection...")
        
        # If no specific port is configured, try to discover GPS ports
        if not self.gps_port:
            possible_ports = self.discover_gps_ports()
            if not possible_ports:
                logger.warning("No potential GPS ports found")
                return False
        else:
            possible_ports = [self.gps_port]
        
        # Try each possible port
        for port in possible_ports:
            try:
                logger.info(f"Attempting GPS connection on {port}")
                self.gps_serial = serial.Serial(
                    port, 
                    self.gps_baudrate, 
                    timeout=2,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
                
                # Test the connection by reading a few lines
                test_lines = 0
                for _ in range(10):  # Try to read up to 10 lines
                    try:
                        line = self.gps_serial.readline().decode('ascii', errors='ignore').strip()
                        if line.startswith('$') and ',' in line:
                            # Looks like NMEA data
                            test_lines += 1
                            if test_lines >= 2:  # We've seen valid NMEA data
                                self.gps_port = port
                                logger.info(f"GPS connected successfully on {port}")
                                return True
                    except Exception:
                        continue
                
                # If we get here, no valid NMEA data was found
                self.gps_serial.close()
                self.gps_serial = None
                logger.warning(f"No valid NMEA data found on {port}")
                
            except Exception as e:
                logger.warning(f"Failed to connect to GPS on {port}: {e}")
                if self.gps_serial:
                    try:
                        self.gps_serial.close()
                    except:
                        pass
                    self.gps_serial = None
                continue
        
        logger.error("Failed to establish GPS connection on any port")
        return False
    
    async def start_gps_monitoring(self):
        """Background task for GPS data collection and publishing"""
        logger.info("Starting GPS monitoring")
        
        if not GPS_AVAILABLE:
            logger.warning("GPS monitoring disabled - pynmea2 or pyserial not available")
            # Keep the task alive but do nothing
            while True:
                await asyncio.sleep(60)
        
        # Try to establish GPS connection
        if not await self.setup_gps_connection():
            logger.error("Failed to setup GPS connection, GPS monitoring disabled")
            while True:
                await asyncio.sleep(60)
                
        logger.info("GPS monitoring started successfully")
        
        # GPS data storage
        last_gps_data = {
            'latitude': None,
            'longitude': None,
            'altitude': None,
            'speed': None,
            'track': None,
            'timestamp': None
        }
        
        while True:
            try:
                if not self.gps_serial or not self.gps_serial.is_open:
                    logger.warning("GPS connection lost, attempting to reconnect...")
                    if not await self.setup_gps_connection():
                        logger.error("Failed to reconnect GPS")
                        await asyncio.sleep(30)
                        continue
                
                # Read NMEA sentences from GPS
                try:
                    line = self.gps_serial.readline().decode('ascii', errors='ignore').strip()
                    if not line.startswith('$'):
                        continue
                        
                    # Parse NMEA sentence
                    try:
                        msg = pynmea2.parse(line)
                        
                        # Process different NMEA sentence types
                        if hasattr(msg, 'latitude') and hasattr(msg, 'longitude'):
                            # GGA, GLL, RMC sentences contain position data
                            if msg.latitude and msg.longitude:
                                last_gps_data['latitude'] = float(msg.latitude)
                                last_gps_data['longitude'] = float(msg.longitude)
                                last_gps_data['timestamp'] = time.time()
                        
                        if hasattr(msg, 'altitude') and msg.altitude:
                            last_gps_data['altitude'] = float(msg.altitude)
                            
                        if hasattr(msg, 'spd_over_grnd') and msg.spd_over_grnd:
                            # Speed in knots, convert to m/s
                            last_gps_data['speed'] = float(msg.spd_over_grnd) * 0.514444
                            
                        if hasattr(msg, 'true_course') and msg.true_course:
                            last_gps_data['track'] = float(msg.true_course)
                            
                    except (pynmea2.ParseError, ValueError) as e:
                        # Skip invalid NMEA sentences
                        if config.getDebug():
                            logger.debug(f"Failed to parse NMEA sentence: {line} - {e}")
                        continue
                
                except Exception as e:
                    logger.error(f"Error reading GPS data: {e}")
                    await asyncio.sleep(1)
                    continue
                
                # Publish GPS data if we have valid position
                if (last_gps_data['latitude'] is not None and 
                    last_gps_data['longitude'] is not None):
                    
                    # Publish individual GPS topics
                    gps_data = {
                        "lemons/gps/pos": f"{last_gps_data['latitude']},{last_gps_data['longitude']}",
                        "lemons/gps/latitude": str(last_gps_data['latitude']),
                        "lemons/gps/longitude": str(last_gps_data['longitude']),
                    }
                    
                    if last_gps_data['speed'] is not None:
                        gps_data["lemons/gps/speed"] = str(last_gps_data['speed'])
                        
                    if last_gps_data['altitude'] is not None:
                        gps_data["lemons/gps/altitude"] = str(last_gps_data['altitude'])
                        
                    if last_gps_data['track'] is not None:
                        gps_data["lemons/gps/track"] = str(last_gps_data['track'])
                    
                    published_count = 0
                    for topic, value in gps_data.items():
                        if value is not None and value != "None":
                            self._publish_message(topic, value)
                            published_count += 1
                    
                    if config.getDebug():
                        logger.debug(f'GPS data published: {published_count} topics, '
                                   f'position: {last_gps_data["latitude"]},{last_gps_data["longitude"]}')
                
            except Exception as e:
                logger.error(f"GPS error: {e}")
                # Wait a bit longer on error before retrying
                await asyncio.sleep(10)
                continue
            
            # Small delay to prevent overwhelming the CPU
            await asyncio.sleep(1)

    def _publish_message(self, topic: str, payload, qos: int = 0, retain: bool = False):
        """Publish message with automatic buffering if disconnected"""
        try:
            if self.mqtt_connected and self.mqttc:
                # Try to publish immediately
                if isinstance(payload, dict):
                    payload = json.dumps(payload)
                elif not isinstance(payload, str):
                    payload = str(payload)
                    
                result = self.mqttc.publish(topic, payload, qos, retain)
                if result.rc != 0:
                    logger.warning(f"MQTT publish failed with return code {result.rc}, buffering message")
                    self._buffer_message(topic, payload, qos, retain)
                    return False
                return True
            else:
                # Buffer the message for later
                self._buffer_message(topic, payload, qos, retain)
                return False
                
        except Exception as e:
            logger.error(f"Error publishing MQTT message: {e}")
            self._buffer_message(topic, payload, qos, retain)
            return False
    
    def _buffer_message(self, topic: str, payload, qos: int = 0, retain: bool = False):
        """Buffer message for later publishing when connection is restored"""
        try:
            # Remove old messages if buffer is full
            while len(self.message_buffer) >= self.max_buffer_size:
                old_msg = self.message_buffer.popleft()
                logger.warning(f"Dropping old buffered message to topic {old_msg['topic']}")
            
            # Add new message with timestamp
            message = {
                'topic': topic,
                'payload': payload,
                'qos': qos,
                'retain': retain,
                'timestamp': time.time()
            }
            self.message_buffer.append(message)
            logger.debug(f"Buffered message to {topic}, buffer size: {len(self.message_buffer)}")
            
        except Exception as e:
            logger.error(f"Error buffering MQTT message: {e}")
    
    def _flush_message_buffer(self):
        """Send all buffered messages when connection is restored"""
        if not self.mqtt_connected or not self.mqttc or not self.message_buffer:
            return
            
        flushed_count = 0
        current_time = time.time()
        
        # Process messages in order (FIFO)
        while self.message_buffer:
            message = self.message_buffer.popleft()
            
            # Skip messages older than 5 minutes
            if current_time - message['timestamp'] > 300:
                logger.warning(f"Dropping expired buffered message to {message['topic']}")
                continue
            
            try:
                result = self.mqttc.publish(
                    message['topic'], 
                    message['payload'], 
                    message['qos'], 
                    message['retain']
                )
                
                if result.rc == 0:
                    flushed_count += 1
                else:
                    # Put message back in buffer and stop processing
                    self.message_buffer.appendleft(message)
                    logger.warning(f"Failed to flush message, stopping buffer flush")
                    break
                    
            except Exception as e:
                # Put message back in buffer and stop processing
                self.message_buffer.appendleft(message)
                logger.error(f"Error flushing buffered message: {e}")
                break
        
        if flushed_count > 0:
            logger.info(f"Flushed {flushed_count} buffered messages to MQTT")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback for when the client receives a CONNACK response from the server"""
        try:
            if reason_code == 0:
                self.mqtt_connected = True
                self.mqtt_retry_count = 0
                logger.info(f"MQTT connected successfully with result code {reason_code}")
                
                # Subscribing in on_connect() means that if we lose the connection and
                # reconnect then subscriptions will be renewed.
                client.subscribe("lemons/#")
                
                # Flush any buffered messages
                self._flush_message_buffer()
            else:
                self.mqtt_connected = False
                logger.error(f"MQTT connection failed with result code {reason_code}")
                
        except Exception as e:
            logger.error(f"Error in MQTT on_connect callback: {e}")
    
    def _on_disconnect(self, client, userdata, reason_code, properties):
        """Callback for when the client disconnects from the server"""
        self.mqtt_connected = False
        if reason_code != 0:
            logger.warning(f"MQTT disconnected unexpectedly with code {reason_code}")
        else:
            logger.info("MQTT disconnected normally")
    
    def _on_publish(self, client, userdata, mid, reason_code, properties):
        """Callback for when a message is published"""
        if reason_code != 0:
            logger.warning(f"Message publish failed with reason code {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server"""
        try:
            payload = str(msg.payload.decode("utf-8"))
            
            if config.getDebug():
                logger.info(f"{msg.topic}: {payload}")
            
            if self.is_pi and self.led_handler:
                self.led_handler.handler(msg, mqttc=self.mqttc)

            # Try to route the message through our handler system
            if not self.message_router.route_message(msg.topic, payload):
                # If no handler found, try OBD handling as fallback
                self._handle_obd_message(msg.topic, payload)
        except Exception as e:
            logger.error(f"Error in MQTT on_message callback: {e}")

    def _handle_obd_message(self, topic: str, payload: str):
        """Handle OBD2-related MQTT messages"""
        if not self.obd_connection:
            return
            
        if topic == 'lemons/obd2/watch':
            if payload in obd.commands:
                with self.obd_connection.paused():
                    self.obd_connection.watch(
                        obd.commands[payload], 
                        callback=partial(myobd.new_metric, mqttc=self.mqttc)
                    )
        elif topic == 'lemons/obd2/unwatch':
            if payload in obd.commands:
                with self.obd_connection.paused():
                    self.obd_connection.unwatch(obd.commands[payload])
        elif topic == 'lemons/obd2/query':
            if payload in obd.commands:
                r = self.obd_connection.query(obd.commands[payload])
                self._process_obd_response(payload, r)

    def _process_obd_response(self, command: str, response):
        """Process OBD2 command responses and publish to appropriate handlers"""
        if command in myobd.metric_commands:
            myobd.new_metric(response, mqttc=self.mqtt_wrapper)
        elif command in myobd.monitor_commands:
            myobd.new_monitor(response, mqttc=self.mqtt_wrapper)
        elif command == 'GET_DTC':
            myobd.new_dtc(response, mqttc=self.mqtt_wrapper)
        else:
            if config.getDebug():
                logger.warning(f'No proper handler for query type "{command}" -- defaulting to Metric')
            myobd.new_metric(response, mqttc=self.mqtt_wrapper)

    async def setup_obd_connection(self) -> bool:
        """Establish OBD2 connection"""
        logger.info("Setting up OBD2 connection...")
        
        while True:
            ports = obd.scan_serial()
            logger.info(f'Possible ports: {ports}')

            if len(ports) == 0:
                logger.warning('No OBDII ports found. Sleeping for 15s then retrying...')
                await asyncio.sleep(config.config.obd_retry_delay)
                continue

            for port in ports:
                self.obd_connection = obd.Async(port, timeout=5, delay_cmds=0, start_low_power=True, fast=True)

                if self.obd_connection.status() is not OBDStatus.CAR_CONNECTED:
                    logger.warning(f'No connection to OBDII port from {port}')
                    continue
                else:
                    logger.info(f'Connected to OBDII port on {port}')
                    return True
                    
            if not self.obd_connection or self.obd_connection.status() is not OBDStatus.CAR_CONNECTED:
                logger.error('No connection to OBDII port')
                return False

    def setup_obd_watches(self):
        """Set up OBD2 command watches for metrics and monitors"""
        if not self.obd_connection:
            logger.error("OBD connection not established")
            return
            
        # Set up metric watches
        for command in myobd.metric_commands:
            if self.obd_connection.supports(obd.commands[command]):
                logger.info(f'Starting metrics watch for {command}')
                self.obd_connection.watch(
                    obd.commands[command], 
                    callback=partial(myobd.new_metric, mqttc=self.mqttc)
                )
        
        # Set up monitor watches
        for command in myobd.monitor_commands:
            if self.obd_connection.supports(obd.commands[command]):
                logger.info(f'Starting monitor watch for {command}')
                self.obd_connection.watch(
                    obd.commands[command], 
                    callback=partial(myobd.new_monitor, mqttc=self.mqttc)
                )

        # Set up DTC watch
        self.obd_connection.watch(
            obd.commands.GET_DTC, 
            callback=partial(myobd.new_dtc, mqttc=self.mqttc)
        )

    async def run(self):
        """Main run loop for the VTMS client"""
        logger.info("Starting VTMS Client...")
        
        # Setup MQTT connection
        if not self.setup_mqtt():
            logger.error("Failed to setup MQTT connection")
            return False
        
        # Start MQTT background loop
        self.mqttc.loop_start()
        logger.info("MQTT background loop started")
        
        # Create tasks for concurrent execution
        tasks = []
        
        # Start GPS monitoring task
        if config.getGpsEnabled():
            gps_task = asyncio.create_task(self.start_gps_monitoring())
            tasks.append(gps_task)
            logger.info("GPS monitoring task started")
        else:
            logger.info("GPS monitoring disabled by configuration")
        
        # Start OBD2 setup and monitoring task
        obd_task = asyncio.create_task(self._run_obd_monitoring())
        tasks.append(obd_task)
        logger.info("OBD2 monitoring task started")
        
        # Start health check task
        health_task = asyncio.create_task(self._health_check_task())
        tasks.append(health_task)
        logger.info("Health check task started")
        
        # Start MQTT connection monitor task
        mqtt_monitor_task = asyncio.create_task(self._mqtt_connection_monitor())
        tasks.append(mqtt_monitor_task)
        logger.info("MQTT connection monitor task started")
        
        # Add a keepalive task to keep the event loop running
        keepalive_task = asyncio.create_task(self._keepalive_task())
        tasks.append(keepalive_task)
        logger.info("Keepalive task started")
        
        try:
            # Wait for all tasks to complete (or until interrupted)
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("Shutting down VTMS Client...")
        finally:
            # Clean shutdown
            logger.info("Cleaning up resources...")
            
            # Cancel all tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to finish cancellation
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Stop OBD connection
            if self.obd_connection:
                self.obd_connection.stop()
                logger.info("OBD2 connection stopped")
            
            # Stop GPS connection
            if self.gps_serial and self.gps_serial.is_open:
                self.gps_serial.close()
                logger.info("GPS connection stopped")
            
            # Stop MQTT
            if self.mqttc:
                self.mqttc.loop_stop()
                self.mqttc.disconnect()
                logger.info("MQTT connection stopped")
    
    async def _run_obd_monitoring(self):
        """Background task for OBD2 setup and monitoring"""
        try:
            # Setup OBD2 connection (async)
            if not await self.setup_obd_connection():
                logger.error("Failed to setup OBD2 connection")
                return
                
            # Setup OBD2 watches
            self.setup_obd_watches()
            
            # Start OBD2 connection
            self.obd_connection.start()
            logger.info("OBD2 monitoring started successfully")
            
            # Keep the task alive (OBD monitoring happens via callbacks)
            while True:
                await asyncio.sleep(10)  # Check every 10 seconds
                if self.obd_connection and self.obd_connection.status() != OBDStatus.CAR_CONNECTED:
                    logger.warning("OBD2 connection lost, attempting to reconnect...")
                    # Attempt to reconnect
                    if not await self.setup_obd_connection():
                        logger.error("Failed to reconnect to OBD2")
                        await asyncio.sleep(30)  # Wait before next attempt
                    else:
                        self.setup_obd_watches()
                        self.obd_connection.start()
                        
        except asyncio.CancelledError:
            logger.info("OBD2 monitoring task cancelled")
            raise
        except Exception as e:
            logger.error(f"OBD2 monitoring error: {e}")
            # Don't exit, keep trying
    
    async def _mqtt_connection_monitor(self):
        """Monitor MQTT connection and attempt reconnections"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self.mqtt_connected:
                    self.mqtt_retry_count += 1
                    logger.warning(f"MQTT disconnected, attempting reconnection #{self.mqtt_retry_count}")
                    
                    try:
                        # Disconnect first to clean up any existing connection
                        if self.mqttc:
                            self.mqttc.disconnect()
                        
                        # Wait a bit before reconnecting
                        await asyncio.sleep(min(self.mqtt_retry_count * 2, 30))
                        
                        # Re-setup MQTT connection
                        await self.setup_mqtt()
                        
                        if self.mqtt_connected:
                            logger.info(f"MQTT reconnected successfully after {self.mqtt_retry_count} attempts")
                        else:
                            logger.error("MQTT reconnection failed")
                            
                    except Exception as e:
                        logger.error(f"Error during MQTT reconnection: {e}")
                else:
                    # Connection is healthy, reset retry counter
                    if self.mqtt_retry_count > 0:
                        self.mqtt_retry_count = 0
                        
            except asyncio.CancelledError:
                logger.info("MQTT connection monitor task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in MQTT connection monitor: {e}")
                await asyncio.sleep(10)

    async def _health_check_task(self):
        """Periodic health check for system components"""
        logger.info("Starting health check task")
        
        while True:
            try:
                await asyncio.sleep(60)  # Health check every minute
                
                # Check MQTT connection status
                mqtt_connected = False
                if self.mqttc:
                    # Check if MQTT client is connected
                    mqtt_connected = self.mqttc.is_connected()
                    if not mqtt_connected:
                        logger.warning("MQTT client is not connected")
                
                # Check OBD2 connection
                obd_connected = False
                if self.obd_connection:
                    status = self.obd_connection.status()
                    obd_connected = (status == OBDStatus.CAR_CONNECTED)
                    if not obd_connected:
                        logger.warning(f"OBD2 connection status: {status}")
                else:
                    logger.warning("No OBD2 connection established")
                
                # Publish health status
                if mqtt_connected:
                    health_data = {
                        "mqtt_connected": mqtt_connected,
                        "obd_connected": obd_connected,
                        "timestamp": time.time()
                    }
                    self._publish_message("lemons/health", health_data)
                    logger.debug(f"Health status published: MQTT={mqtt_connected}, OBD={obd_connected}")
                
            except asyncio.CancelledError:
                logger.info("Health check task cancelled")
                raise
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def _keepalive_task(self):
        """Simple keepalive task to maintain the event loop"""
        logger.info("Starting keepalive task")
        
        try:
            while True:
                await asyncio.sleep(30)  # Simple heartbeat every 30 seconds
                logger.debug("Keepalive heartbeat")
        except asyncio.CancelledError:
            logger.info("Keepalive task cancelled")
            raise


class MQTTWrapper:
    """Wrapper class to provide robust MQTT publishing for OBD2 functions"""
    
    def __init__(self, vtms_client):
        self.vtms_client = vtms_client
    
    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False):
        """Wrapper for robust MQTT publishing"""
        return self.vtms_client._publish_message(topic, payload, qos, retain)


def main():
    """Main entry point"""
    client = VTMSClient()
    asyncio.run(client.run())


if __name__ == "__main__":
    main()