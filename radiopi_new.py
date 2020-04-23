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
import utils.cmd

import socket
import subprocess
import smbus
import time

from mpd import (MPDClient, MPDError, ConnectionError)

# initialize the LCD plate
#   use busnum = 0 for raspi version 1 (256MB)
#   and busnum = 1 for raspi version 2 (512MB)
LCD = Adafruit_CharLCDPlate(busnum=1)

# Define a queue to communicate with worker thread
LCD_QUEUE = queue.Queue()
cfgParser = configparser.ConfigParser()

LCD_PLAYER_MODE = 0
LCD_MENU_MODE = 1

# Globals
INI_FILE = 'radiopi.ini'
#playlist_track_names = []
mpd_playlists = []
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
display_mode_state = LCD_PLAYER_MODE
mpdc = {}

menufile = 'radiopi.xml'
# set DEBUG=True/falst to enable/disable print debug statements
DEBUG = True
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
LONG_PRESS = 0x80
LONG_PRESS_TIME = 0.2  # in sec

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

# Show what is playing on the lcd screen
def get_mpd_info(lcd_q, client):
    global DEBUG

    try:
        cso = client.currentsong()
        cst = client.status()
        if DEBUG:
            print(cso)
            print(cst)

        # show the symbol if it is in play/stop/pause
        if 'state' in cst and cst['state'] == 'play':
            state_bitmap = chr(8)  # play symbol
        elif 'state' in cst and cst['state'] == 'pause':
            state_bitmap = chr(7)  # pause symbol
        # elif cst['state'] == 'stop':
        else:
            state_bitmap = chr(5)  # stop symbol

        if 'title' in cso:
            line1_info = cso['title']
        elif 'name' in cso:
            line1_info = cso['name']
        else:
            line1_info = ''

        line1 = line1_info[:16].ljust(16, ' ')
        line2 = '%s Vol: %s' % (state_bitmap,
                                cst['volume'])
        line2 = line2.ljust(16, ' ')
        lcd_q.put((MSG_LCD, line1 + '\n' + line2),
                  True)
    except Exception as e:
        print('Exception: {}'.format(e))
        raise e


# Keep track of what is playing by polling and displaying
def mpd_poller(lcd_q):
    global DEBUG
    client = MPDClient()       # create client object
    client.timeout = 10        # network timeout (S) default: None
    # timeout for fetching the result of the idle command is handled
    # seperately, default: None
    client.idletimeout = 60 # keep refreshing every minute even if no change
    while True:
        client.connect("localhost", 6600)  # connect to localhost:6600
        if DEBUG:
            print(client.status())
        while True:
            try:
                changes = client.idle()
                # Update the display only if LCD in player mode
                # otherwise though music is being played, a menu might
                # be displayed that we do not want to overwrite
                if display_mode_state == LCD_PLAYER_MODE:
                    # if 'player' in change or 'mixer' in change:
                        # get_mpd_info(lcd_q, client)
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
        total_tracks, cfgParser, INI_FILE

    # Stop music player
    # output = run_cmd("mpc stop") # NOTE: no need to stop what was playing

    # Create the lcd update worker thread and make it a daemon
    lcd_thread = threading.Thread(target=lcd_worker, args=(LCD_QUEUE,))
    lcd_thread.setDaemon(True)
    lcd_thread.start()

    # Create the 2nd worker thread polling mpd and make it a daemon
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

    run_cmd("mpc volume " + str(cur_vol))
    run_cmd("mpc volume +2")
    run_cmd("mpc volume -2")

    return


def mpc_next(client):
    global cur_track, total_tracks
    cur_track += 1
    if(cur_track > total_tracks):
        cur_track = 1
    if DEBUG:
        print('Track %d'%(cur_track))
    client.next()
    return True


def mpc_prev(client):
    global cur_track, total_tracks
    cur_track -= 1
    if(cur_track < 1):
        cur_track = total_tracks
    client.previous()
    if DEBUG:
        print('Track %d'%(cur_track))
    return True


def mpc_vol_up(client, amt=5):
    global cur_vol
    if(cur_vol <= (100-amt)):
        cur_vol += amt
        client.setvol(cur_vol)
        if DEBUG:
            print('Setting Volume %d'%(cur_vol))
        return True
    return False


def mpc_vol_down(client, amt=5):
    global cur_vol
    if(cur_vol >= amt):
        cur_vol -= amt
        client.setvol(cur_vol)
        if DEBUG:
            print('Setting Volume %d'%(cur_vol))
        return True
    return False


def mpc_toggle_pause(client):
    status = client.status()
    state = status['state']
    # if state is pause/stop then play. If play then pause
    pause = 1 if state == 'play' else 0
    client.pause(pause)
    if DEBUG:
        print('Toggling play/pause')
    return True


# Inside a playlist manage the buttons to play nex prev track
def playerMode(**kwargs):
    global mpdc, display_mode_state

    if DEBUG:
        print('inside playerMode - flushing')

    button_table = { SELECT: mpc_toggle_pause, LEFT: mpc_prev, RIGHT: mpc_next,
        UP: mpc_vol_up, DOWN: mpc_vol_down}
    display_mode_state_old = display_mode_state
    display_mode_state = LCD_PLAYER_MODE

    flush_buttons()

    client = mpdc['client']

    while True:
        press = read_buttons()

        if not press:
            time.sleep(0.1)
            continue

        # SELECT button long pressed
        if(press == (LONG_PRESS | SELECT)):
            break  # Return back to main menu

        # extre steps to handle the situation where the client
        # connection seems to timeout while waiting
        try:
            client.status()
        except ConnectionError:
            # client.close()  # doing a close under error condition causes
            # error again
            client.connect("localhost", 6600)  # connect to localhost:6600
            continue
        except Exception as e:
            print('Exception: {}'.format(e))
            continue

        press &= 0x7F  # mask out the long press bit
        try: 
            # Call the function handling the type of button press
            if press in button_table:
                button_table[press](client)

        except Exception as e:
            print('Exception: {}'.format(e))
            continue

    display_mode_state = display_mode_state_old
    return

def flush_buttons():
    while(LCD.buttons() != 0):
        delay_milliseconds(1)


def read_buttons():
    buttons = LCD.buttons()

    if not buttons:
        return 0

    # Debounce push buttons
    time_1 = time.time()
    time_2 = time_1
    if(buttons != 0):
        while(LCD.buttons() != 0):
            time_2 = time.time()
            delay_milliseconds(1)

    if (time_2 - time_1) > 0.2:
        buttons |= LONG_PRESS

    if buttons and DEBUG:
        print(f"Key press: {buttons:#0{4}x}")

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
        cfgParser, INI_FILE
    cfgParser.set('settings_section', 'volume', str(cur_vol))
    cfgParser.set('settings_section', 'station', str(cur_track))
    cfgParser.set('settings_section', 'lcdcolor', str(cur_color))
    # Write our configuration file
    with open(INI_FILE, 'wb') as configfile:
        cfgParser.write(configfile)


def saveSettingsWrapper(**kwargs):
    LCD_QUEUE.put((MSG_LCD, "Saving          \nSettings ...    "), block=True)
    saveSettings()
    time.sleep(1)
    LCD_QUEUE.put((MSG_LCD, "Settings        \nSaved ...       "), block=True)
    time.sleep(2)


# Get the names of all playlists known to mpd
def get_mpd_playlists(mpdc):
    global mpd_playlists

    for t in mpdc['client'].listplaylists():
        if DEBUG:
            print('available playlists')
            print(t)
        mpd_playlists.append(t)

    return


# ----------------------------
# RADIO SETUP MENU
# ----------------------------

def audioHdmi(**kwargs):
    # audio output to headphone jack
    output = run_cmd("amixer -q cset numid=3 1")


def audioHphone(**kwargs):
    # audio output to HDMI port
    run_cmd("amixer -q cset numid=3 2")


def audioAuto(**kwargs):
    # audio output auto-select
    run_cmd("amixer -q cset numid=3 0")


