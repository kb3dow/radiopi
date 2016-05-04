# ListSelector.py
#
# Created by Alan Aufderheide, February 2013
#
# Given a list of items in the passed list,
# allow quick access by picking letters progressively.
# Uses up/down to go up and down where cursor is.
# Move left/right to further filter to quickly get to item.
# Still need to do case insensitive, and sort.
from time import sleep
from Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
from time                  import sleep

# Buttons
NONE           = 0x00
SELECT         = 0x01
RIGHT          = 0x02
DOWN           = 0x04
UP             = 0x08
LEFT           = 0x10
UP_AND_DOWN    = 0x0C
LEFT_AND_RIGHT = 0x12

class ListSelector:
    def __init__(self, theList, theLcd):
        self.list = []
        for item in theList:
            if isinstance(item, basestring):
                self.list.append(item)
            else:
                self.list.append(item[0])
        self.lcd = theLcd

    def delay_milliseconds(milliseconds):
       seconds = milliseconds / float(1000)	# divide milliseconds by 1000 for seconds
       sleep(seconds)

    def read_buttons(self):
       buttons = self.lcd.buttons()
       # Debounce push buttons
       if(buttons != 0):
          while(self.lcd.buttons() != 0):
             delay_milliseconds(1)
       return buttons

    def Pick(self):
        sleep(0.5)
        curitem = 0
        curlen = 1
        self.lcd.clear()
        self.lcd.message(self.list[curitem])
        self.lcd.home()
        self.lcd.blink()
        self.lcd.setCursor(0,0)
        while 1:
            press = read_buttons()
            #if self.lcd.buttonPressed(self.lcd.SELECT):
            if (press == SELECT):
                sleep(0.5)
                break
            #if self.lcd.buttonPressed(self.lcd.UP):
            if (press == UP):
                tempitem = curitem
                prevstr = self.list[tempitem][:curlen]
                while tempitem > 0 and self.list[tempitem-1][:curlen-1] == self.list[curitem][:curlen-1] and self.list[tempitem][:curlen] >= prevstr:
                    tempitem -= 1
                curitem = tempitem
                # overwrite message, uses spaces to clear previous entries
                self.lcd.home()
                self.lcd.message(self.list[curitem]+'                ')
                self.lcd.setCursor(curlen-1,0)
                sleep(0.5)
            #if self.lcd.buttonPressed(self.lcd.DOWN):
            if (press == DOWN):
                nextstr = self.list[curitem][:curlen-1]+chr(ord(self.list[curitem][curlen-1])+1)
                tempitem = curitem
                while tempitem+1 < len(self.list) and self.list[tempitem+1][:curlen-1] == self.list[curitem][:curlen-1] and self.list[tempitem] < nextstr:
                    tempitem += 1
                if tempitem < len(self.list):
                    curitem = tempitem
                # overwrite message, uses spaces to clear previous entries
                self.lcd.home()
                self.lcd.message(self.list[curitem]+'                ')
                self.lcd.setCursor(curlen-1,0)
                sleep(0.5)
            #if self.lcd.buttonPressed(self.lcd.RIGHT):
            if (press == RIGHT):
                if curlen < len(self.list[curitem]):
                    curlen += 1
                self.lcd.setCursor(curlen-1,0)
                self.lcd.blink()
                sleep(0.5)
            #if self.lcd.buttonPressed(self.lcd.LEFT):
            if (press == LEFT):
                if curlen > 1:
                    curlen -= 1
                self.lcd.setCursor(curlen-1,0)
                self.lcd.blink()
                sleep(0.5)

        self.lcd.setCursor(0,0)
        self.lcd.noBlink()
        return curitem

