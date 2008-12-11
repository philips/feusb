"""TestRCS.py -- Fascinating Electronics RC Servo control module test program.

Initializes and runs the servos at varying accelerations with the positions
displayed in graphical bars. Analog voltages are measured and similarly
displayed.

Important: This program is written for Windows and uses the WConio display
interface.

In addition to Python2.5 or later, you must download and install:
feusb      http://FascinatingElectronics.com
PyWin32    http://sourceforge.net/projects/pywin32/
WConio     http://newcenturycomputers.net/projects/wconio.html
"""

__author__ = "Ronald M Jackson <Ron@FascinatingElectronics.com>"

__copyright__ = "Copyright 2008 Ronald M Jackson"

__version__ = "1.1"

import WConio
from feusb import *

##########  Constants  ##########

# Analog to digital converter constants
ANALOG_MAX = 16380  #4092 or 16380

# Graphics constants
FULL_BAR = '\xDB'
HALF_BAR = '\xDD'
SPACE = '\x20'

# Servo motion constants
SERVO_MIN = 9000    # USB-RCS minimum is  6,500
SERVO_MAX = 27000   # USB-RCS maximum is 29,500
SERVO_RANGE = SERVO_MAX - SERVO_MIN
SERVO_STEP = (SERVO_MAX - SERVO_MIN) / 15
SERVO_INIT_DELAY = 10

# Servo motion modes
INIT = 'Init'
RUN = 'Run'
BRAKE = 'Brake'
IDLE = 'Idle'

# Servo motion directions
F = 'Forward'
R = 'Reverse'

##########  Display Routines  ##########

def display_once(firmware_version):
    """Display static information, call once."""
    WConio.textattr(0x70)
    WConio.clrscr()
    # Display Firmware Version or Firmware Status.
    WConio.gotoxy(2, 0)
    if firmware_version < 1.0:
        WConio.textattr(0xc0)
        WConio.cputs(' Firmware Unreliable!   ')
    else:
        WConio.textattr(0xa0)
        WConio.cputs(' Firmware Version %2.2f '%firmware_version)
    # Display servo static labels.
    WConio.gotoxy(0, 2)
    WConio.textattr(0x70)
    WConio.cputs(' S# Acc #Q Cyc Speed Pos mS\n')
    for i in range(1, 17):
        WConio.cputs(' %2i\n'%i)
    # Display analog channel labels.
    WConio.gotoxy(0, 20)
    WConio.textattr(0x70)
    WConio.cputs    (' C#  Voltage                             C#  Voltage')
    for i in range(1, 5):
        WConio.cputs('\n  %i                                       %i'%
                     (i, i+4))

def display_update():
    """Display changing information, call repeatedly."""
    # Display the Disable Input Status.
    WConio.gotoxy(28, 0)
    if disabled:
        WConio.textattr(0xc0)
        WConio.cputs('   Enable Input Open -- All Servos Are Held Idle   ')
    else:
        WConio.textattr(0xa0)
        WConio.cputs('Enable Input Shorted -- Servo Positioning Permitted')
    # Display the servo command mode.
    WConio.gotoxy(28, 2)
    WConio.textattr(0x70)
    if command_mode is INIT:
        WConio.cputs('Servos held initialized:  AnyKey to run, Q to quit.')
    elif command_mode is RUN:
        WConio.cputs('Servos allowed to run:  AnyKey to brake, Q to quit.')
    elif command_mode is BRAKE:
        WConio.cputs('Servos braking:   AnyKey to idle servos, Q to quit.')
    elif command_mode is IDLE:
        WConio.cputs('Servos held idle:  AnyKey to initialize, Q to quit.')
    else:
        WConio.cputs('Error:  Unrecognized command mode!!!     Q to quit.')
    # Display servo cycle, speed, position in mS and position bar graph.
    for i, each_servo in enumerate(all_servos):
        WConio.gotoxy(4, 3 + i)
        WConio.textattr(0x70)
        # Cyc..Spd..Pos mS
        if accel_dif:
            accel = accel_list[i]
        else:
            accel = 1
        WConio.cputs('%3i %2i %3i %5i %01.4f'
                     %(accel, each_servo[3], each_servo[2], each_servo[1],
                       each_servo[0]/12000.0))
        color = 0x2b if i % 2 else 0x2a  #2a is green, 9b is blue
        display_bar(28, 3 + i, color,
                    float(each_servo[0] - SERVO_MIN) / SERVO_RANGE, 51)
    # Display analog measurement values.
    for i, each_channel in enumerate(analog_channels):
        color = 0x3b if i % 2 else 0x3a #a is green, b is blue
        volts = each_channel * 5.0 / ANALOG_MAX
        if i < 4:
            xoffset = 0
            yoffset = i
        else:
            xoffset = 40
            yoffset = i-4
        WConio.gotoxy(5 + xoffset, 21 + yoffset)
        WConio.textattr(0x70)
        WConio.cputs('%01.4fv'%volts)
        display_bar(13 + xoffset, 21 + yoffset, color, volts/5.0, 26)

def display_bar(xcol, yrow, color, division, width):
    """Display a bar of 'color' and 'width', with two sections at 'division'."""
    full_cells, cell_frac = divmod(int(width * division * 3), 3)
    if division < 0:
        display_string = SPACE * width
    elif full_cells == width:
        display_string = FULL_BAR * width
    elif cell_frac == 0:
        display_string = FULL_BAR * full_cells + SPACE * (width - full_cells)
    elif cell_frac == 1:
        display_string = FULL_BAR * full_cells + HALF_BAR + SPACE * (width - full_cells - 1)
    else:
        display_string = FULL_BAR * (full_cells + 1) + SPACE * (width - full_cells - 1)
    WConio.gotoxy(xcol, yrow)
    WConio.textattr(color)
    WConio.cputs(display_string)

########## Command String Routines ##########

def servo_init_string():
    """Create servo INIT command string (call once)."""
    cmd = ['A 0']   # initialize to all analog input configuration
    for i in range(0, 16):  # initialize servo positions individually
        cmd.append('I %i %i %i'%
                   (i+1, SERVO_MIN + i * SERVO_STEP, SERVO_INIT_DELAY))
    cmd.append('I')         # then start servos initializing
    return ' '.join(cmd)

def servo_run_strings():
    """Create servo RUN command strings (call all during RUN)."""
    global next_dir
    cmd1 = cmd2 = []
    cmd_count = 0
    for i, each_servo in enumerate(all_servos):
        if each_servo[3] < 2:
            cmd_count += 1
            if next_dir[i] is F:
                cmd1.append('Q %i %i 2300 %i' % (i+1, SERVO_MAX, accel[i]))
                next_dir[i] = R
            else:
                cmd1.append('Q %i %i 2300 %i' % (i+1, SERVO_MIN, accel[i]))
                next_dir[i] = F
            if cmd_count == 8:
                cmd2 = cmd1
                cmd1 = []
    return ' '.join(cmd1), ' '.join(cmd2)

########## Device Interface ##########

def get_rcs():
    """Connect to the RCS on a user selected port."""
    while True:
        WConio.cputs('Available Ports\nSEL   Comm Port\n---   ---------\n')
        ports = ['Quit'] + port_list()
        for i, v in enumerate(ports):
            WConio.cputs('%3d     %s\n'%(i, v))
        sel_str = raw_input('Select a comm port or 0 to Quit -->')
        try:
            sel = int(sel_str)
            ports[sel]
        except Exception:
            WConio.cputs('\nAcceptable values are 0 to %d.\n'%i)
        else:
            if sel == 0:
                exit()
            elif sel > 0:
                try:
                    rcs = Robust_Feusb(ports[sel])
                except OpenError, e:
                    WConio.cputs(str(e)+'\n')
                else:
                    return rcs
            else:
                WConio.cputs('\nAcceptable values are 0 to %d.\n'%i)

class Robust_Feusb(Feusb):
    """Feusb with error handlers."""
    
    def robust_write(self, command = ''):
        """Write to the RCS with robust exception handling."""
        try:
            self.write(command)
        except DisconnectError:
            global servo_mode
            servo_mode = IDLE
            # Blank screen due to device disconnect.
            WConio.textattr(0xb0)
            WConio.clrscr()
            WConio.gotoxy(10, 10)
            WConio.cputs('USB-RCS has been disconnected during write. '
                         'Trying to reconnect. ')
            self.robust_reconnect()
            usb = rcs.robust_read('U')
            firmware_version = usb[2]
            display_once(firmware_version)
        except Exception, e:
            WConio.textattr(0xc0)
            WConio.clrscr()
            WConio.gotoxy(0, 10)
            print "Unexpected exception in robust_write: ", type(e)
            print
            print e
            print
            raw_input("Press enter to exit ->")
            exit()

    def robust_read(self, command = None, count = 1):
        """Read from the RCS with robust exception handling."""
        global servo_mode
        while True:
            try:
                return self.read(command, count)
            except DisconnectError:
                servo_mode = IDLE
                # Blank screen due to device disconnect.
                WConio.textattr(0xb0)
                WConio.clrscr()
                WConio.gotoxy(10, 10)
                WConio.cputs('USB-RCS has been disconnected during read. '
                             'Trying to reconnect. ')
                self.robust_reconnect()
                usb = rcs.robust_read('U')
                firmware_version = usb[2]
                display_once(firmware_version)
            except ReadTimeoutError, e:
                servo_mode = IDLE
                # Blank screen due to device disconnect.
                WConio.textattr(0xc0)
                WConio.clrscr()
                WConio.gotoxy(10, 10)
                WConio.cputs('USB-RCS read timeout: '
                             'Communications is not responding as expected.')
                WConio.gotoxy(10, 12)
                raw_input("Unplug the USB-RCS.")
                while self.status() != DISCONNECTED:
                    time.sleep(0.500)
                WConio.gotoxy(10, 12)
                WConio.cputs("Now, plug-in the USB-RCS.")
                self.robust_reconnect()
                usb = rcs.robust_read('U')
                firmware_version = usb[2]
                display_once(firmware_version)
            except Exception, e:
                WConio.textattr(0xc0)
                WConio.clrscr()
                WConio.gotoxy(0, 10)
                print "Unexpected exception in robust_read: ", type(e)
                print e
                raw_input("Press enter to exit ->")
                exit()

    def robust_reconnect(self):
        """Reconnect with exception handling."""
        recon_count = 0
        while True:
            time.sleep(0.500)
            try:
                self.reconnect()
            except OpenError:
                recon_count += 1
                WConio.gotoxy(20, 14)
                WConio.cputs(' Reconnect retry attempts: %5i '%
                             recon_count)
            except Exception, e:
                WConio.gotoxy(5, 16)
                print "Unexpected exception during reconnect:", type(e)
                print e
                raw_input("Press enter to exit ->")
                exit()
            else:
                return

