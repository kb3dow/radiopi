#!/usr/bin/env python
'''
# radio.py, version 2.1 (RGB LCD Pi Plate version)
# February 17, 2013
# Written by Sheldon Hartling for Usual Panic
# BSD license, all text above must be included in any redistribution

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
'''

# dependancies
import datetime
import subprocess
import time
import queue
import threading
import xml.dom.minidom as minidom
# from xml.dom.minidom import *
import socket
import sys
from mpd import (MPDClient, MPDError)
# from mpd import (MPDClient, MPDError, ConnectionError)

# from Adafruit.Adafruit_I2C import Adafruit_I2C
# from Adafruit.Adafruit_MCP230xx import Adafruit_MCP230XX
from Adafruit.Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
# import utils.cmd
from AppConfig import AppConfig

# initialize the LCD plate
#   use busnum = 0 for raspi version 1 (256MB)
#   and busnum = 1 for raspi version 2 (512MB)
LCD = Adafruit_CharLCDPlate(busnum=1)

# Define a queue to communicate with worker thread
LCD_QUEUE = queue.Queue()

LCD_PLAYER_MODE = 0
LCD_MENU_MODE = 1

# Globals
total_tracks = 0
display_mode_state = LCD_MENU_MODE

mpd_client = MPDClient()

MENUFILE = 'radiopi.xml'
# set DEBUG=True/falst to enable/disable print debug statements
DEBUG = True
LCD_ROWS = 2
LCD_COLS = 16

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
                     0b00000],
                    [0b00100,
                     0b01110,
                     0b11111,
                     0b00000,
                     0b00000,
                     0b11111,
                     0b01110,
                     0b00100]]


def dbg_print(msg):
    ''' debug print message '''
    if DEBUG:
        print(msg)


# ----------------------------
# WORKER THREADS
# ----------------------------

def get_mpd_info(lcd_q, client):
    '''
    Show what is playing on the lcd screen
    '''
    try:
        cso = client.currentsong()
        cst = client.status()
        dbg_print(cso)
        dbg_print(cst)

        state = cst['state'] if 'state' in cst else None
        volume = int(cst['volume']) if 'volume' in cst else 0

        # show the symbol if it is in play/stop/pause
        if state == 'play':
            state_bitmap = chr(8)  # play symbol
        elif state == 'pause':
            state_bitmap = chr(7)  # pause symbol
        # elif state == 'stop':
        else:
            state_bitmap = chr(5)  # stop symbol

        if 'title' in cso:
            line1_info = cso['title']
        elif 'name' in cso:
            line1_info = cso['name']
        else:
            line1_info = ''

        line1 = line1_info[:16].ljust(16, ' ')
        line2 = '%s Vol: %d' % (state_bitmap,
                                volume)
        line2 = line2.ljust(16, ' ')
        lcd_q.put((MSG_LCD, line1 + '\n' + line2),
                  True)
        if volume != AppConfig.get('volume', 'rpi_player'):
            AppConfig.set(volume, 'volume', 'rpi_player')

    except Exception as e:
        print('Exception: {}'.format(e))
        raise e


def mpd_poller(lcd_q):
    '''
    Keep track of what is playing by polling and displaying
    '''
    client = MPDClient()       # create client object
    client.timeout = 10        # network timeout (S) default: None
    # timeout for fetching the result of the idle command is handled
    # seperately, default: None
    client.idletimeout = 60  # keep refreshing every minute even if no change
    while True:
        client.connect(AppConfig.get('host', 'mpdclient'),
                       AppConfig.get('port', 'mpdclient'))
        # connect to localhost:6600

        dbg_print(client.status())
        while True:
            try:
                client.idle()
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
        msg_type, msg = q.get()
        # if we're falling behind, skip some LCD updates
        while not q.empty():
            q.task_done()
            msg_type, msg = q.get()

        if msg_type == MSG_LCD:
            LCD.setCursor(0, 0)
            LCD.message(msg)
        elif msg_type == MSG_SAVE:
            settings_save()

        q.task_done()


def settings_load():
    ''' load settings from yaml file '''
    AppConfig.config_load()


