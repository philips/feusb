"""feusb\feusb_win32.py -- Fascinating Electronics USB CDC Library

The feusb libary supports USB CDC devices from Fascinating Electronics, with
useful features and error detection for USB device suspend and disconnect.

Feusb does not support legacy RS232 devices or modems.

This file only contains support for Windows. Other files distributed with feusb
provide support for Linux and OS-X.

Do not import this file directly, instead "import feusb". This will load the
correct support file for your operating system automatically.
"""

__author__ = "Brandon Philips <brandon@ifup.org"

__copyright__ = "Copyright 2008 Ronald M Jackson, Brandon D Philips"

__version__ = "1.1"

import exceptions
import time
import sys
import glob
import os
import select
import struct
import fcntl

TIMEOUTS = (0, 0, 1000, 0, 1000) #milliseconds - read timeout - write timeout
COMMAND_INTERVAL = 0.001    #seconds - process command to read reply
RETRY_INTERVAL = 0.001      #seconds
RETRY_LIMIT = 100           #max number of read retries per reply
SUSPEND_INTERVAL = 1.0      #seconds
PORT_OK = 'PORT_OK'         #port status conditions
SUSPENDED = 'SUSPENDED'
DISCONNECTED = 'DISCONNECTED'
UNRESPONSIVE = 'UNRESPONSIVE'
BEL = '\a'                  #non-printing bel character
ERRNUM_CANNOT_OPEN = 2      #The system cannot find the file specified.
ERRNUM_ACCESS_DENIED = 5    #Access is denied.
ERRNUM_SUSPENDED = 31       #A device attached to the system is not functioning.
ERRNUM_DISCONNECTED = 1167  #The device is not connected.

import termios
TIOCM_zero_str = struct.pack('I', 0)
TIOCINQ   = hasattr(termios, 'FIONREAD') and termios.FIONREAD


def port_list():
    """Return a list of the available serial ports (as strings)."""
    ports = []
    list = []
    list.extend(glob.glob('/dev/ttyACM*'))
    list.extend(glob.glob('/dev/fercs*'))
    for port in list:
        try:
            p = Feusb(port)
        except OpenError:
            pass
        else:
            ports.append(port)
            del p
    return ports


class FeusbError(Exception):
    """Base class for exceptions raised in the Feusb class."""
    pass

class OpenError(FeusbError):
    """Unsuccessful opening the port."""
    pass

class SuspendError(FeusbError):
    """The device is in a USB suspend state."""
    pass

class DisconnectError(FeusbError):
    """The device has been disconnected."""
    pass

class ReadTimeoutError(FeusbError):
    """The device hasn't returned the requested number of replies in time."""
    pass

class UnexpectedError(FeusbError):
    """An error occurred that was not part of normal operation."""
    pass

