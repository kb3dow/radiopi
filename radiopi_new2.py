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
# 2016 May: Some ideas for flask from :
#     http://www.instructables.com/id/Raspberry-Pi-Internet-Radio-With-Flask/?ALLSTEPS
# 2020 Mar: All flash changes abandoned for now
# 2020 Mar: Rework to allow playlists. Assume playlists are formed externally

# dependancies
from Adafruit.Adafruit_I2C import Adafruit_I2C
from Adafruit.Adafruit_MCP230xx import Adafruit_MCP230XX
from Adafruit.Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
import datetime
import subprocess
import time
import queue
import threading
import configparser
# from string                import split
from xml.dom.minidom import *
# from ListSelector          import ListSelector
import utils.cmd

import subprocess
import smbus
import time

from mpd import MPDClient

# initialize the LCD plate
#   use busnum = 0 for raspi version 1 (256MB)
#   and busnum = 1 for raspi version 2 (512MB)
LCD = Adafruit_CharLCDPlate(busnum=1)

# Define a queue to communicate with worker thread
LCD_QUEUE = queue.Queue()
cfgParser = configparser.ConfigParser()

# Globals
INI_FILE = 'radiopi.ini'
playlist_track_names = []
cur_playlist = ''
cur_track = 1
total_tracks = 0
min_vol = 0
max_vol = 100
def_vol = 50
cur_vol = min_vol  # Current volume
new_vol = def_vol  # 'Next' volume after interactions
spd_vol = 1.0      # Speed of volume change (accelerates w/hold)
set_vol = False    # True if currently setting volume
paused = False    # True if music is paused
def_color = LCD.VIOLET
cur_color = def_color
bar_width = 7.0          # Vol Bar width on display
rng_vol = max_vol - min_vol + 1
vol_solbar = rng_vol / bar_width
vol_line = vol_solbar / 5.0  # There are 5 vert lines per char display

menufile = 'radiopi.xml'
# set DEBUG=1 for print debug statements
DEBUG = 1
DISPLAY_ROWS = 2
DISPLAY_COLS = 16

# set location
locchosen = ['Laurel, MD', '39.1333', '-76.8435', 92]

# Buttons
NONE = 0x00
SELECT = 0x01
RIGHT = 0x02
DOWN = 0x04
UP = 0x08
LEFT = 0x10
UP_AND_DOWN = 0x0C
LEFT_AND_RIGHT = 0x12

# Message Types
MSG_LCD = 1
MSG_SAVE = 2

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
# WORKER THREADS
# ----------------------------

def get_mpd_info(lcd_q, client):
    try:
        cso = client.currentsong()
        cst = client.status()
        print('State: %s, Vol: %s, Title: %s' % (cst['state'],
                                                 cst['volume'],
                                                 cso['title']))
        if cst['state'] == 'play':
            state_bitmap = chr(8)
        elif cst['state'] == 'pause':
            state_bitmap = chr(7)
        # elif cst['state'] == 'stop':
        else:
            state_bitmap = chr(5)

        line1 = cso['title'][:16].ljust(16, ' ')
        line2 = '%s Vol: %s' % (state_bitmap,
                                cst['volume'])
        line2 = line2.ljust(16, ' ')
        lcd_q.put((MSG_LCD, line1 + '\n' + line2),
                  True)
    except Exception as e:
        print('Exception: {}'.format(e))
        raise e


def mpd_poller(lcd_q):
    client = MPDClient()       # create client object
    client.timeout = 10        # network timeout (S) default: None
    # timeout for fetching the result of the idle command is handled
    # seperately, default: None
    client.idletimeout = None
    while True:
        client.connect("localhost", 6600)  # connect to localhost:6600
        print(client.mpd_version)          # print the MPD version
        print(client.status())
        while True:
            try:
                changes = client.idle()
                for change in changes:
                    if change == 'player' or change == 'mixer':
                        get_mpd_info(lcd_q, client)

            except Exception as e:
                print('Exception: {}'.format(e))
                break
        client.close()                     # send the close command
        client.disconnect()                # disconnect from the server
    client.close()                     # send the close command
    client.disconnect()                # disconnect from the server


def lcd_worker(q):
    '''
    Define a function to run in the worker thread
    '''
    while True:
        msgType, msg = q.get()
        # if we're falling behind, skip some LCD updates
        while not q.empty():
            q.task_done()
            msgType, msg = q.get()

        if msgType == MSG_LCD:
            LCD.setCursor(0, 0)
            LCD.message(msg)
        elif msgType == MSG_SAVE:
            saveSettings()

        q.task_done()
    return