def mpdc_init():
    ''' Setup music player daemon client '''
    mpd_client.timeout = AppConfig.get('timeout', 'mpdclient')
    mpd_client.connect(AppConfig.get('host', 'mpdclient'),
                       AppConfig.get('port', 'mpdclient'))


def lcd_init():
    ''' Setup AdaFruit LCD Plate '''
    LCD.begin(LCD_COLS, LCD_ROWS)
    LCD.clear()
    LCD.backlight(AppConfig.get('lcdcolor', 'rpi_player'))

    # Create volume bargraph custom characters (chars 0-5):
    for i in range(6):
        bitmap = []
        bits = (255 << (5 - i)) & 0x1f
        for _ in range(8):
            bitmap.append(bits)
        LCD.createChar(i, bitmap)

    # Create up/down icon (char 6)
    LCD.createChar(6, charSevenBitmaps[2])
    # By default, char 7 is loaded in 'pause' state
    LCD.createChar(7, charSevenBitmaps[1])
    # By default, char 8 is loaded in 'play' state
    LCD.createChar(8, charSevenBitmaps[0])


def threads_init():
    ''' Create the worker threads '''
    thrds = []

    # Create the lcd update worker thread and make it a daemon
    lcd_thread = threading.Thread(target=lcd_worker, args=(LCD_QUEUE,))
    lcd_thread.setDaemon(True)
    lcd_thread.start()
    thrds.append(lcd_thread)

    # Create the 2nd worker thread polling mpd and make it a daemon
    mpd_thread = threading.Thread(target=mpd_poller, args=(LCD_QUEUE,))
    mpd_thread.setDaemon(True)
    mpd_thread.start()
    thrds.append(mpd_thread)

    return thrds


def player_init():
    ''' Init Player '''

    # Stop music player
    # output = run_cmd("mpc stop") # NOTE: no need to stop what was playing

    # Display startup banner
    LCD_QUEUE.put((MSG_LCD, 'Welcome to\nRadio Pi'), True)

    time.sleep(2)
    LCD.clear()


def mpc_next(client):
    ''' Play the next track in current playlist '''
    client_status = client.status()
    if 'nextsong' in client_status:
        next_song = client_status['nextsong']
        client.next()
    else:
        next_song = '0'
        client.play(0)

    dbg_print('Track  % s' % (next_song))
    return True


def mpc_prev(client):
    ''' Play the prev track in current playlist '''
    client_status = client.status()
    # NOTE: sometimes song item is not in dict
    # TODO: fix it
    if client_status['song'] == '0':
        prev_song = int(client_status['playlistlength']) - 1
        client.play(prev_song)
    else:
        prev_song = int(client_status['song']) - 1
        client.previous()

    dbg_print('Track  % d' % (prev_song))
    return True


def mpc_vol_up(client, amt=5):
    ''' Volume up '''
    volume = AppConfig.get('volume', 'rpi_player')
    if volume <= (100-amt):
        volume += amt
        client.setvol(volume)
        dbg_print('Setting Volume  % d' % (volume))
        AppConfig.set(volume, 'volume', 'rpi_player')
        return True
    return False


def mpc_vol_down(client, amt=5):
    ''' Volume down '''
    volume = AppConfig.get('volume', 'rpi_player')
    if volume >= amt:
        volume -= amt
        client.setvol(volume)
        dbg_print('Setting Volume  % d' % (volume))
        AppConfig.set(volume, 'volume', 'rpi_player')
        return True
    return False


def mpc_toggle_pause(client):
    ''' toggle pause/play '''
    status = client.status()
    state = status['state']
    # if state is pause/stop then play. If play then pause
    pause = 1 if state == 'play' else 0
    client.pause(pause)
    dbg_print('Toggling play/pause')
    return True


def get_mpd_client():
    ''' get the mpd client. hack to avoid using the same global everywhere '''
    # extra steps to handle the situation where the mpd_client
    # connection seems to timeout while waiting
    while True:
        try:
            mpd_client.status()
        except ConnectionError:
            mpd_client.connect(AppConfig.get('host', 'mpdclient'),
                               AppConfig.get('port', 'mpdclient'))
            continue
        except MPDError as e:
            print('Exception: {}'.format(e))
            continue
        return mpd_client