########## Main Routine ##########
if __name__=='__main__':
    try:
        WConio.settitle("TestRCS -- Test the RC Servo Controller")
        # Initial Page, Select and Open the Serial Port
        WConio.textattr(0x07)
        WConio.setcursortype(2)
        rcs = get_rcs()   # select a port and open the rcs
        WConio.setcursortype(0)
        WConio.cputs("\nCommunications port is open!\n")
        time.sleep(0.5)
        # disable servos, configure analog, read:  USB report, servo status, analog
        usb, all_servos, analog_channels  = rcs.robust_read('CA0USM', 3)
        firmware_version = usb[2]
        disabled = (all_servos[-1][-1] == -1)

        # Servo and Analog Display Page
        servo_mode = IDLE   # Set up variables for running servos
        command_mode = INIT
        accel_dif = False
        accel_list = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 255]
        display_once(firmware_version)      # Display static and initial items

        while True:
            if len(all_servos) == 16: #check for valid servo data
                display_update()
            # 'Q' to quit, otherwise sequence through the servo command modes
            if WConio.kbhit():
                key_num, key_str = WConio.getch()
                if key_str.upper() == 'Q':
                    try:
                        rcs.robust_write('C')  #stop all servos at exit
                        del(rcs)        #close serial port
                    except:
                        pass
                    exit()
                elif command_mode is INIT:
                    command_mode = RUN 
                elif command_mode is RUN:
                    command_mode = BRAKE
                elif command_mode is BRAKE:
                    command_mode = IDLE
                else:
                    command_mode = INIT
                    accel_dif = not accel_dif
            # Create command strings and update the servo mode
            cmd1 = ''
            cmd2 = ''
            if not disabled:
                if command_mode is BRAKE:
                    if servo_mode is not BRAKE:
                        cmd1 = 'B'
                        servo_mode = BRAKE
                elif command_mode is IDLE:
                    if servo_mode is not IDLE:
                        cmd1 = 'C'
                        servo_mode = IDLE
                elif servo_mode is BRAKE:
                    cmd1 = 'C'
                    servo_mode = IDLE
                elif servo_mode is IDLE:
                    cmd1 = servo_init_string()
                    next_dir = [F, F, F, F, F, F, F, F, F, F, F, F, F, F, F, R]
                    servo_mode = INIT
                elif command_mode is RUN:
                    if servo_mode is INIT:
                        if all_servos[-1][2] == 0:  # wait for init to complete
                            servo_mode = RUN
                    else:
                        clst1 = []
                        clst2 = []
                        cmd_count = 0
                        for i, each_servo in enumerate(all_servos):
                            if each_servo[3] < 3:
                                cmd_count += 1
                                if accel_dif:
                                    accel = accel_list[i]
                                else:
                                    accel = 1
                                if next_dir[i] is F:
                                    clst1.append('Q %i %i 2300 %i'%
                                                 (i+1, SERVO_MAX, accel))
                                    next_dir[i] = R
                                else:
                                    clst1.append('Q %i %i 2300 %i'%
                                                 (i+1, SERVO_MIN, accel))
                                    next_dir[i] = F
                                if cmd_count == 8:
                                    clst2 = clst1
                                    clst1 = []
                        cmd1 = ' '.join(clst1)
                        cmd2 = ' '.join(clst2)
            # Update servos with any commands, get new analog and servo status
            if cmd2 != '':
                rcs.robust_write(cmd2)
            if cmd1 != '':
                rcs.robust_write(cmd1)
            analog_channels, all_servos = rcs.robust_read('MS', 2)
            disabled = ( all_servos[-1][-1] == -1 )     # read disable state
            if all_servos[0][0] == 0:                   # detects a past disable
                servo_mode = IDLE
            time.sleep(0.020)
    except Exception, e:
        WConio.gotoxy(0,1)
        WConio.textattr(0xc0)
        print "Unexpected exception somewhere: ", type(e)
        print e
        raw_input("Press enter to exit ->")
        exit()