class Feusb:
    """Fascinating Electronics USB-CDC device class."""
    
    def __init__(self, port_string, error_on_suspend=False):
        """Open the port and allocate buffers."""
        self._port_string = port_string
        self._error_on_suspend = error_on_suspend
        self._string_buffer = ''
        self._status = DISCONNECTED
        try:
            self._handle = open(self._port_string, "r+")
	except exceptions.IOError, e:
		raise OpenError()
        except Exception, e:
            raise UnexpectedError('Unexpected error in __init__.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))
        else:
            self._status = PORT_OK

    def __del__(self):
        """Close the port."""
        if hasattr(self, "_handle"):
            self._handle.close()

    def error_on_suspend(self, new_error_on_suspend=None):
        """Return error_on_suspend status, with optional set parameter."""
        if new_error_on_suspend is True:
            self._error_on_suspend = True
        elif new_error_on_suspend is False:
            self._error_on_suspend = False
        return self._error_on_suspend

    def raw_waiting(self):
        """Update buffer, return the number of characters available."""
        if self._status is DISCONNECTED:
            raise DisconnectError("Port %s needs to be reconnected."
                                  %self._port_string)
        try:
            s = fcntl.ioctl(self._handle, TIOCINQ, TIOCM_zero_str)
            in_que = struct.unpack('I',s)[0]
        except Exception, e:
            raise UnexpectedError('Unexpected error in raw_waiting.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))
        else:
            if self._status is SUSPENDED:
                self._status = PORT_OK
            if in_que > 0:
                try:
                     buff = self._handle.read(in_que)
                except Exception, e:
                    raise UnexpectedError('Unexpected ReadFile error '
                                          'in raw_waiting.\n'
                                          '%s\nDetails: %s'
                                          %(str(type(e)),str(e)))
                else:
                    self._string_buffer += buff
                    if len(buff) < in_que:
                        raise UnexpectedError('ReadFile in raw_waiting '
                                              'returned fewer characters '
                                              'than expected.\n'
                                              'Expected: %d  Got: %d'%
                                              (in_que, len(buff)))
        return len(self._string_buffer)

    def waiting(self):
        """Update buffer, return the number of replies available."""
        self.raw_waiting()  #update _string_buffer
        return self._string_buffer.count('\n')

    def raw_read(self, limit=None):
        "Return any characters available (a string), with an optional limit."
        char_count = self.raw_waiting()  #update _string_buffer
        if char_count <= limit or limit is None:
            split_location = char_count
        else:
            split_location = limit
        ret_str = self._string_buffer[:split_location]
        self._string_buffer = self._string_buffer[split_location:]
        return ret_str

    def read(self, command=None, count=1):
        """Send command, return replies stripped of text, blocking if necessary.

        Replies are stripped of text, leaving just integers or floats.
        For a single line reply, either a number or tuple is returned.
        For a multi-line reply, a list of numbers and tuples is returned.
        When the command count > 1, a list of the above is returned.
        """
        if command is not None:
            self.write(command)
            time.sleep(COMMAND_INTERVAL)
        current_replies = self.waiting()
        old_replies = current_replies
        retries = 0
        while current_replies < count:
            if self._status is SUSPENDED:
                time.sleep(SUSPEND_INTERVAL)
            else:
                if current_replies == old_replies:
                    retries += 1
                    if retries == RETRY_LIMIT:
                        status = self.status()
                        if status is DISCONNECTED:
                            raise DisconnectError('Port %s is disconnected.'%
                                                  self._port_string)
                        elif status is SUSPENDED:
                            raise UnexpectedError('Unexpected error in read(): '
                                                  'Port %s is suspended, but '
                                                  "the suspend wasn't caught "
                                                  'in waiting() as expected.'%
                                                  self._port_string)
                        else:
                            raise ReadTimeoutError("Feusb method read() took "
                                                   "more than %4.3f seconds "
                                                   "per reply."%
                                                   (RETRY_INTERVAL*RETRY_LIMIT))
                else:
                    retries = 0
                    old_replies = current_replies
                time.sleep(RETRY_INTERVAL)
            current_replies = self.waiting()
        all_replies = self._string_buffer.split("\n")
        return_value = []
        for i in range(count):
            reply_lines = all_replies.pop(0).splitlines()
            command_reply = []
            for line in reply_lines:
                token_list = line.split()
                line_reply = []
                for token in token_list:
                    if token[0].isalpha():
                        pass
                    elif '.' in token:
                        line_reply.append(float(token))
                    else:
                        line_reply.append(int(token))
                if len(line_reply) > 1:
                    command_reply.append(tuple(line_reply))
                elif len(line_reply) == 1:
                    command_reply.append(line_reply[0])
            if len(command_reply) == 1:
                return_value.append(command_reply[0])
            else:
                return_value.append(command_reply)
        self._string_buffer = "\r\n".join(all_replies)
        if len(return_value) == 1:
            return return_value[0]
        else:
            return return_value
            
    def raw_write(self, string=''):
        """Write a command string to the port.

        The string should end with <return> or <newline> characters ('\r' or
        '\n') if you want the module to start processing the command now.
        """
        if self._status is DISCONNECTED:
            raise DisconnectError("Port %s needs to be reconnected before use."
                                  %self._port_string)
        while True:
            self._handle.write(string)
            self._handle.flush()
            self._status = PORT_OK
            return

    def write(self, command=''):
        """Write commands as UPPERCASE terminated with '\r' to the port."""
        if not (command.endswith('\r') or command.endswith('\n')):
            command += '\r'
        self.raw_write(command.upper())

    def raw_status(self):
        """Return the port's recent status, but don't perform a test."""
        return self._status
    
    def status(self):
        """Test and return port status without asserting exceptions."""
        if self._status is DISCONNECTED:
            return self._status
        try:
            self._handle.write(BEL)
            self._handle.flush()
	except IOError, e:
            if e.errno == 5:
                self._status = DISCONNECTED
        except Exception, e:
            raise UnexpectedError('Unexpected error in status.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))
        else:
            self._status = PORT_OK
        return self._status

    def reconnect(self):
        """Reconnect a port that had been DISCONNECTED, return status."""
        if self._status is not DISCONNECTED:
            raise OpenError("Port %s is not disconnected."%self._port_string)
        try:
            self._handle.close()
            self._handle = open(self._port_string, "r+")
            #NEED TO FLUSH COMM READ BUFFER HERE
        except IOError, e:
            raise OpenError('Unable to reopen port %s.'%self._port_string)
        except Exception, e:
            raise UnexpectedError('Unexpected error in reconnect.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))
        else:
            self._string_buffer = ''
            self._status = PORT_OK
        return self._status

if __name__=='__main__':
    print 'feusb_win32 - Fascinating Electronics USB comm port class.'
    # OPEN THE PORT
    while True:
        print '\nAvailable Ports\nSEL   Comm Port\n---   ---------'
        ports = ['Quit'] + port_list()
        for i, v in enumerate(ports):
            print '%3d     %s'%(i, v)
        try:
            sel = abs(int(raw_input('Select a comm port or 0 to Quit -->')))
            ports[sel]
        except Exception:
            print 'Acceptable values are 0 to %d.'%i
        else:
            if sel == 0:
                exit()
            else:
                print "Testing:  Feusb('%s')"%ports[sel]
                try:
                    dev = Feusb(ports[sel])
                except OpenError, e:
                    sys.stderr.write(str(e)+'\n')
                else:
                    break
    # RAW READ AND WRITE AND WAITING TESTS
    print "Testing:  raw_write('u\\r')"
    dev.raw_write('u\r')
    print 'Testing:  raw_waiting() and waiting()'
    while True:
        rw = dev.raw_waiting()
        w = dev.waiting()
        print 'raw_waiting() returned:  %d'%rw
        print 'waiting() returned:  %d'%w
        if w > 1:
            break
        print 'Sleeping for 1 mS.'
        time.sleep(.001)
    print 'Testing:  raw_read()\nReply received below:\n', dev.raw_read(),
    # NUMERIC READ FORMAT TESTS
    print "Testing:  read('m1')"
    print 'Reply received:  ', dev.read('m1')
    print "Testing:  read('s1')"
    print 'Reply received:  ', dev.read('s1')
    print "Testing:  read('m')"
    print 'Reply received:  ', dev.read('m')
    print "Testing:  read('m1s1m', 3)"
    print 'Reply received:\n', dev.read('m1s1m', 3)
    print "Testing:  read('s')"
    r = repr(dev.read('s'))
    print 'Reply received:'
    print r[:56]
    print r[56:112]
    print r[112:168]
    print r[168:]
    # STATUS TESTS
    print 'Testing:  status()\n*** Unplug the device ***'
    old_stat = ''
    while True:
        stat = dev.status()
        if old_stat is not stat:
            print 'Device status is: ', stat
        old_stat = stat
        if stat is DISCONNECTED:
            break
        time.sleep(0.050)
    print 'Testing:  reconnect()'
    while True:
        try:
            dev.reconnect()
        except OpenError, e:
            time.sleep(0.100)
        else:
            print "Verifying reconnect:"
            dev.raw_write('u\r')
            while dev.waiting() < 1:
                print 'Sleeping for 1 mS.'
                time.sleep(0.001)
            print dev.raw_read(),
            break
    # SUSPEND/RESUME DURING READ
    print "Testing:  raw_write, raw_waiting, raw_read, error_on_suspend."
    print "Sleep/resume computer to test for read errors."
    print "Disconnect device to end the test."
    NUMCMDS = 240
    dev.raw_write('cs\r')
    while dev.waiting() < 1:
        time.sleep(0.001)
    comparison_string = dev.raw_read()
    comparison_length = len(comparison_string)
    print "Each 'r' represents %d characters read."%(NUMCMDS*comparison_length)
    dev.error_on_suspend(True)
    keep_going = True
    while keep_going:
        while True:
            try:
                dev.raw_write('s'*NUMCMDS+'\r')
            except SuspendError:
                print "SuspendError reported during raw_write().",
                print "Sleeping 1 second."
                time.sleep(1.0)
            except DisconnectError:
                print "DisconnectError reported during raw_write()."
                keep_going = False
                break
            else:
                print 'w',
                break
        read_tries = 0
        responses_read = 0
        while keep_going and responses_read < NUMCMDS:
            try:
                num_of_characters = dev.raw_waiting()
            except SuspendError:
                print "SuspendError reported during raw_waiting(). ",
                print "Sleeping 1 second."
                time.sleep(1.0)
            else:
                read_tries += 1
                if num_of_characters >= comparison_length:
                    read_tries = 0
                    try:
                        response = dev.raw_read(comparison_length)
                    except SuspendError:
                            print "SuspendError during raw_read(). ",
                            print "Sleeping 1 second."
                            time.sleep(1.0)
                    else:
                        responses_read += 1
                        if response != comparison_string:
                            print "\nResponse does not match expected:"
                            print response
                            #flush remaining buffer
                            print "Flushing remaining characters."
                            while len(response) > 0:
                                time.sleep(0.25)
                                try:
                                    response = dev.raw_read()
                                except SuspendError:
                                    print "SuspendError while flushing buffer."
                                    time.sleep(0.75)
                                else:
                                    print "Flushed %d characters."%len(response)
                            break
                if read_tries >= 10:
                    print "10 attempted reads without getting a full response."
                    current_status = dev.status()
                    print "dev.status() reports: %s"%current_status
                    if current_status is DISCONNECTED:
                        keep_going = False
                    else:
                        print "%d responses read correctly so far."%responses_read
                        print "Number of waiting characters: ", num_of_characters
                        if num_of_characters > 0:
                            print "Response at this time:"
                            print dev.raw_read()
                        break
                time.sleep(0.002)
        if responses_read == NUMCMDS:
            print 'r',
    print 'Reconnecting.'
    while True:
        try:
            dev.reconnect()
        except OpenError:
            time.sleep(0.100)
        else:
            break
    # *********** THIS MAY HAVE BEEN HANDLED BY THE PREVIOUS TESTING ***********
    print "Read-Suspend Testing. Suspend and resume computer several times."
    print "To exit this test, disconnect the device and reattach."
    read_count = 0
    while read_count != -1:
        read_count += 1
        try:
            anA, sA = dev.read('ms', 2)
            sB, anB = dev.read('sm', 2)
        except DisconnectError, e:
            print "%s Reconnect to continue."%e
            while True:
                try:
                    dev.reconnect()
                except OpenError, e:
                    time.sleep(0.100)
                else:
                    read_count = -1
                    break
        except ReadTimeoutError, e:
            print "Unexpected ReadTimeoutError! %s"%e
        except FeusbError, e:
            print "Unexpected FeusbError! %s"%e
        else:
            if (len(anA) == 8 and len(sA) == 16 and
                len(sB) == 16 and len(anB) == 8):
                if read_count % 100 == 0:
                    print "Reads are OK %6i times."%read_count
            else:
                print "Read value length mismatch occurred."
                read_count = 0