def player_mode(**_kwargs):
    '''
    Inside a playlist manage the buttons to play nex prev track
    '''
    global display_mode_state

    dbg_print('inside player_mode - flushing')

    button_table = {SELECT: mpc_toggle_pause,
                    LEFT: mpc_prev,
                    RIGHT: mpc_next,
                    UP: mpc_vol_up,
                    DOWN: mpc_vol_down}
    display_mode_state_old = display_mode_state
    display_mode_state = LCD_PLAYER_MODE

    flush_buttons()

    while True:
        press = read_buttons()

        if not press:
            time.sleep(0.1)
            continue

        # SELECT button long pressed
        if press == (LONG_PRESS | SELECT):
            break  # Return back to main menu

        client = get_mpd_client()

        press &= 0x7F  # mask out the long press bit
        try:
            # Call the function handling the type of button press
            if press in button_table:
                button_table[press](client)

        except Exception as e:
            print('Exception: {}'.format(e))
            continue

    display_mode_state = display_mode_state_old


def flush_buttons():
    ''' clear button reads '''
    while LCD.buttons() != 0:
        delay_milliseconds(1)


def read_buttons():
    ''' read which button is pressed '''
    buttons = LCD.buttons()

    if not buttons:
        return 0

    # Debounce push buttons
    time_1 = time.time()
    time_2 = time_1
    if buttons != 0:
        while LCD.buttons() != 0:
            time_2 = time.time()
            delay_milliseconds(1)

    if (time_2 - time_1) > 0.2:
        buttons |= LONG_PRESS

    if buttons and DEBUG:
        print(f"Key press: {buttons:#0{4}x}")

    return buttons


def delay_milliseconds(milliseconds):
    ''' delay in mSec '''
    # divide milliseconds by 1000 for seconds
    seconds = milliseconds / float(1000)
    time.sleep(seconds)


def settings_save():
    ''' save settings to file '''
    AppConfig.config_save()


def save_settings_wrapper(**_kwargs):
    ''' display message on lcd and save settings '''
    LCD_QUEUE.put((MSG_LCD, "Saving          \nSettings ...    "), block=True)
    settings_save()
    time.sleep(1)
    LCD_QUEUE.put((MSG_LCD, "Settings        \nSaved ...       "), block=True)
    time.sleep(2)


def get_mpd_playlists():
    ''' Get the names of all playlists known to mpd '''
    mpd_playlists = []

    client = get_mpd_client()
    for playlist in client.listplaylists():
        dbg_print('available playlists')
        dbg_print(playlist)
        mpd_playlists.append(playlist['playlist'])

    return mpd_playlists


def get_mpd_artists():
    ''' Get the names of all artists known to mpd '''
    stored_artists = []

    client = get_mpd_client()
    for playlist in client.listplaylists():
        for song in client.listplaylistinfo(playlist['playlist']):
            if 'artist' in song and song['artist'] not in stored_artists:
                stored_artists.append(song['artist'])

    return stored_artists


# ----------------------------
# RADIO SETUP MENU
# ----------------------------
def audio_hdmi(**_kwargs):
    ''' audio output to HDMI jack '''
    run_cmd("amixer -q cset numid=3 1")


def audio_headphone(**_kwargs):
    ''' audio output to headphone port '''
    run_cmd("amixer -q cset numid=3 2")


def audio_auto(**_kwargs):
    ''' audio output auto-select '''
    run_cmd("amixer -q cset numid=3 0")