def display_ipaddr(**kwargs):
    global cur_color

    # connect to google dns server and find the address
    # this shows the address of the link with the default route
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_addr = s.getsockname()[0].ljust(16, ' ')
    s.close()

    LCD.backlight(LCD.VIOLET)
    i = 29
    muting = False
    keep_looping = True
    while (keep_looping):
        # Every 1/2 second, update the time display
        i += 1
        if(i % 5 == 0):
            LCD_QUEUE.put((MSG_LCD,
                           datetime.datetime.now().strftime(
                               '%b %d  %H:%M:%S\n') +
                           str(ip_addr)), block=True)

        # Every 100 milliseconds, read the switches
        press = read_buttons()
        # Take action on switch press

        # SELECT button = exit
        if(press):
            keep_looping = False

        delay_milliseconds(99)

    LCD.backlight(cur_color)


def run_cmd(cmd):
    p = subprocess.Popen(cmd,
                         shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    output = p.communicate()[0]
    return output


# commands
def DoQuit(**kwargs):
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


def DoShutdown(**kwargs):
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


def LcdOff(**kwargs):
    LCD.backlight(LCD.OFF)


def LcdOn(**kwargs):
    LCD.backlight(LCD.ON)


# Set the LCD color, kwargs has a key called 'text'
# that is displayed on the lcd menu and used to set the color
# on the physical lcd
def SetLcdColor(**kwargs):
    global cur_color
    text_to_color = {'Red': LCD.RED, 'Green': LCD.GREEN, 'Blue': LCD.BLUE,
        'Yellow': LCD.YELLOW, 'Teal': LCD.TEAL, 'Violet': LCD.VIOLET, }

    if 'text' in kwargs and kwargs['text'] in text_to_color:
        if DEBUG:
            print('setting LCD to {}'.format(kwargs['text']))
        cur_color = text_to_color[kwargs['text']]
        LCD.backlight(cur_color)

def ShowDateTime(**kwargs):
    LCD.clear()
    while not(LCD.buttons()):
        time.sleep(0.25)
        LCD_QUEUE.put((MSG_LCD,
                       time.strftime('%a %b %d %Y\n%I:%M:%S %p',
                                     time.localtime())))


class Widget:
    def __init__(self, myName, myFunction, kwargs):
        self.text = myName
        self.function = myFunction
        self.kwargs = kwargs


class Folder:
    def __init__(self, myName, myParent):
        self.text = myName
        self.items = []
        self.parent = myParent


def loaded_playlist():
    ''' return the name of the playlist currently being played '''
    global mpdc, DEBUG

    client = mpdc['client']
    in_playlist = ''

    stored_playlists = []
    for i in client.listplaylists():
        name = i['playlist']
        stored_playlists.append(name)

    current_playlist = []
    for s in client.playlistinfo():
        song = s['file']
        current_playlist.append(song)

    for plist in stored_playlists:
        tmp_playlist= []
        for s in client.listplaylist(plist):
            tmp_playlist.append(s)

        if tmp_playlist == current_playlist:
            if DEBUG:
                print("Currently in playlist: {}".format(plist))
            in_playlist = plist
            break
    return in_playlist


def mpc_load_playlist(**kwargs):
    '''
    load a named playlist, if already in that playlist, do nothing
    The name of the playlist comes from the menu selection that is there in
    kwargs['text']
    '''
    global DEBUG, mpdc

    if DEBUG:
        print('In mpc_load_playlist() label: %s' % (kwargs['text']))

    client = mpdc['client']
    playlist_name = kwargs['text']

    if playlist_name != loaded_playlist():
        client.clear()
        client.load(playlist_name)
        client.play('0')

    playerMode(**{})
    return

# From the playlist names retreived earlier, form the menu for the LCE
def form_playlist_menu(folder):
    global DEBUG
    global mpd_playlists
    for plist in mpd_playlists:
        label = plist['playlist']
        if DEBUG:
            print('adding label %s to folder %s' % (label, folder.text))
        w = Widget(label,
            'mpc_load_playlist',
            {'text': label})
        folder.items.append(w)

def ProcessNode(currentNode, currentFolder):
    '''
    currentNode is a dom.documentElement - a folder node from xml
    currentFolder is of type Folder into which items from currentNode are to be
        added
    '''
    global DEBUG

    dynamic_folder_handlers = {'Playlists': form_playlist_menu}
    current_node_text = currentNode.getAttribute('text')

    if DEBUG:
        print('IN ProcessNode(%s, %s)' % (current_node_text,
            currentFolder.text))

    if currentFolder.text in dynamic_folder_handlers:
        if DEBUG:
            print('adding dynamic labels to folder %s' % (current_node_text))
        dynamic_folder_handlers[current_node_text](currentFolder)
        return

    children = currentNode.childNodes

    for child in children:
        if isinstance(child, xml.dom.minidom.Element):
            # form a dict of all the attributes so that they can be used
            # by the widget later when/if needed
            attributes_d = {}
            for a in child.attributes.values():
                attributes_d[a.name] = a.value

            child_text_attrib = child.getAttribute('text')

            if child.tagName == 'folder':
                thisFolder = Folder(child_text_attrib, currentFolder)
                currentFolder.items.append(thisFolder)
                ProcessNode(child, thisFolder)
            elif child.tagName == 'widget':
                thisWidget = Widget(child_text_attrib,
                                    child.getAttribute('function'),
                                    attributes_d)
                currentFolder.items.append(thisWidget)
            '''
            elif child.tagName == 'run':
                thisCommand = CommandToRun(child_text_attrib,
                                           child.firstChild.data)
                currentFolder.items.append(thisCommand)
            elif child.tagName == 'settings':
                HandleSettings(child)
            '''


class Display:
    def __init__(self, folder):
        self.curFolder = folder
        self.curTopItem = 0
        self.curSelectedItem = 0
        # Map keys hit to functions
        self.upd_table = {LEFT: self.left,
                          RIGHT: self.right,
                          UP: self.up,
                          DOWN: self.down,
                          SELECT: self.select
                          }

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

    def update(self, key):
        if key in self.upd_table:
            self.upd_table[key]()

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
                print('going to call %s()' %
                    (self.curFolder.items[self.curSelectedItem].function))
            eval(self.curFolder.items[self.curSelectedItem].function+\
                '(**self.curFolder.items[self.curSelectedItem].kwargs)')
        '''
        elif isinstance(self.curFolder.items[self.curSelectedItem], CommandToRun):
            self.curFolder.items[self.curSelectedItem].Run()
        '''

    def select(self):
        if isinstance(self.curFolder.items[self.curSelectedItem], Folder):
            self.curFolder = self.curFolder.items[self.curSelectedItem]
            self.curTopItem = 0
            self.curSelectedItem = 0
        elif isinstance(self.curFolder.items[self.curSelectedItem], Widget):
            if DEBUG:
                print('going to call %s()' %
                    (self.curFolder.items[self.curSelectedItem].function))
            eval(self.curFolder.items[self.curSelectedItem].function+\
                '(**self.curFolder.items[self.curSelectedItem].kwargs)')


# ----------------------------
# MAIN LOOP
# ----------------------------
# start things up
def main():
    global cur_track, total_tracks, \
        cfgParser, INI_FILE,\
        mpdc

    if DEBUG:
        print('entering main()')

    settingsLoad(mpdc, cfgParser, INI_FILE)
    mpdc_init(mpdc)
    lcdInit()
    radioInit()

    uiItems = Folder('root', '')

    # parse an XML file by name
    dom = parse(menufile)

    top = dom.documentElement

    get_mpd_playlists(mpdc)
    ProcessNode(top, uiItems)

    playerMode(**{})

    display = Display(uiItems)
    display.display()

    if DEBUG:
        print('entering while() in main()')

    while 1:
        # Poll all buttons once, avoids repeated I2C traffic
        pressed = read_buttons()
        pressed &= 0x7F  # we are not interested in LONG_PRESS

        if (pressed):
            display.update(pressed)
            display.display()
        time.sleep(0.15)


    lcd_thread.join()
    mpd_thread.join()


if __name__ == '__main__':
    main()

# vim: set expandtab shiftwidth=4 softtabstop=4 textwidth=79 ai:
