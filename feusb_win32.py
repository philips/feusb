"""feusb\feusb_win32.py -- Fascinating Electronics USB CDC Library

The feusb libary supports USB CDC devices from Fascinating Electronics, with
useful features and error detection for USB device suspend and disconnect.

This file provides feusb support on Windows XP and later. To provide Windows
support pywin32 must be installed before this library can be run.

Pywin32 is available as a free download from:
http://sourceforge.net/projects/pywin32/

Feusb does not support legacy RS232 devices or modems.

This file only contains support for Windows. Other files distributed with feusb
provide support for Linux and OS-X.

Do not import this file directly, instead "import feusb". This will load the
correct support file for your operating system automatically.
"""

__author__ = "Ronald M Jackson <Ron@FascinatingElectronics.com>"

__copyright__ = "Copyright 2008 Ronald M Jackson"

__version__ = "1.1"

import win32file
import win32con
import pywintypes
import msvcrt
import exceptions
import time

TIMEOUTS = (0, 0, 20, 0, 1000) #milliseconds - read timeout - write timeout
COMMAND_INTERVAL = 0.001    #seconds - process command to read reply
RETRY_INTERVAL = 0.001      #seconds
RETRY_LIMIT = 20            #max number of read retries per reply
SUSPEND_INTERVAL = 1.000    #seconds
PORT_OK = 'PORT_OK'         #port status conditions
SUSPENDED = 'SUSPENDED'
DISCONNECTED = 'DISCONNECTED'
BEL = '\a'                  #non-printing bel character
ERRNUM_CANNOT_OPEN = 2      #The system cannot find the file specified.
ERRNUM_ACCESS_DENIED = 5    #Access is denied.
ERRNUM_SUSPENDED = 31       #A device attached to the system is not functioning.
ERRNUM_DISCONNECTED = 1167  #The device is not connected.
PURGE_RXCLEAR = 0x0008      #Windows PurgeComm flag
PURGE_TXCLEAR = 0x0004      #Windows PurgeComm flag

def get_ch():
    """Read a keyboard character on all supported operating systems.

    Warning!
    This only works in console (DOS) windows. This function does not work when
    run in the interactive Python window (IDLE).
    """
    if msvcrt.kbhit():
        return msvcrt.getch()
    else:
        return ''

