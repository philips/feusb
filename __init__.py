"""feusb\__init__.py -- Fascinating Electronics USB CDC Library

This libary provides support for USB CDC-class devices, specifically the
Fascinating Electronics USB-series modules. The Feusb class transparently
handles USB suspends (or optionally generates errors on suspends), and with
user program supervision supports disconnection and reconnection of hardware.

This library does not support legacy RS232 devices or modems! Legacy serial
port properties, such as baud rates, are not supported.

Identical support is provided on Windows (XP or later), Linux and OS-X.

Port Status Constants:
---------------------
PORT_OK, SUSPENDED, DISCONNECTED

Non-Class Functions:
-------------------
get_ch()  Read a keyboard character on all supported operating systems.
port_list()  Return a list of the available serial ports (as strings).

Exceptions:
----------
FeusbError  Base class for exceptions raised in the FEUSB class.
OpenError  Unsuccessful opening the port.
SuspendError  The device is in a USB suspend state (optional error).
DisconnectError  The device has been disconnected.
ReadTimeoutError  The device hasn't returned the requested number of replies.
UnexpectedError  Please report the error message and what appeared to cause the
                 error to Ron@FascinatingElectronics.com. We strive to make
                 this library as robust as possible. Thank-you!

FEUSB Class:
-----------
Class for serial ports. Class methods are:
__init__(port_string, error_on_suspend)  Open the port and allocate buffers.
__del__()  Close the port.
error_on_suspend(new_error_on_suspend)  Return error_on_suspend, optional set.
raw_waiting()  Update buffer, return the number of characters available.
waiting()  Update buffer, return the number of replies available.
raw_read(limit)  Return any characters available (string), with optional limit.
read(command, count)  Send command, return replies stripped of text, blocking.
raw_write(string)  Write a command string to the port.
write(command)  Write commands as UPPERCASE terminated with '\r' to the port.
raw_status()  Return the port's recent status, but don't perform a test.
status()  Test and return the port's status without asserting exceptions.
reconnect()  Reconnect a port that had been DISCONNECTED, return status.
"""

__author__ = "Ronald M Jackson <Ron@FascinatingElectronics.com>"

__copyright__ = "Copyright 2008 Ronald M Jackson"

__version__ = "1.0"

import sys

if sys.platform == 'win32':
    from feusb_win32 import *
elif sys.platform == 'linux2':
    from feusb_linux import *
elif sys.platform == 'darwin':
    from feusb_darwin import *
else:
    sys.exit('Your operating system is not supported.')
