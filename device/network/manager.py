# Import standard python modules
import os, logging, threading, time, platform

# Import python types
from typing import Dict, Any, Tuple, List

# Import device utilities
from device.utilities import logger, accessors, constants
from device.utilities.statemachine import manager
from device.utilities.state.main import State
from device.utilities import network as network_utilities

# Import manager elements
from device.network import modes


class NetworkManager(manager.StateMachineManager):
    """Manages network connections."""

    _connected: bool = False

    def __init__(self, state: State) -> None:
        """Initializes network manager."""

        # Initialize parent class
        super().__init__()

        # Initialize parameters
        self.state = state

        # Initialize logger
        self.logger = logger.Logger("NetworkManager", "network")
        self.logger.debug("Initializing manager")

        # Initialize reported metrics
        self.status = "Initializing"

        # Initialize state machine transitions
        self.transitions: Dict[str, List[str]] = {
            modes.CONNECTED: [modes.DISCONNECTED, modes.SHUTDOWN, modes.ERROR],
            modes.DISCONNECTED: [modes.CONNECTED, modes.SHUTDOWN, modes.ERROR],
            modes.ERROR: [modes.SHUTDOWN],
        }

        # Initialize state machine mode
        self.mode = modes.DISCONNECTED

    @property
    def is_connected(self) -> bool:
        """Gets internet connection status."""
        return self.state.network.get("is_connected", False)

    @is_connected.setter
    def is_connected(self, value: bool) -> None:
        """Sets connection status, updates reconnection status, and logs changes."""

        # Set previous and current connection state
        prev_connected = self._connected
        self._connected = value

        # Check for new connection
        if prev_connected != self._connected and self._connected:
            self.logger.info("Connected to internet")
            self.reconnected = True
            self.mode = modes.CONNECTED

        # Check for new disconnection
        elif prev_connected != self._connected and not self._connected:
            self.logger.info("Disconnected from internet")
            self.reconnected = False
            self.mode = modes.DISCONNECTED

        # No change to connection
        else:
            self.reconnected = False

        # Update connection status in shared state
        with self.state.lock:
            self.state.network["is_connected"] = value

    @property
    def wifi_ssids(self) -> List[Dict[str, str]]:
        """Gets value."""
        return self.state.network.get("wifi_ssids")  # type: ignore

    @wifi_ssids.setter
    def wifi_ssids(self, value: List[Dict[str, str]]) -> None:
        """Safely updates value in shared state."""
        with self.state.lock:
            self.state.network["wifi_ssids"] = value

    @property
    def ip_address(self) -> str:
        """Gets value."""
        return self.state.network.get("ip_address")  # type: ignore

    @ip_address.setter
    def ip_address(self, value: str) -> None:
        """Safely updates value in shared state."""
        with self.state.lock:
            self.state.network["ip_address"] = value

    ##### EXTERNAL STATE DECORATORS ####################################################

    @property
    def iot_is_registered(self) -> bool:
        """Gets value."""
        return self.state.iot.get("is_registered", False)  # type: ignore

    @property
    def iot_is_connected(self) -> bool:
        """Gets value."""
        return self.state.iot.get("is_connected", False)  # type: ignore

    ##### STATE MACHINE FUNCTIONS ######################################################

    def run(self) -> None:
        """Runs state machine."""

        # Loop forever
        while True:

            # Check if manager is shutdown
            if self.is_shutdown:
                break

            # Check for mode transitions
            if self.mode == modes.CONNECTED:
                self.run_connected_mode()
            elif self.mode == modes.DISCONNECTED:
                self.run_disconnected_mode()
            elif self.mode == modes.ERROR:
                self.run_error_mode()  # defined in parent classs
            elif self.mode == modes.SHUTDOWN:
                self.run_shutdown_mode()  # defined in parent class
            else:
                self.logger.critical("Invalid state machine mode")
                self.mode = modes.INVALID
                self.is_shutdown = True
                break

    def run_connected_mode(self) -> None:
        """Runs normal mode."""
        self.logger.info("Entered CONNECTED")

        # Initialize timing variables
        last_update_time = 0.0
        update_interval = 300  # seconds -> 5 minutes

        # Loop forever
        while True:

            # Update connection and storage state every update interval
            if time.time() - last_update_time > update_interval:
                last_update_time = time.time()
                self.update_connection()

            # Check for network disconnect
            if not self.is_connected:
                self.mode = modes.DISCONNECTED

            # Check for events
            self.check_events()

            # Check for transitions
            if self.new_transition(modes.CONNECTED):
                break

            # Check for raspberry pi successful initial network connection event
            # Since raspberry pi can't access the internet and broadcast an access point
            # simultaneously, we need to re-enable the access point upon initial iot
            # registration so the user can get the iot access code / link.
            # The indicator to detect this registration event is that the network is
            # connected and the iot device is registered with the iot cloud but not
            # connected to the iot cloud. The device can only connect to the iot cloud
            # once it is associated with a user account (which happens by entering the
            # iot access code in the cloud ui or clicking on the iot access link)
            if "raspberry-pi" in os.getenv("PLATFORM"):
                if self.iot_is_registered and not self.iot_is_connected:
                    message = "Detected raspberry pi successful initial network connection event"
                    self.logger.info(message)

                    # Re-enable access point
                    network_utilities.enable_raspi_access_point()

                    # Give access point time to initialize
                    time.sleep(10)

                    # Update connection information
                    self.update_connection()

            # Update every 100ms
            time.sleep(0.1)

    def run_disconnected_mode(self) -> None:
        """Runs normal mode."""
        self.logger.info("Entered DISCONNECTED")

        # Initialize timing variables
        last_update_time = 0.0
        update_interval = 5  # seconds

        # Loop forever
        while True:

            # Update connection and storage state every update interval
            if time.time() - last_update_time > update_interval:
                last_update_time = time.time()
                self.update_connection()

            # Check for network connect
            if self.is_connected:
                self.mode = modes.CONNECTED

            # Check for events
            self.check_events()

            # Check for transitions
            if self.new_transition(modes.DISCONNECTED):
                break

            # Check if raspberry pi failed initial network connection event
            # This occurs when the user first tries to connect the device to the internet
            # but failed (likely due to incorrect wifi credentials). If this is the case
            # we need to re-enable to raspi access point so the user can try to connect
            # to the internet again.
            # if "raspberry-pi" in os.getenv("PLATFORM") and not self.iot_is_registered:
            #     message = "Detected raspberry pi failed initial network connection event"
            #     self.logger.info(message)

            #     # Make sure the device isn't in the middle of the registration process
            #     time.sleep(10)
            #     if self.iot_is_registered:
            #         break

            #     # Re-enable access point
            #     network_utilities.enable_raspi_access_point()

            # Update every 100ms
            time.sleep(0.1)

        # If completing raspi registration, give the iot manager enough time to
        # establish a new connection
        if "raspberry-pi" in os.getenv("PLATFORM") and self.iot_is_registered:
            timeout = 120  # seconds
            start_time = time.time()

            # Wait for iot to connect to timeout
            while time.time() - start_time < timeout:

                # Check if iot manager has connected yet
                if self.iot_is_connected:
                    return

                # Update every 2 seconds
                time.sleep(2)

            # Handle timeout events
            message = "IoT manager did not connect to cloud after completing raspi registration"
            self.logger.warning(message)

    ##### HELPER FUNCTIONS #############################################################

    def update_connection(self) -> None:
        """Updates connection state."""
        self.is_connected = network_utilities.is_connected()
        if self.is_connected:
            self.ip_address = network_utilities.get_ip_address()
        else:
            self.ip_address = "UNKNOWN"

        self.wifi_ssids = network_utilities.get_wifi_ssids()

    ##### EVENT FUNCTIONS ##############################################################

    def join_wifi(self, request: Dict[str, Any]) -> Tuple[str, int]:
        """ Joins wifi."""
        self.logger.debug("Joining wifi")

        # Get request parameters
        try:
            wifi_ssid = request["wifi_ssid"]
            wifi_password = request["wifi_password"]
        except KeyError as e:
            message = "Unable to join wifi, invalid parameter {}".format(e)
            return message, 400

        # Join wifi
        self.logger.debug("Sending join wifi request")
        try:
            network_utilities.join_wifi(wifi_ssid, wifi_password)
        except Exception as e:
            message = "Unable to join wifi, unhandled exception: {}".format(type(e))
            self.logger.exception(message)
            return message, 500

        # Wait for internet connection to be established
        timeout = 60  # seconds
        start_time = time.time()
        while not network_utilities.is_connected():
            self.logger.debug("Waiting for network connection")

            # Check for timeout
            if time.time() - start_time > timeout:
                message = "Did not connect to internet within {} ".format(timeout)
                message += "seconds of joining wifi, recheck if internet is connected"
                self.logger.warning(message)
                return message, 202

            # Recheck if internet is connected every second
            time.sleep(2)

        # Update connection state
        self.is_connected = True

        # Succesfully joined wifi
        self.logger.debug("Successfully joined wifi")
        return "Successfully joined wifi", 200

    def join_wifi_advanced(self, request: Dict[str, Any]) -> Tuple[str, int]:
        """ Joins wifi."""
        self.logger.debug("Joining wifi advanced")

        # Get request parameters
        try:
            ssid_name = request["ssid_name"]
            passphrase = request["passphrase"]
            hidden_ssid = request["hidden_ssid"]
            security = request["security"]
            eap = request["eap"]
            identity = request["identity"]
            phase2 = request["phase2"]
        except KeyError as e:
            message = "Unable to join wifi advanced, invalid parameter `{}`".format(e)
            return message, 400

        # Join wifi advanced
        self.logger.debug("Sending join wifi request to network utility")
        try:
            network_utilities.join_wifi_advanced(
                ssid_name, passphrase, hidden_ssid, security, eap, identity, phase2
            )
        except Exception as e:
            message = "Unable to join wifi advanced, unhandled exception: {}".format(
                type(e)
            )
            self.logger.exception(message)
            return message, 500

        # Wait for internet connection to be established
        timeout = 60  # seconds
        start_time = time.time()
        while not network_utilities.is_connected():
            self.logger.debug("Waiting for network to connect")

            # Check for timeout
            if time.time() - start_time > timeout:
                message = "Did not connect to internet within {} ".format(timeout)
                message += "seconds of joining wifi, recheck if internet is connected"
                self.logger.warning(message)
                return message, 202

            # Recheck if internet is connected every second
            time.sleep(2)

        # Update connection state
        self.is_connected = True

        # Succesfully joined wifi advanced
        self.logger.debug("Successfully joined wifi advanced")
        return "Successfully joined wifi advanced", 200

    def delete_wifis(self) -> Tuple[str, int]:
        """ Deletes wifi."""
        self.logger.debug("Deleting wifis")

        # Join wifi
        try:
            network_utilities.delete_wifis()
        except Exception as e:
            message = "Unable to delete wifi, unhandled exception: {}".format(type(e))
            self.logger.exception(message)
            return message, 500

        # Wait for internet to be disconnected
        timeout = 10  # seconds
        start_time = time.time()
        while network_utilities.is_connected():
            self.logger.debug("Waiting for internet to disconnect")

            # Check for timeout
            if time.time() - start_time > timeout:
                message = "Did not disconnect from internet within {} ".format(timeout)
                message += "seconds of deleting wifis"
                self.logger.warning(message)
                return message, 202

            # Recheck if internet is connected every second
            time.sleep(2)

        # Update connection state
        self.is_connected = False

        # Succesfully deleted wifi
        self.logger.debug("Successfully deleted wifis")
        return "Successfully deleted wifis", 200

    def disable_raspi_access_point(self) -> Tuple[str, int]:
        """Disables raspberry pi access point."""
        self.logger.debug("Disabling raspberry pi access point")

        try:
            network_utilities.disable_raspi_access_point()
        except Exception as e:
            message = "Unable to disable raspi access point, unhandled exception: {}".format(
                type(e)
            )
            self.logger.exception(message)
            return message, 500

        # Wait for internet connection to be established
        timeout = 60  # seconds
        start_time = time.time()
        while not network_utilities.is_connected():
            self.logger.debug("Waiting for network connection")

            # Check for timeout
            if time.time() - start_time > timeout:
                message = "Did not connect to internet within {} ".format(timeout)
                message += "seconds of joining wifi, recheck if internet is connected"
                self.logger.warning(message)
                return message, 202

            # Recheck if internet is connected every second
            time.sleep(2)

        # Update connection state
        self.is_connected = True

        # Succesfully joined wifi
        self.logger.debug("Successfully disabled raspberry pi access point")
        return "Successfully disabled raspberry pi access point", 200