def display_ipaddr(**_kwargs):
    ''' show IP addr on display '''

    # connect to google dns server and find the address
    # this shows the address of the link with the default route
    sck = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sck.connect(("8.8.8.8", 80))
    ip_addr = sck.getsockname()[0].ljust(16, ' ')
    sck.close()

    LCD.backlight(LCD.VIOLET)
    i = 29
    keep_looping = True
    while keep_looping:
        # Every 1/2 second, update the time display
        i += 1
        if i % 5 == 0:
            LCD_QUEUE.put((MSG_LCD,
                           datetime.datetime.now().strftime(
                               '%b %d  %H:%M:%S\n') +
                           str(ip_addr)), block=True)

        # Every 100 milliseconds, read the switches
        press = read_buttons()
        # Take action on switch press

        # SELECT button = exit
        if press:
            keep_looping = False

        delay_milliseconds(99)

    LCD.backlight(AppConfig.get('lcdcolor', 'rpi_player'))


def run_cmd(cmd):
    ''' run an external command '''
    p = subprocess.Popen(cmd,
                         shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    output = p.communicate()[0]
    return output


# commands
def quit_app(**_kwargs):
    ''' quit the app '''
    LCD.clear()
    LCD.message('Are you sure?\nPress Sel for Y')
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        if LCD.buttonPressed(LCD.SELECT):
            LCD.clear()
            LCD.backlight(LCD.OFF)
            sys.exit()
        time.sleep(0.25)


def do_shutdown(**_kwargs):
    ''' Shutdown the board '''
    LCD.clear()
    LCD.message('Are you sure?\nPress Sel for Y')
    while 1:
        if LCD.buttonPressed(LCD.LEFT):
            break
        if LCD.buttonPressed(LCD.SELECT):
            LCD.clear()
            LCD.backlight(LCD.OFF)
            settings_save()
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
            sys.exit()
        time.sleep(0.25)


def lcd_turn_off(**_kwargs):
    ''' Turn LCD OFF '''
    LCD.backlight(LCD.OFF)


def lcd_turn_on(**_kwargs):
    ''' Turn LCD ON '''
    LCD.backlight(LCD.ON)


def lcd_set_color(**kwargs):
    '''
    Set the LCD color, kwargs has a key called 'text' that is displayed on the
    lcd menu and used to set the color on the physical lcd
    '''
    text_to_color = {'Red': LCD.RED, 'Green': LCD.GREEN,
                     'Blue': LCD.BLUE, 'Yellow': LCD.YELLOW,
                     'Teal': LCD.TEAL, 'Violet': LCD.VIOLET, }

    if 'text' in kwargs and kwargs['text'] in text_to_color:
        dbg_print('setting LCD to {}'.format(kwargs['text']))
        color = text_to_color[kwargs['text']]
        LCD.backlight(color)
        AppConfig.set(color, 'lcdcolor', 'rpi_player')


def dt_show(**_kwargs):
    ''' Show the data/time on lcd '''
    LCD.clear()
    while not LCD.buttons():
        time.sleep(0.25)
        LCD_QUEUE.put((MSG_LCD,
                       time.strftime('%a %b %d %Y\n%I:%M:%S %p',
                                     time.localtime())))


class Widget:
    ''' Widget Class for lcd items '''
    def __init__(self, myName, myFunction, kwargs):
        self.text = myName
        self.function = myFunction
        self.kwargs = kwargs


class Folder:
    ''' Folder Class for lcd items '''
    def __init__(self, myName, myParent):
        self.text = myName
        self.items = []
        self.parent = myParent


def loaded_playlist():
    ''' return the name of the playlist currently being played '''
    in_playlist = ''

    stored_playlists = []
    client = get_mpd_client()
    for i in client.listplaylists():
        name = i['playlist']
        stored_playlists.append(name)

    current_playlist = []
    for plistinfo in client.playlistinfo():
        song = plistinfo['file']
        current_playlist.append(song)

    for plist in stored_playlists:
        tmp_playlist = []
        for l_plist in client.listplaylist(plist):
            tmp_playlist.append(l_plist)

        if tmp_playlist == current_playlist:
            dbg_print("Currently in playlist: {}".format(plist))
            in_playlist = plist
            break
    return in_playlist


def mpc_load_playlist(**kwargs):
    '''
    load a named playlist, if already in that playlist, do nothing
    The name of the playlist comes from the menu selection that is there in
    kwargs['text']
    '''
    dbg_print('In mpc_load_playlist() label: %s' % (kwargs['text']))

    playlist_name = kwargs['text']
    client = get_mpd_client()

    if playlist_name != loaded_playlist():
        client.clear()
        client.load(playlist_name)
        client.play('0')

    player_mode(**{})
    return


def mpc_load_artist(**kwargs):
    '''
    clear the current playlist
    load a named artist
    The name of the artist comes from the menu selection that is there in
    kwargs['text']
    # TODO If the artist is already in effect, do NOT clear the playlist and
    start from 0
    '''
    dbg_print('In mpc_load_artist() label: %s' % (kwargs['text']))

    artist = kwargs['text']

    client = get_mpd_client()
    client.clear()
    client.findadd('artist', artist)
    client.play('0')

    player_mode(**{})


def form_playlists_menu(folder):
    '''
    Form the Playlist menu for the LCD
    '''
    for item in get_mpd_playlists():
        dbg_print('adding item %s to folder %s' % (item, folder.text))
        wdgt = Widget(item,
                      'mpc_load_playlist',
                      {'text': item})
        folder.items.append(wdgt)


def form_artists_menu(folder):
    '''
    Form the Artist menu for the LCD
    '''
    for item in get_mpd_artists():
        dbg_print('adding item %s to folder %s' % (item, folder.text))
        wdgt = Widget(item,
                      'mpc_load_artist',
                      {'text': item})
        folder.items.append(wdgt)


def process_node(current_node, current_folder):
    '''
    current_node is a dom.documentElement - a folder node from xml
    current_folder is of type Folder into which items from current_node are to
    be added
    '''

    dynamic_folder_handlers = {'Playlists': form_playlists_menu,
                               'Artists': form_artists_menu}
    current_node_text = current_node.getAttribute('text')

    dbg_print('IN process_node(%s, %s)' % (current_node_text,
                                           current_folder.text))

    if current_folder.text in dynamic_folder_handlers:
        dbg_print('adding dynamic labels to folder %s' % (current_node_text))
        dynamic_folder_handlers[current_node_text](current_folder)
        return

    children = current_node.childNodes

    for child in children:
        if isinstance(child, minidom.Element):
            # form a dict of all the attributes so that they can be used
            # by the widget later when/if needed
            attributes_d = {}
            for cav in child.attributes.values():
                attributes_d[cav.name] = cav.value

            child_text_attrib = child.getAttribute('text')

            if child.tagName == 'folder':
                this_folder = Folder(child_text_attrib, current_folder)
                current_folder.items.append(this_folder)
                process_node(child, this_folder)
            elif child.tagName == 'widget':
                this_widget = Widget(child_text_attrib,
                                     child.getAttribute('function'),
                                     attributes_d)
                current_folder.items.append(this_widget)
            '''
            elif child.tagName == 'run':
                thisCommand = CommandToRun(child_text_attrib,
                                           child.firstChild.data)
                current_folder.items.append(thisCommand)
            elif child.tagName == 'settings':
                HandleSettings(child)
            '''


class Display:
    ''' Class for sending info to LCD display '''
    def __init__(self, folder):
        self.current_folder = folder
        self.current_top_item = 0
        self.current_selected_item = 0
        # Map keys hit to functions
        self.upd_table = {LEFT: self.btn_left,
                          RIGHT: self.btn_right,
                          UP: self.btn_up,
                          DOWN: self.btn_down,
                          SELECT: self.btn_select
                          }

    def display(self):
        ''' decide what to display depending on where we are in the menu '''
        if self.current_top_item > len(self.current_folder.items) - LCD_ROWS:
            self.current_top_item = len(self.current_folder.items) - LCD_ROWS
        if self.current_top_item < 0:
            self.current_top_item = 0
        dbg_print('------------------')
        lcd_str = ''
        for row in range(self.current_top_item,
                         self.current_top_item+LCD_ROWS):
            if row > self.current_top_item:
                lcd_str += '\n'
            if row < len(self.current_folder.items):
                if row == self.current_selected_item:
                    cmd = '-'+self.current_folder.items[row].text
                    if len(cmd) < 16:
                        for _ in range(len(cmd), 16):
                            cmd += ' '
                    dbg_print('|'+cmd+'|')
                    lcd_str += cmd
                else:
                    cmd = ' '+self.current_folder.items[row].text
                    if len(cmd) < 16:
                        for _ in range(len(cmd), 16):
                            cmd += ' '
                    dbg_print('|'+cmd+'|')
                    lcd_str += cmd
        dbg_print('------------------')
        LCD_QUEUE.put((MSG_LCD, lcd_str), block=True)

    def update(self, key):
        ''' take action an an item chosen in menu '''
        if key in self.upd_table:
            self.upd_table[key]()

    def btn_up(self):
        ''' go up one menu item '''
        if self.current_selected_item == 0:
            return
        if self.current_selected_item > self.current_top_item:
            self.current_selected_item -= 1
        else:
            self.current_top_item -= 1
            self.current_selected_item -= 1

    def btn_down(self):
        ''' go down one menu item '''
        if self.current_selected_item+1 == len(self.current_folder.items):
            return
        if self.current_selected_item < self.current_top_item+LCD_ROWS-1:
            self.current_selected_item += 1
        else:
            self.current_top_item += 1
            self.current_selected_item += 1

    def btn_left(self):
        ''' menu item go back '''
        if isinstance(self.current_folder.parent, Folder):
            # find the current in the parent
            itemno = 0
            index = 0
            for item in self.current_folder.parent.items:
                if self.current_folder == item:
                    dbg_print('foundit')
                    index = itemno
                else:
                    itemno += 1
            if index < len(self.current_folder.parent.items):
                self.current_folder = self.current_folder.parent
                self.current_top_item = index
                self.current_selected_item = index
            else:
                self.current_folder = self.current_folder.parent
                self.current_top_item = 0
                self.current_selected_item = 0

    def btn_right(self):
        ''' menu item selected go forward '''
        if isinstance(self.current_folder.items[self.current_selected_item],
                      Folder):
            self.current_folder \
                = self.current_folder.items[self.current_selected_item]
            self.current_top_item = 0
            self.current_selected_item = 0
        elif isinstance(self.current_folder.items[self.current_selected_item],
                        Widget):
            dbg_print('going to call %s()' %
                      (self.current_folder.items[self.current_selected_item]
                       .function))
            eval(self.current_folder.items[self.current_selected_item].function
                 + '(**self.current_folder.items'
                 '[self.current_selected_item].kwargs)')

    def btn_select(self):
        ''' menu item selected. do something '''
        if isinstance(self.current_folder.items[self.current_selected_item],
                      Folder):
            self.current_folder = self.current_folder.items[
                self.current_selected_item]
            self.current_top_item = 0
            self.current_selected_item = 0
        elif isinstance(self.current_folder.items[self.current_selected_item],
                        Widget):
            dbg_print('going to call %s()' %
                      (self.current_folder.items[self.current_selected_item]
                       .function))
            eval(self.current_folder.items
                 [self.current_selected_item].function
                 + '(**self.current_folder.items'
                 '[self.current_selected_item].kwargs)')


# ----------------------------
# MAIN LOOP
# ----------------------------
def main():
    '''
    Main function to init stuff and start player
    '''

    dbg_print('entering main()')

    settings_load()
    mpdc_init()
    lcd_init()

    thrds = threads_init()
    player_init()

    ui_items = Folder('root', '')

    # parse an XML file by name
    dom = minidom.parse(MENUFILE)

    top = dom.documentElement

    process_node(top, ui_items)

    player_mode(**{})

    display = Display(ui_items)
    display.display()

    dbg_print('entering while() in main()')

    while 1:
        # Poll all buttons once, avoids repeated I2C traffic
        pressed = read_buttons()
        pressed &= 0x7F  # we are not interested in LONG_PRESS

        if pressed:
            display.update(pressed)
            display.display()
        time.sleep(0.15)

    for thrd in thrds:
        thrd.join()


if __name__ == '__main__':
    main()

# vim: set expandtab shiftwidth=4 softtabstop=4 textwidth=79 ai:
