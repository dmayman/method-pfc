#!/usr/bin/env python3

# Import standard python modules
import os, time, sys

if len(sys.argv) < 4:  # no command line args
    print(
        "Please provide the MCP address (0x47), port (0 to 7) and output(0 to 0xFF) on the command line"
    )
    exit(1)

# Import usb-to-i2c communication modules
from pyftdi.i2c import I2cController

# Ensure virtual environment is activated
if os.getenv("VIRTUAL_ENV") == None:
    print("Please activate your virtual environment then re-run script")
    exit(0)

# Ensure platform info is sourced
if os.getenv("PLATFORM") == None:
    print("Please source your platform info then re-run script")
    exit(0)

# Ensure platform is usb-to-i2c enabled
if os.getenv("IS_USB_I2C_ENABLED") != "true":
    print("Platform is not usb-to-i2c enabled")
    exit(0)

# Initialize i2c instance
print("I2C cable init...")
i2c_controller = I2cController()
i2c_controller.configure("ftdi://ftdi:232h/1")
address = int(sys.argv[1], 16)
print("I2C address 0x{:2X}".format(address))
i2c = i2c_controller.get_port(address)

# Get the port from the command line
port = int(sys.argv[2])
byte = 0x30 + port

# Get the value in hex from the command line
value = int(sys.argv[3], 16)

# Set the port high
print("Port={} value={}/0x{:2X}".format(port, value, value))
i2c.write([byte, value, 0x00])