def settingsLoad(mpdc, cfgp, cfgfile):
    global cur_track, cur_vol, cfgParser
    global cur_color
    # Read INI file
    if DEBUG:
        print('loading saved settings')
    try:
        cfgp.read(cfgfile)
        cur_vol = cfgParser.getint('settings_section', 'volume')
        cur_track = cfgParser.getint('settings_section', 'track')
        cur_color = cfgParser.getint('settings_section', 'lcdcolor')
        cur_playlist = cfgParser.get('settings_section', 'playlist')
        mpdc['host'] = cfgParser.get('mpdclient_section', 'host')
        mpdc['timeout'] = cfgParser.getint('mpdclient_section', 'timeout')
        mpdc['port'] = cfgParser.getint('mpdclient_section', 'port')
    except Exception as e:
        print('Exception: {}'.format(e))
        quit()


def mpdc_init(mpdc):
    client = MPDClient()
    client.timeout = mpdc['timeout']
    client.connect(mpdc['host'], mpdc['port'])
    mpdc['client'] = client


def lcdInit():
    # Setup AdaFruit LCD Plate
    global cur_color
    LCD.begin(DISPLAY_COLS, DISPLAY_ROWS)
    LCD.clear()
    LCD.backlight(cur_color)

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
    # By default, char 8 is loaded in 'play' state
    LCD.createChar(8, charSevenBitmaps[0])


def radioInit():
    global cur_track, cur_vol,\
        total_tracks, playlist_track_names, cfgParser, INI_FILE

    # Stop music player
    # output = run_cmd("mpc stop") # NOTE: no need to stop what was playing

    # Create the worker thread and make it a daemon
    lcd_thread = threading.Thread(target=lcd_worker, args=(LCD_QUEUE,))
    lcd_thread.setDaemon(True)
    lcd_thread.start()

    # Create the 2nd worker thread and make it a daemon
    mpd_thread = threading.Thread(target=mpd_poller, args=(LCD_QUEUE,))
    mpd_thread.setDaemon(True)
    mpd_thread.start()

    # Display startup banner
    LCD_QUEUE.put((MSG_LCD, 'Welcome to\nRadio Pi'), True)

    time.sleep(2)
    LCD.clear()
    if(cur_track > total_tracks):
        cur_track = 1

    # Start music player
    if DEBUG:
        print('starting player with track {}'.format(cur_track))
    if cur_track:
        LCD_QUEUE.put((MSG_LCD, playlist_track_names[cur_track - 1]), True)
    mpc_play_track(cur_track)
    run_cmd("mpc volume " + str(cur_vol))
    run_cmd("mpc volume +2")
    run_cmd("mpc volume -2")

    return


def play_next(mpdc):
    global cur_track, total_tracks
    cur_track += 1
    if(cur_track > total_tracks):
        cur_track = 1
    if DEBUG:
        print('playing Station ' + repr(cur_track))
    mpdc['client'].next()
    return True


def play_prev(mpdc):
    global cur_track, total_tracks
    cur_track -= 1
    if(cur_track < 1):
        cur_track = total_tracks
    if DEBUG:
        print('playing Station ' + repr(cur_track))
    mpdc['client'].previous()
    return True


def volUp(amt):
    global cur_vol
    if(cur_vol <= (100-amt)):
        output = run_cmd("mpc volume +"+str(amt))
        cur_vol += amt
        if DEBUG:
            print('Setting Volume ' + repr(cur_vol))
        return True
    return False


def volDown(amt):
    global cur_vol
    if(cur_vol >= amt):
        output = run_cmd("mpc volume -"+str(amt))
        cur_vol -= amt
        if DEBUG:
            print('Setting Volume ' + repr(cur_vol))
        return True
    return False


# Inside a playlist manage the buttons to play nex prev track
def playListPlay(mpdc):
    global spd_vol, set_vol, cur_vol, cur_track, total_tracks
    global playlist_track_names, cfgParser, INI_FILE

    LCD_QUEUE.put((MSG_LCD, playlist_track_names[cur_track - 1]), True)
    countdown_to_play = 0
    showTime = False
    timeSinceLastDisplayChange = 0

    if DEBUG:
        print('inside playListPlay - flushing')
    flush_buttons()
    # Main loop
    while True:
        press = read_buttons()

        # SELECT button pressed
        if(press == SELECT):
            return  # Return back to main menu

        # LEFT button pressed
        if(press == LEFT):
            play_prev(mpdc)
            LCD_QUEUE.put((MSG_LCD, playlist_track_names[cur_track - 1]),
                          block=True)
            showTime = False
            timeSinceLastDisplayChange = 0

        # RIGHT button pressed
        if(press == RIGHT):
            play_next(mpdc)
            LCD_QUEUE.put((MSG_LCD, playlist_track_names[cur_track - 1]),
                          block=True)
            showTime = False
            timeSinceLastDisplayChange = 0

        # UP button pressed
        if(press == UP):
            set_vol = volUp(2)

        # DOWN button pressed
        if(press == DOWN):
            set_vol = volDown(2)

        # UP/DOWN volume change show bar on LCD
        if set_vol is True:
            timeSinceLastDisplayChange = 0
            # Display the volume as a bar
            nSolid = int((cur_vol - min_vol) / vol_solbar)
            fracV = (cur_vol - min_vol) % vol_solbar
            nVertLines = int(round(fracV / vol_line))
            s = (chr(6) + ' Volume ' +  # ^ Volume string
                 chr(5) * nSolid +  # Solid brick(s)
                 chr(nVertLines) +  # Fractional brick
                 chr(0) * (6 - nSolid))  # Spaces
            if DEBUG:
                # print('vol_solbar = ' + str (vol_solbar) + '\n')
                # print('vol_line = ' + str (vol_line) + '\n')
                print('cur_vol = ' + str(cur_vol))
                print('nSolid = ' + str(nSolid))
                print('nVertLines = ' + str(nVertLines))
            LCD_QUEUE.put((MSG_LCD,
                           playlist_track_names[cur_track - 1].split()[0] +
                          "\n" + s), block=True)
            spd_vol = 1.0
            set_vol = False
        # Volume-setting mode now active (or was already there);
        # act on button press.
        if press == UP:
            new_vol = cur_vol + spd_vol
            if new_vol > max_vol:
                new_vol = max_vol
        else:
            new_vol = cur_vol - spd_vol
            if new_vol < min_vol:
                new_vol = min_vol
        # volTime   = time.time() # Time of last volume button press
        # spd_vol *= 1.15        # Accelerate volume change
        #     elif set_vol:
        #         spd_vol = 1.0 # Buttons released = reset volume speed
        #         # If no interaction in 4 seconds, return to prior state.
        #         # Volume bar will be erased by subsequent operations.
        #         if (time.time() - volTime) >= 4:
        #             set_vol = False
        #             if paused: drawPaused()

        delay_milliseconds(99)
        timeSinceLastDisplayChange += 99
        if (showTime):
            if (timeSinceLastDisplayChange > 900):
                timeSinceLastDisplayChange = 0
                now = datetime.datetime.now()
                LCD_QUEUE.put((MSG_LCD,
                               playlist_track_names[cur_track - 1].
                               split()[0] + "\n" +
                              now.strftime('%b %d  %H:%M:%S')), block=True)
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
    time.sleep(seconds)


# ----------------------------
# LOAD PLAYLIST OF STATIONS
# ----------------------------

def saveSettings():
    global cur_track, cur_vol, total_tracks, \
        playlist_track_names, cfgParser, INI_FILE
    cfgParser.set('settings_section', 'volume', str(cur_vol))
    cfgParser.set('settings_section', 'station', str(cur_track))
    cfgParser.set('settings_section', 'lcdcolor', str(cur_color))
    # Write our configuration file
    with open(INI_FILE, 'wb') as configfile:
        cfgParser.write(configfile)


def saveSettingsWrapper():
    LCD_QUEUE.put((MSG_LCD, "Saving          \nSettings ...    "), block=True)
    saveSettings()
    time.sleep(1)
    LCD_QUEUE.put((MSG_LCD, "Settings        \nSaved ...       "), block=True)
    time.sleep(2)


def playListLoad(mpdc):
    global cur_track, total_tracks, playlist_track_names, DEBUG

    playlist_track_names = []
    # mpdc['client'].iterate = True
    for song in mpdc['client'].playlistinfo():
        playlist_track_names.append(song['title'])
    total_tracks = len(playlist_track_names)

    status = mpdc['client'].status()
    cur_track = int(status['song']) + 1

    if DEBUG:
        print(playlist_track_names)
        print(mpdc['client'].status())

    '''
    # OLD WAY
    playlist_track_names = []
    o, e = utils.cmd.cmd_oe('mpc playlist')
    playlist_track_names = o.copy()
    total_tracks = len(playlist_track_names)
    o, e = utils.cmd.cmd_oe('mpc current')
    try:
        cur_track = o[1].split(' ')[1][1:].split('/')[0]
    except IndexError:
        cur_track = 1
    '''


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
    global cur_vol, cur_color

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
            LCD_QUEUE.put((MSG_LCD,
                           datetime.datetime.now().strftime(
                               '%b %d  %H:%M:%S\n') +
                           ipaddr), block=True)

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
            if(cur_vol < 99):
                cur_vol += 2

        # DOWN button pressed
        if(press == DOWN):
            output = run_cmd("mpc volume -2")
            if(cur_vol > 1):
                cur_vol -= 2

        # SELECT button = exit
        if(press == SELECT):
            keep_looping = False

        # LEFT or RIGHT toggles mute
        elif(press == LEFT or press == RIGHT):
            if muting:
                # amixer command not working, can't use next line
                # output = run_cmd("amixer -q cset numid=2 1")
                mpc_play_track(cur_track)
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

    LCD.backlight(cur_color)


