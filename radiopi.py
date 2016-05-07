#!/usr/bin/env python

# radio.py, version 2.1 (RGB LCD Pi Plate version)
# February 17, 2013
# Written by Sheldon Hartling for Usual Panic
# BSD license, all text above must be included in any redistribution
#

#
# based on code from Kyle Prier (http://wwww.youtube.com/meistervision)
# and AdaFruit Industries (https://www.adafruit.com)
# Kyle Prier - https://www.dropbox.com/s/w2y8xx7t6gkq8yz/radio.py
# AdaFruit - https://github.com/adafruit/Adafruit-Raspberry-Pi-Python-Code.git,
# Adafruit_CharLCDPlate
#
# Additions by Rajarajan Rajamani - to save settings to an .ini file
# 5/6/16 Some ideas for flask from :
#     http://www.instructables.com/id/Raspberry-Pi-Internet-Radio-With-Flask/?ALLSTEPS

# dependancies
from Adafruit_I2C          import Adafruit_I2C
from Adafruit_MCP230xx     import Adafruit_MCP230XX
from Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
from datetime              import datetime
from subprocess            import *
from time                  import sleep, strftime, localtime
from Queue                 import Queue
from threading             import Thread
from ConfigParser          import SafeConfigParser
from string                import split
from xml.dom.minidom       import *
# from ListSelector          import ListSelector

import commands
import smbus
import time

# initialize the LCD plate
#   use busnum = 0 for raspi version 1 (256MB)
#   and busnum = 1 for raspi version 2 (512MB)
LCD = Adafruit_CharLCDPlate(busnum=1)

# Define a queue to communicate with worker thread
LCD_QUEUE = Queue()
cfgParser = SafeConfigParser()

# Globals
INI_FILE       = 'radiopi.ini'
PLAYLIST_MSG   = []
STATION        = 1
NUM_STATIONS   = 0
VOL_MIN        = 0
VOL_MAX        = 100
VOL_DEFAULT    = 70
LCD_COLOR      = LCD.VIOLET
volCur         = VOL_MIN      # Current volume
volNew         = VOL_DEFAULT  # 'Next' volume after interactions
volSpeed       = 1.0          # Speed of volume change (accelerates w/hold)
volSet         = False        # True if currently setting volume
paused         = False        # True if music is paused
BARWIDTH       = 7.0          # Vol Bar width on display
VOLSPAN        = VOL_MAX - VOL_MIN + 1
vPerSolidBar   = VOLSPAN / BARWIDTH
vPerLine       = vPerSolidBar / 5.0  # There are 5 vert lines per char display

configfile = 'radiopi.xml'
# set DEBUG=1 for print debug statements
DEBUG = 0
DISPLAY_ROWS = 2
DISPLAY_COLS = 16

# set zip chosen
zipchosen = 20723
# set location
locchosen = ['Laurel, MD', '39.1333', '-76.8435', 92]

# Buttons
NONE           = 0x00
SELECT         = 0x01
RIGHT          = 0x02
DOWN           = 0x04
UP             = 0x08
LEFT           = 0x10
UP_AND_DOWN    = 0x0C
LEFT_AND_RIGHT = 0x12

# Char 7 gets reloaded for different modes.  These are the bitmaps:
charSevenBitmaps = [[0b10000,  # Play (also selected station)
                     0b11000,
                     0b11100,
                     0b11110,
                     0b11100,
                     0b11000,
                     0b10000,
                     0b00000],
                    [0b11011,  # Pause
                     0b11011,
                     0b11011,
                     0b11011,
                     0b11011,
                     0b11011,
                     0b11011,
                     0b00000],
                    [0b00000,  # Next Track
                     0b10100,
                     0b11010,
                     0b11101,
                     0b11010,
                     0b10100,
                     0b00000,
                     0b00000]]


# ----------------------------
# WORKER THREAD
# ----------------------------

# Define a function to run in the worker thread
def update_lcd(q):
    while True:
        msg = q.get()
        # if we're falling behind, skip some LCD updates
        while not q.empty():
            q.task_done()
            msg = q.get()
        LCD.setCursor(0, 0)
        LCD.message(msg)
        q.task_done()
    return


def settingsLoad():
    global STATION, volCur, NUM_STATIONS, PLAYLIST_MSG, cfgParser, INI_FILE
    global LCD_COLOR
    # Read INI file
    if DEBUG:
        print('loading saved settings')
    cfgParser.read(INI_FILE)
    volCur = cfgParser.getint('settings_section', 'volume')
    STATION = cfgParser.getint('settings_section', 'station')
    LCD_COLOR = cfgParser.getint('settings_section', 'lcdcolor')


def lcdInit():
    # Setup AdaFruit LCD Plate
    global LCD_COLOR
    LCD.begin(DISPLAY_COLS, DISPLAY_ROWS)
    LCD.clear()
    LCD.backlight(LCD_COLOR)

    # Create volume bargraph custom characters (chars 0-5):
    for i in range(6):
        bitmap = []
        bits = (255 << (5 - i)) & 0x1f
        for j in range(8):
            bitmap.append(bits)
        LCD.createChar(i, bitmap)

    # Create up/down icon (char 6)
    LCD.createChar(6, [0b00100,
                   0b01110,
                   0b11111,
                   0b00000,
                   0b00000,
                   0b11111,
                   0b01110,
                   0b00100])

    # By default, char 7 is loaded in 'pause' state
    LCD.createChar(7, charSevenBitmaps[1])


def radioInit():
    global STATION, volCur, NUM_STATIONS, PLAYLIST_MSG, cfgParser, INI_FILE

    # Stop music player
    output = run_cmd("mpc stop")

    # Create the worker thread and make it a daemon
    worker = Thread(target=update_lcd, args=(LCD_QUEUE,))
    worker.setDaemon(True)
    worker.start()

    # Display startup banner
    LCD_QUEUE.put('Welcome to\nRadio Pi', True)

    # Load our station playlist
    loadPlaylist()
    sleep(2)
    LCD.clear()
    if(STATION > NUM_STATIONS):
        STATION = 1

    # Start music player
    LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
    mpc_play(STATION)
    run_cmd("mpc volume " + str(volCur))
    run_cmd("mpc volume +2")
    run_cmd("mpc volume -2")

    return


def chanUp():
    global STATION, NUM_STATIONS
    STATION += 1
    if(STATION > NUM_STATIONS):
        STATION = 1
    if DEBUG:
        print('playing Station ' + repr(STATION))
    mpc_play(STATION)
    return True


def chanDown():
    global STATION, NUM_STATIONS
    STATION -= 1
    if(STATION < 1):
        STATION = NUM_STATIONS
    if DEBUG:
        print('playing Station ' + repr(STATION))
    mpc_play(STATION)
    return True


def volUp(amt):
    global volCur
    if(volCur <= (100-amt)):
        output = run_cmd("mpc volume +"+str(amt))
        volCur += amt
        if DEBUG:
            print('Setting Volume ' + repr(volCur))
        return True
    return False


def volDown(amt):
    global volCur
    if(volCur >= amt):
        output = run_cmd("mpc volume -"+str(amt))
        volCur -= amt
        if DEBUG:
            print('Setting Volume ' + repr(volCur))
        return True
    return False


def radioPlay():
    global volSpeed, volSet, volCur, STATION, NUM_STATIONS
    global PLAYLIST_MSG, cfgParser, INI_FILE

    LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
    countdown_to_play = 0
    showTime = False
    timeSinceLastDisplayChange = 0

    if DEBUG:
        print('inside radioPlay - flushing')
    flush_buttons()
    # Main loop
    while True:
        press = read_buttons()

        # SELECT button pressed
        if(press == SELECT):
            return  # Return back to main menu

        # LEFT button pressed
        if(press == LEFT):
            chanDown()
            LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
            showTime = False
            timeSinceLastDisplayChange = 0

        # RIGHT button pressed
        if(press == RIGHT):
            chanUp()
            LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
            showTime = False
            timeSinceLastDisplayChange = 0

        # UP button pressed
        if(press == UP):
            volSet = volUp(2)

        # DOWN button pressed
        if(press == DOWN):
            volSet = volDown(2)

        # UP/DOWN volume change show bar on LCD
        if volSet is True:
            timeSinceLastDisplayChange = 0
            # Display the volume as a bar
            nSolid = int((volCur - VOL_MIN) / vPerSolidBar)
            fracV = (volCur - VOL_MIN) % vPerSolidBar
            nVertLines = int(round(fracV / vPerLine))
            s = (chr(6) + ' Volume ' +  # ^ Volume string
                 chr(5) * nSolid +  # Solid brick(s)
                 chr(nVertLines) +  # Fractional brick
                 chr(0) * (6 - nSolid))  # Spaces
            if DEBUG:
                # print('vPerSolidBar = ' + str (vPerSolidBar) + '\n')
                # print('vPerLine = ' + str (vPerLine) + '\n')
                print('volCur = ' + str(volCur))
                print('nSolid = ' + str(nSolid))
                print('nVertLines = ' + str(nVertLines))
            LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1].split()[0] +
                          "\n" + s, True)
            volSpeed = 1.0
            volSet = False
        # Volume-setting mode now active (or was already there);
        # act on button press.
        if press == UP:
            volNew = volCur + volSpeed
            if volNew > VOL_MAX:
                volNew = VOL_MAX
        else:
            volNew = volCur - volSpeed
            if volNew < VOL_MIN:
                volNew = VOL_MIN
        # volTime   = time.time() # Time of last volume button press
        # volSpeed *= 1.15        # Accelerate volume change
        #     elif volSet:
        #         volSpeed = 1.0 # Buttons released = reset volume speed
        #         # If no interaction in 4 seconds, return to prior state.
        #         # Volume bar will be erased by subsequent operations.
        #         if (time.time() - volTime) >= 4:
        #             volSet = False
        #             if paused: drawPaused()

        delay_milliseconds(99)
        timeSinceLastDisplayChange += 99
        if (showTime):
            if (timeSinceLastDisplayChange > 900):
                timeSinceLastDisplayChange = 0
                now = datetime.now()
                LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1].split()[0] + "\n" +
                              now.strftime('%b %d  %H:%M:%S'), True)
        else:
            if (timeSinceLastDisplayChange > 5000):
                timeSinceLastDisplayChange = 0
                showTime = True


def flush_buttons():
    while(LCD.buttons() != 0):
        delay_milliseconds(1)


def read_buttons():
    buttons = LCD.buttons()
    # Debounce push buttons
    if(buttons != 0):
        while(LCD.buttons() != 0):
            delay_milliseconds(1)
    return buttons


def delay_milliseconds(milliseconds):
    # divide milliseconds by 1000 for seconds
    seconds = milliseconds / float(1000)
    sleep(seconds)


# ----------------------------
# LOAD PLAYLIST OF STATIONS
# ----------------------------

def saveSettings():
    global STATION, volCur, NUM_STATIONS, PLAYLIST_MSG, cfgParser, INI_FILE
    cfgParser.set('settings_section', 'volume', str(volCur))
    cfgParser.set('settings_section', 'station', str(STATION))
    cfgParser.set('settings_section', 'lcdcolor', str(LCD_COLOR))
    # Write our configuration file
    with open(INI_FILE, 'wb') as configfile:
        cfgParser.write(configfile)


def saveSettingsWrapper():
    LCD_QUEUE.put("Saving          \nSettings ...    ", True)
    saveSettings()
    sleep(1)
    LCD_QUEUE.put("Settings        \nSaved ...       ", True)
    sleep(2)


def loadPlaylist():
    global STATION, NUM_STATIONS, PLAYLIST_MSG

    # Run shell script to add all stations
    # to the MPC/MPD music player playlist
    output = run_cmd("mpc clear")
    output = run_cmd("/home/pi/radiopi/radio_playlist.sh")

    # Load PLAYLIST_MSG list
    PLAYLIST_MSG = []
    with open("/home/pi/radiopi/radio_playlist.sh", "r") as playlist:
        # Skip leading hash-bang line
        for line in playlist:
            if line[0:1] != '#!':
                break
        # Remaining comment lines are loaded
        for line in playlist:
            if line[0] == "#":
                PLAYLIST_MSG.append(line.replace(r'\n',
                                    '\n')[1:-1] + "                ")
    playlist.close()
    NUM_STATIONS = len(PLAYLIST_MSG)


# ----------------------------
# RADIO SETUP MENU
# ----------------------------

def audioHdmi():
    # audio output to headphone jack
    output = run_cmd("amixer -q cset numid=3 1")


def audioHphone():
    # audio output to HDMI port
    run_cmd("amixer -q cset numid=3 2")


def audioAuto():
    # audio output auto-select
    run_cmd("amixer -q cset numid=3 0")


def display_ipaddr():
    global volCur, LCD_COLOR

    show_wlan0 = "ip addr show wlan0 | cut -d/ -f1 | \
            awk '/inet/ {printf \"w%15.15s\", $2}'"
    show_eth0 = "ip addr show eth0  | cut -d/ -f1 | \
            awk '/inet/ {printf \"e%15.15s\", $2}'"
    ipaddr = run_cmd(show_eth0)
    if ipaddr == "":
        ipaddr = run_cmd(show_wlan0)

    LCD.backlight(LCD.VIOLET)
    i = 29
    muting = False
    keep_looping = True
    while (keep_looping):
        # Every 1/2 second, update the time display
        i += 1
        # if(i % 10 == 0):
        if(i % 5 == 0):
            LCD_QUEUE.put(datetime.now().strftime('%b %d  %H:%M:%S\n') +
                          ipaddr, True)

        # Every 3 seconds, update ethernet or wi-fi IP address
        if(i == 60):
            ipaddr = run_cmd(show_eth0)
            i = 0
        elif(i == 30):
            ipaddr = run_cmd(show_wlan0)

        # Every 100 milliseconds, read the switches
        press = read_buttons()
        # Take action on switch press

        # UP button pressed
        if(press == UP):
            output = run_cmd("mpc volume +2")
            if(volCur < 99):
                volCur += 2

        # DOWN button pressed
        if(press == DOWN):
            output = run_cmd("mpc volume -2")
            if(volCur > 1):
                volCur -= 2

        # SELECT button = exit
        if(press == SELECT):
            keep_looping = False

        # LEFT or RIGHT toggles mute
        elif(press == LEFT or press == RIGHT):
            if muting:
                # amixer command not working, can't use next line
                # output = run_cmd("amixer -q cset numid=2 1")
                mpc_play(STATION)
                # work around a problem.  Play always starts at full volume
                delay_milliseconds(400)
                output = run_cmd("mpc volume +2")
                output = run_cmd("mpc volume -2")
            else:
                # amixer command not working, can't use next line
                # output = run_cmd("amixer -q cset numid=2 0")
                output = run_cmd("mpc stop")
            muting = not muting

        delay_milliseconds(99)

    LCD.backlight(LCD_COLOR)


def run_cmd(cmd):
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
    output = p.communicate()[0]
    return output


def mpc_play(STATION):
    pid = Popen(["/usr/bin/mpc", "play", '%d' % (STATION)]).pid


# commands
def DoQuit():
    LCD.clear()
    LCD.message('Are you sure?\nPress Sel for Y')
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        if LCD.buttonPressed(LCD.SELECT):
            LCD.clear()
            LCD.backlight(LCD.OFF)
            quit()
        sleep(0.25)


def DoShutdown():
    LCD.clear()
    LCD.message('Are you sure?\nPress Sel for Y')
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        if LCD.buttonPressed(LCD.SELECT):
            LCD.clear()
            LCD.backlight(LCD.OFF)
            saveSettings()
            commands.getoutput("sudo shutdown -h now")
            quit()
        sleep(0.25)


def LcdOff():
    LCD.backlight(LCD.OFF)


def LcdOn():
    LCD.backlight(LCD.ON)


def LcdRed():
    global LCD_COLOR
    LCD_COLOR = LCD.RED
    LCD.backlight(LCD_COLOR)


def LcdGreen():
    global LCD_COLOR
    LCD_COLOR = LCD.GREEN
    LCD.backlight(LCD_COLOR)


def LcdBlue():
    global LCD_COLOR
    LCD_COLOR = LCD.BLUE
    LCD.backlight(LCD_COLOR)


def LcdYellow():
    global LCD_COLOR
    LCD_COLOR = LCD.YELLOW
    LCD.backlight(LCD_COLOR)


def LcdTeal():
    global LCD_COLOR
    LCD_COLOR = LCD.TEAL
    LCD.backlight(LCD_COLOR)


def LcdViolet():
    global LCD_COLOR
    LCD_COLOR = LCD.VIOLET
    LCD.backlight(LCD_COLOR)


def ShowDateTime():
    if DEBUG:
        print('in ShowDateTime')
    LCD.clear()
    while not(LCD.buttons()):
        sleep(0.25)
        # LCD.home()
        # LCD.message(strftime('%a %b %d %Y\n%I:%M:%S %p', localtime()))
        LCD_QUEUE.put(strftime('%a %b %d %Y\n%I:%M:%S %p', localtime()))


def SetDateTime():
    if DEBUG:
        print('in SetDateTime')


def ShowIPAddress():
    if DEBUG:
        print('in ShowIPAddress')
    LCD.clear()
    LCD.message(commands.getoutput("/sbin/ifconfig").
                split("\n")[1].split()[1][5:])
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        sleep(0.25)


# only use the following if you find useful
def Use10Network():
    "Allows you to switch to a different network for local connection"
    LCD.clear()
    LCD.message('Are you sure?\nPress Sel for Y')
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        if LCD.buttonPressed(LCD.SELECT):
            # uncomment the following once you have a separate network defined
            # commands.getoutput("sudo cp /etc/network/interfaces.hub.10"
            # "/etc/network/interfaces")
            LCD.clear()
            LCD.message('Please reboot')
            sleep(1.5)
            break
        sleep(0.25)


# only use the following if you find useful
def UseDHCP():
    "Allows you to switch to a network config that uses DHCP"
    LCD.clear()
    LCD.message('Are you sure?\nPress Sel for Y')
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        if LCD.buttonPressed(LCD.SELECT):
            # uncomment the following once you get an original copy in place
            # commands.getoutput("sudo"
            # "cp /etc/network/interfaces.orig /etc/network/interfaces")
            LCD.clear()
            LCD.message('Please reboot')
            sleep(1.5)
            break
        sleep(0.25)


def ShowLatLon():
    if DEBUG:
        print('in ShowLatLon')


def SetLatLon():
    if DEBUG:
        print('in SetLatLon')


def ShowLocation():
    global LCD
    global locchosen
    if DEBUG:
        print('in ShowLocation')
        print locchosen[0], locchosen[1], locchosen[2]
    LCD.clear()
    LCD.message(locchosen[0])
    sleep(0.1)
    waitForButton()


def SetLocation():
    if DEBUG:
        print('in SetLocation')
    global LCD
    global locchosen
    list = []
    # coordinates usable by ephem library, lat, lon, elevation (m)
    list.append(['Laurel, MD', '39.1333', '-76.8435', 92])
    list.append(['New York', '40.7143528', '-74.0059731', 9.775694])
    list.append(['Paris', '48.8566667', '2.3509871', 35.917042])
    selector = ListSelector(list, LCD)
    item = selector.Pick()
    # do something useful
    locchosen = list[item]


def waitForButton():
        # Poll all buttons once,
        # avoids repeated I2C traffic for different cases
        while 1:
                b        = LCD.buttons()
                btnUp    = b & (1 << LCD.UP)
                btnDown  = b & (1 <<LCD.DOWN)
                btnLeft  = b & (1 <<LCD.LEFT)
                btnRight = b & (1 <<LCD.RIGHT)
                btnSel   = b & (1 <<LCD.SELECT)

                if (btnUp or btnDown or btnLeft or btnRight or btnSel):
                        break
                sleep(0.1)


class CommandToRun:
    def __init__(self, myName, theCommand):
        self.text = myName
        self.commandToRun = theCommand

    def Run(self):
        self.clist = split(commands.getoutput(self.commandToRun), '\n')
        clistlen = len(self.clist)
        if clistlen > 0:
            LCD.clear()
            if clistlen > 1:
                LCD.message(self.clist[0]+'\n'+self.clist[1])
            else:
                LCD.message(self.clist[0])

            j = 0
            btnPressed = 1
            while 1:

                if btnPressed:
                        LCD.clear()
                        if j < (clistlen-1):
                                LCD.message(self.clist[j]+'\n'+self.clist[j+1])
                        else:
                                LCD.message(self.clist[j]+'\n')
                        sleep(0.25)

                btnPressed = 0
                b        = LCD.buttons()
                btnUp    = b & (1 << LCD.UP)
                btnDown  = b & (1 << LCD.DOWN)
                btnLeft  = b & (1 << LCD.LEFT)
                btnRight = b & (1 << LCD.RIGHT)
                btnSel   = b & (1 << LCD.SELECT)

                if btnDown:
                        btnPressed = 1
                        if j < (clistlen-1):
                                j = j+1
                elif btnUp:
                        btnPressed = 1
                        if j:
                                j = j-1
                elif btnLeft:
                        btnPressed = 1
                        break


class Widget:
    def __init__(self, myName, myFunction):
        self.text = myName
        self.function = myFunction


class Folder:
    def __init__(self, myName, myParent):
        self.text = myName
        self.items = []
        self.parent = myParent


def HandleSettings(node):
    global LCD
    if DEBUG:
        print('In HandleSettings')
    if node.getAttribute('lcdColor').lower() == 'red':
        LCD.backlight(LCD.RED)
    elif node.getAttribute('lcdColor').lower() == 'green':
        LCD.backlight(LCD.GREEN)
    elif node.getAttribute('lcdColor').lower() == 'blue':
        LCD.backlight(LCD.BLUE)
    elif node.getAttribute('lcdColor').lower() == 'yellow':
        LCD.backlight(LCD.YELLOW)
    elif node.getAttribute('lcdColor').lower() == 'teal':
        LCD.backlight(LCD.TEAL)
    elif node.getAttribute('lcdColor').lower() == 'violet':
        LCD.backlight(LCD.VIOLET)
    elif node.getAttribute('lcdColor').lower() == 'white':
        LCD.backlight(LCD.ON)
    if node.getAttribute('lcdBacklight').lower() == 'on':
        LCD.backlight(LCD.ON)
    elif node.getAttribute('lcdBacklight').lower() == 'off':
        LCD.backlight(LCD.OFF)


def ProcessNode(currentNode, currentItem):
    global LCD_COLOR
    children = currentNode.childNodes

    for child in children:
        if isinstance(child, xml.dom.minidom.Element):
            if child.tagName == 'settings':
                HandleSettings(child)
            elif child.tagName == 'folder':
                thisFolder = Folder(child.getAttribute('text'), currentItem)
                currentItem.items.append(thisFolder)
                ProcessNode(child, thisFolder)
            elif child.tagName == 'widget':
                thisWidget = Widget(child.getAttribute('text'),
                                    child.getAttribute('function'))
                currentItem.items.append(thisWidget)
            elif child.tagName == 'run':
                thisCommand = CommandToRun(child.getAttribute('text'),
                                           child.firstChild.data)
                currentItem.items.append(thisCommand)

    LCD.backlight(LCD_COLOR)


class Display:
    def __init__(self, folder):
        self.curFolder = folder
        self.curTopItem = 0
        self.curSelectedItem = 0

    def display(self):
        if self.curTopItem > len(self.curFolder.items) - DISPLAY_ROWS:
            self.curTopItem = len(self.curFolder.items) - DISPLAY_ROWS
        if self.curTopItem < 0:
            self.curTopItem = 0
        if DEBUG:
            print('------------------')
        str = ''
        for row in range(self.curTopItem, self.curTopItem+DISPLAY_ROWS):
            if row > self.curTopItem:
                str += '\n'
            if row < len(self.curFolder.items):
                if row == self.curSelectedItem:
                    cmd = '-'+self.curFolder.items[row].text
                    if len(cmd) < 16:
                        for row in range(len(cmd), 16):
                            cmd += ' '
                    if DEBUG:
                        print('|'+cmd+'|')
                    str += cmd
                else:
                    cmd = ' '+self.curFolder.items[row].text
                    if len(cmd) < 16:
                        for row in range(len(cmd), 16):
                            cmd += ' '
                    if DEBUG:
                        print('|'+cmd+'|')
                    str += cmd
        if DEBUG:
            print('------------------')
        LCD_QUEUE.put(str, True)

    def update(self, command):
        if DEBUG:
            print('do', command)
        if command == 'u':
            self.up()
        elif command == 'd':
            self.down()
        elif command == 'r':
            self.right()
        elif command == 'l':
            self.left()
        elif command == 's':
            self.select()

    def up(self):
        if self.curSelectedItem == 0:
            return
        elif self.curSelectedItem > self.curTopItem:
            self.curSelectedItem -= 1
        else:
            self.curTopItem -= 1
            self.curSelectedItem -= 1

    def down(self):
        if self.curSelectedItem+1 == len(self.curFolder.items):
            return
        elif self.curSelectedItem < self.curTopItem+DISPLAY_ROWS-1:
            self.curSelectedItem += 1
        else:
            self.curTopItem += 1
            self.curSelectedItem += 1

    def left(self):
        if isinstance(self.curFolder.parent, Folder):
            # find the current in the parent
            itemno = 0
            index = 0
            for item in self.curFolder.parent.items:
                if self.curFolder == item:
                    if DEBUG:
                        print('foundit')
                    index = itemno
                else:
                    itemno += 1
            if index < len(self.curFolder.parent.items):
                self.curFolder = self.curFolder.parent
                self.curTopItem = index
                self.curSelectedItem = index
            else:
                self.curFolder = self.curFolder.parent
                self.curTopItem = 0
                self.curSelectedItem = 0

    def right(self):
        if isinstance(self.curFolder.items[self.curSelectedItem], Folder):
            self.curFolder = self.curFolder.items[self.curSelectedItem]
            self.curTopItem = 0
            self.curSelectedItem = 0
        elif isinstance(self.curFolder.items[self.curSelectedItem], Widget):
            if DEBUG:
                print('eval',
                      self.curFolder.items[self.curSelectedItem].function)
            eval(self.curFolder.items[self.curSelectedItem].function+'()')
        elif isinstance(self.curFolder.items[self.curSelectedItem],
                        CommandToRun):
            self.curFolder.items[self.curSelectedItem].Run()

    def select(self):
        if DEBUG:
            print('check widget')
        if isinstance(self.curFolder.items[self.curSelectedItem], Folder):
            self.curFolder = self.curFolder.items[self.curSelectedItem]
            self.curTopItem = 0
            self.curSelectedItem = 0
        elif isinstance(self.curFolder.items[self.curSelectedItem], Widget):
            if DEBUG:
                print('eval',
                      self.curFolder.items[self.curSelectedItem].function)
            eval(self.curFolder.items[self.curSelectedItem].function+'()')


# ----------------------------
# MAIN LOOP
# ----------------------------
# start things up
def main():
    global STATION, volCur, NUM_STATIONS, PLAYLIST_MSG, cfgParser, INI_FILE

    if DEBUG:
        print('entering main()')

    settingsLoad()
    lcdInit()
    radioInit()
    radioPlay()

    uiItems = Folder('root', '')

    # parse an XML file by name
    dom = parse(configfile)

    top = dom.documentElement

    ProcessNode(top, uiItems)

    display = Display(uiItems)
    display.display()

    if DEBUG:
        print('entering while() in main()')

    while 1:
        # Poll all buttons once, avoids repeated I2C traffic
        pressed = read_buttons()

        if (pressed == LEFT):
            display.update('l')
            display.display()

        if (pressed == UP):
            display.update('u')
            display.display()

        if (pressed == DOWN):
            display.update('d')
            display.display()

        if (pressed == RIGHT):
            display.update('r')
            display.display()

        if (pressed == SELECT):
            display.update('s')
            display.display()

    sleep(0.15)

    update_lcd.join()

if __name__ == '__main__':
    main()