def port_list():
    """Return a list of the available serial ports (as strings)."""
    ports = []
    for port_number in range(1, 257):
        if port_number < 10:
            port = 'COM%d'%port_number
        else:
            port = r'\\.\COM%d'%port_number
        try:
            handle = win32file.CreateFile(port, #port name
                                          win32con.GENERIC_READ |
                                          win32con.GENERIC_WRITE,
                                          0, #exclusive access
                                          None, #no security
                                          win32con.OPEN_EXISTING,
                                          win32con.FILE_ATTRIBUTE_NORMAL,
                                          None) #no template
        except pywintypes.error, e:
            if e[0] != ERRNUM_CANNOT_OPEN and e[0] != ERRNUM_ACCESS_DENIED:
                raise UnexpectedError('Unexpected pywintypes.error in'
                                      'port_list.\n%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
        except Exception, e:
            raise UnexpectedError('Unexpected error in port_list.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))            
        else:
            ports.append(port)
            try:
                win32file.CloseHandle(handle)
            except Exception, e:
                raise UnexpectedError('Unexpected CloseHandle error in '
                                      'port_list.\n%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
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
            self._handle = win32file.CreateFile(self._port_string, #port name
                                                win32con.GENERIC_READ |
                                                win32con.GENERIC_WRITE,
                                                0, #exclusive access
                                                None, #no security
                                                win32con.OPEN_EXISTING,
                                                win32con.FILE_ATTRIBUTE_NORMAL,
                                                None) #no template
            win32file.SetupComm(self._handle, 16384, 16384) #allocate buffers
            win32file.SetCommTimeouts(self._handle, TIMEOUTS)
        except pywintypes.error, e:
            if e[0] == ERRNUM_CANNOT_OPEN or e[0] == ERRNUM_ACCESS_DENIED:
                raise OpenError('Unable to open port %s.'%self._port_string)
            else:
                raise UnexpectedError('Unexpected pywintypes.error in'
                                      '__init__.\n%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
        except Exception, e:
            raise UnexpectedError('Unexpected error in __init__.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))            
        else:
            self._status = PORT_OK
            self.purge()

    def __del__(self):
        """Close the port."""
        try:
            print "DEBUG: Closing %s in __del__."%self._port_string
            win32file.CloseHandle(self._handle)
        except AttributeError:
            print "DEBUG: Attribute error, handle not found in __del__."
            pass #self._handle not found
        except Exception, e:
            print "DEBUG: Unexpected error in __del__."
            raise UnexpectedError('Unexpected error in __del__.\n'
                                  "%s\nDetails: %s"
                                  %(str(type(e)),str(e)))

    def purge(self):
        """Purge input buffer and attempt to purge device responses."""
        if len(self._string_buffer) > 0:
#            print 'DEBUG: Purging string_buffer of %d characters.'%len(self._string_buffer)
            self._string_buffer = ''
        if self._status is DISCONNECTED:
            raise DisconnectError("Port %s is disconnected."
                                  %self._port_string)
        retries = 0
#        print 'DEBUG: Purging characters from device buffer.'
        while retries < RETRY_LIMIT:
            time.sleep(RETRY_INTERVAL)
            try:
                flags, comstat = win32file.ClearCommError(self._handle)
            except pywintypes.error, e:
                if e[0] == ERRNUM_SUSPENDED:
                    self._status = SUSPENDED
                    if self._error_on_suspend:
                        raise SuspendError("Port %s is suspended."
                                           %self._port_string)
                    else:
                        time.sleep(SUSPEND_INTERVAL)
                else:
                    raise UnexpectedError('Unexpected pywintypes.error in '
                                          'purge.\n%s\nDetails: %s'
                                          %(str(type(e)),str(e)))
            except Exception, e:
                raise UnexpectedError('Unexpected error in purge.\n'
                                      '%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
            else:
                if self._status is SUSPENDED:
                    self._status = PORT_OK
                if comstat.cbInQue > 0:
                    retries = 0
                    print comstat.cbInQue,
                    try:
                        win32file.PurgeComm(self._handle,
                                            PURGE_RXCLEAR | PURGE_TXCLEAR)
                    except Exception, e:
                        raise UnexpectedError('Unexpected PurgeComm error '
                                              'in purge.\n'
                                              '%s\nDetails: %s'
                                              %(str(type(e)),str(e)))
                else:
#                    if retries == 0:
#                        print '\nDEBUG: No characters, retry countdown.'
                    retries += 1
#                    print retries,
#        print '\nDEBUG: Exiting purge.'

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
            flags, comstat = win32file.ClearCommError(self._handle)
        except pywintypes.error, e:
            if e[0] == ERRNUM_SUSPENDED:
                self._status = SUSPENDED
                if self._error_on_suspend:
                    raise SuspendError("Port %s is suspended."
                                       %self._port_string)
                else:
                    return len(self._string_buffer)
            else:
                raise UnexpectedError('Unexpected pywintypes.error in '
                                      'raw_waiting.\n%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
        except Exception, e:
            raise UnexpectedError('Unexpected error in raw_waiting.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))
        else:
            if self._status is SUSPENDED:
                self._status = PORT_OK
            in_que = int(comstat.cbInQue) #cbInQue is type long
            if in_que > 0:
                try:
                    hr, buff = win32file.ReadFile(self._handle, in_que)
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
        return self._string_buffer.count('\r\n')

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
        all_replies = self._string_buffer.split("\r\n")
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
            try:
                win32file.WriteFile(self._handle, string)
                win32file.FlushFileBuffers(self._handle)
            except pywintypes.error, e:
                if e[0] == ERRNUM_DISCONNECTED:
                    self._status = DISCONNECTED
                    print "DEBUG: Closing %s in raw_write."%self._port_string
                    win32file.CloseHandle(self._handle)
                    raise DisconnectError("Port %s is disconnected."
                                          %self._port_string)
                elif e[0] == ERRNUM_SUSPENDED:
                    self._status = SUSPENDED
                    if self._error_on_suspend:
                        raise SuspendError("Port %s is suspended."
                                           %self._port_string)
                    else:
                        time.sleep(SUSPEND_INTERVAL)
                else:
                    raise
            else:
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
            win32file.WriteFile(self._handle, BEL)
            win32file.FlushFileBuffers(self._handle)
        except pywintypes.error, e:
            if e[0] == ERRNUM_SUSPENDED:
                self._status = SUSPENDED
            elif e[0] == ERRNUM_DISCONNECTED:
                self._status = DISCONNECTED
                try:
                    win32file.CloseHandle(self._handle)
                except AttributeError:
                    pass #self._handle not found
                except Exception, e:
                    raise UnexpectedError('Unexpected error in status.\n'
                                          '%s\nDetails: %s'
                                          %(str(type(e)),str(e)))
            else:
                raise UnexpectedError('Unexpected pywintypes.error in status.\n'
                                      '%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
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
            self._handle = win32file.CreateFile(self._port_string, #port name
                                                win32con.GENERIC_READ |
                                                win32con.GENERIC_WRITE,
                                                0,  #exclusive access
                                                None, #no security
                                                win32con.OPEN_EXISTING,
                                                win32con.FILE_ATTRIBUTE_NORMAL,
                                                None) #no template
            win32file.SetupComm(self._handle, 16384, 16384)
            win32file.SetCommTimeouts(self._handle, TIMEOUTS)
        except pywintypes.error, e:
            if e[0] == ERRNUM_CANNOT_OPEN or e[0] == ERRNUM_ACCESS_DENIED:
                raise OpenError('Unable to reopen port %s.'%self._port_string)
            else:
                raise UnexpectedError('Unexpected pywintypes.error in'
                                      'reconnect.\n%s\nDetails: %s'
                                      %(str(type(e)),str(e)))
        except Exception, e:
            raise UnexpectedError('Unexpected error in reconnect.\n'
                                  '%s\nDetails: %s'
                                  %(str(type(e)),str(e)))
        else:
            self._status = PORT_OK
            self.purge()
        return self._status

if __name__=='__main__':
    try:
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
            if w == 1:
                break
            print 'Sleeping for 1 mS.'
            time.sleep(.001)
        print 'Testing:  raw_read()\nReply received:\n', dev.raw_read(),
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
        # SUSPEND/RESUME DURING RAW_READ
        print "Testing:  raw_write, raw_waiting, raw_read, error_on_suspend."
        print "Sleep/resume computer to test for read errors."
        print "Disconnect device to end this test."
        NUMCMDS = 240
        dev.raw_write('cs\r')
        while dev.waiting() < 1:
            time.sleep(0.001)
        comparison_string = dev.raw_read()
        comparison_length = len(comparison_string)
        print ("Each 'r' represents %d characters read."
               %(NUMCMDS*comparison_length))
        dev.error_on_suspend(True)
        keep_going = True
        while keep_going:
            while True:
                try:
                    dev.raw_write('s'*NUMCMDS+'\r')
                except SuspendError:
                    print ('SuspendError reported during raw_write(). '
                           'Sleeping 1 second.')
                    time.sleep(1.0)
                except DisconnectError:
                    print 'DisconnectError reported during raw_write().'
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
                    print ('SuspendError reported during raw_waiting(). '
                           'Sleeping 1 second.')
                    time.sleep(1.0)
                else:
                    read_tries += 1
                    if num_of_characters >= comparison_length:
                        read_tries = 0
                        try:
                            response = dev.raw_read(comparison_length)
                        except SuspendError:
                                print ('SuspendError during raw_read(). '
                                       'Sleeping 1 second.')
                                time.sleep(1.0)
                        else:
                            responses_read += 1
                            if response != comparison_string:
                                print "\nResponse does not match expected:"
                                print response
                                print "Purging remaining characters."
                                dev.purge()
                                break
                    if read_tries >= RETRY_LIMIT:
                        print ('\n%d attempted reads without getting a full '
                               'response.'%RETRY_LIMIT)
                        time.sleep(0.500) #time for a disconnect to be detected
                        current_status = dev.status()
                        print 'dev.status() reports: %s'%current_status
                        if current_status is DISCONNECTED:
                            keep_going = False
                            break
                        else:
                            print ('%d responses read correctly so far.'
                                   %responses_read)
                            print ('Number of waiting characters: %d'
                                   %num_of_characters)
                            if num_of_characters > 0:
                                print 'Response at this time:'
                                print dev.raw_read()
                        print 'Port is probably unresponsive.'
                        ri = raw_input('Hit <enter> to exit, or any key '
                                       '<enter> to disconnect and reconnect ->')
                        if ri == '':
                            exit()
                        else:
                            print '*** Unplug the device ***'
                            old_stat = ''
                            stat = ''
                            while stat is not DISCONNECTED:
                                stat = dev.status()
                                if old_stat is not stat:
                                    print 'Device status is:', stat
                                old_stat = stat
                                time.sleep(0.050)
                            print '*** Plug in the device ***'
                            while True:
                                try:
                                    dev.reconnect()
                                except OpenError:
                                    time.sleep(0.050)
                                else:
                                    break
                            print 'Device status is:', dev.status()
                            break
                    time.sleep(RETRY_INTERVAL)
            if responses_read == NUMCMDS:
                print 'r',
        dev.error_on_suspend(False)
        if dev.status() is not PORT_OK:        
            print '*** Plug in the device ***'
            while True:
                try:
                    dev.reconnect()
                except OpenError:
                    time.sleep(0.100)
                else:
                    break
        # SUSPEND/RESUME DURING READ
        print "Testing:  read (and consequently write)."
        print "Sleep/resume computer to test for read errors."
        print "Disconnect device to end this test."
        NUMCMDS = 240
        dev.raw_write('S\r')
        while dev.waiting() < 1:
            time.sleep(RETRY_INTERVAL)
        comp_len = dev.raw_waiting()
        comp = dev.read()
        print ("Each '*' represents %d characters and %d commands read."
               %(comp_len*NUMCMDS, NUMCMDS))
        while True:
            try:
                responses = dev.read('S'*NUMCMDS, NUMCMDS)
            except DisconnectError, e:
                print 'DisconnectError reported during read().'
                print 'Details:\n', e
                break
            except ReadTimeoutError, e:
                print 'ReadTimeoutError reported during read().'
                print 'Details:\n', e
                print '%d characters in input buffer.'%dev.raw_waiting()
                print '%d responses in input buffer.'%dev.waiting()
                print 'Purging port.'
                dev.purge()
                # test port status (could have timed out due to disconnect)
                print 'Testing port status.'
                status = dev.status()
                while status is not PORT_OK:
                    if status == DISCONNECTED:
                        print 'Port status is actually DISCONNECTED.'
                        break
                    elif status == SUSPENDED:
                        print 'Status is SUSPENDED. Sleeping 1 second.'
                        time.sleep(1.000)
                    status = dev.status()
                if status is DISCONNECTED:
                    break
                elif status is PORT_OK:
                    print 'Port status returns PORT_OK.'
                else:
                    print 'Port status error!'
                try:        # test for port unresponsive
                    response = dev.read('U')
                except DisconnectError, e:
                    print 'DisconnectError reported testing responsiveness.'
                    print 'Details:\n', e
                    break
                except ReadTimeoutError, e:
                    print 'ReadTimeoutError reported testing responsiveness.'
                    print 'Details:\n', e
                    print 'Port is unresponsive.'
                    print '*** Unplug the device ***'
                    old_stat = ''
                    stat = ''
                    while stat is not DISCONNECTED:
                        stat = dev.status()
                        if old_stat is not stat:
                            print 'Device status is:', stat
                        old_stat = stat
                        time.sleep(0.050)
                    break
                else:
                    print 'Port checks out OK.'
            else:
                match = 0
                for response in responses:
                    if comp == response:
                        match += 1
                    else:
                        print 'Expected: %s Got: %s'%(repr(comp),repr(response))
                if match == NUMCMDS:
                    print '*',
                else:
                    print '\n%d of %d match correctly.'%(match, NUMCMDS)
        print 'Reconnecting.'
        while True:
            try:
                dev.reconnect()
            except OpenError:
                time.sleep(0.100)
            else:
                break
        # GET_CH() TEST
        print 'WARNING:  get_ch() only works in a console window,'
        print 'it will cause the interactive Python window (IDLE) to hang.'
        print 'Type any char <enter> to test get_ch, <enter> alone to skip -->',
        if raw_input() != '':
            print 'Testing:  get_ch()  Type any character for get_ch -->',
            got = get_ch()
            while got == '':
                time.sleep(0.010)
                got = get_ch()
            print repr(got)
        del(dev)
        raw_input("Tests complete. Hit <enter> to exit -->")
    except Exception, e:
        print "Unhandled main program exception!!!"
        print type(e)
        print e
        raw_input("Hit enter to exit ->")
        