def run_cmd(cmd):
    p = subprocess.Popen(cmd,
                         shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    output = p.communicate()[0]
    return output


def mpc_play():
    utils.cmd.cmd_oe('mpc play')


def mpc_play_track(cur_track):
    utils.cmd.cmd_oe('/usr/bin/mpc play {}'.format(cur_track))


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
        time.sleep(0.25)


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
            subprocess.run(["sudo", "shutdown", "-h", "now"])
            quit()
        time.sleep(0.25)


def LcdOff():
    LCD.backlight(LCD.OFF)


def LcdOn():
    LCD.backlight(LCD.ON)


def LcdRed():
    global cur_color
    cur_color = LCD.RED
    LCD.backlight(cur_color)


def LcdGreen():
    global cur_color
    cur_color = LCD.GREEN
    LCD.backlight(cur_color)


def LcdBlue():
    global cur_color
    cur_color = LCD.BLUE
    LCD.backlight(cur_color)


def LcdYellow():
    global cur_color
    cur_color = LCD.YELLOW
    LCD.backlight(cur_color)


def LcdTeal():
    global cur_color
    cur_color = LCD.TEAL
    LCD.backlight(cur_color)


def LcdViolet():
    global cur_color
    cur_color = LCD.VIOLET
    LCD.backlight(cur_color)


def ShowDateTime():
    if DEBUG:
        print('in ShowDateTime')
    LCD.clear()
    while not(LCD.buttons()):
        time.sleep(0.25)
        LCD_QUEUE.put((MSG_LCD,
                       time.strftime('%a %b %d %Y\n%I:%M:%S %p',
                                     time.localtime())))


'''
# NOTE: NOT-USED YET
def SetDateTime():
    if DEBUG:
        print('in SetDateTime')


# NOTE: NOT-USED YET
def ShowIPAddress():
    if DEBUG:
        print('in ShowIPAddress')
    LCD.clear()
    LCD.message(run_cmd("/sbin/ifconfig").
                split("\n")[1].split()[1][5:])
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        time.sleep(0.25)
'''


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
            time.sleep(1.5)
            break
        time.sleep(0.25)


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
            time.sleep(1.5)
            break
        time.sleep(0.25)


def waitForButton():
        # Poll all buttons once,
        # avoids repeated I2C traffic for different cases
        while 1:
            b = LCD.buttons()
            btnUp = b & (1 << LCD.UP)
            btnDown = b & (1 << LCD.DOWN)
            btnLeft = b & (1 << LCD.LEFT)
            btnRight = b & (1 << LCD.RIGHT)
            btnSel = b & (1 << LCD.SELECT)

            if (btnUp or btnDown or btnLeft or btnRight or btnSel):
                    break
            time.sleep(0.1)


class CommandToRun:
    def __init__(self, myName, theCommand):
        self.text = myName
        self.commandToRun = theCommand

    def Run(self):
        self.clist = split(run_cmd(self.commandToRun), '\n')
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
                        time.sleep(0.25)

                btnPressed = 0
                b = LCD.buttons()
                btnUp = b & (1 << LCD.UP)
                btnDown = b & (1 << LCD.DOWN)
                btnLeft = b & (1 << LCD.LEFT)
                btnRight = b & (1 << LCD.RIGHT)
                btnSel = b & (1 << LCD.SELECT)

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
    global cur_color
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

    LCD.backlight(cur_color)


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
        LCD_QUEUE.put((MSG_LCD, str), block=True)

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
    global cur_track, cur_vol, total_tracks, \
        playlist_track_names, cfgParser, INI_FILE
    mpdc = {}

    if DEBUG:
        print('entering main()')

    settingsLoad(mpdc, cfgParser, INI_FILE)
    mpdc_init(mpdc)
    lcdInit()
    playListLoad(mpdc)
    radioInit()

    while True:
        time.sleep(2.5)

    playListPlay(mpdc)

    uiItems = Folder('root', '')

    # parse an XML file by name
    dom = parse(menufile)

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

    time.sleep(0.15)

    lcd_thread.join()
    mpd_thread.join()


if __name__ == '__main__':
    main()

# vim: set expandtab shiftwidth=4 softtabstop=4 textwidth=79 ai:
