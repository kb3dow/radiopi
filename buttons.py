import utils

# NOTE: Code taken from
# http:##jmsarduino.blogspot.com/2009/10/4-way-button-click-double-click-hold.html
# 4-Way Button: Click, Double-Click, Press+Hold, and Press+Long-Hold
# By Jeff Saltzman
# Oct. 13, 2009


# Button timing variables
# ms debounce period to avoid flickering when pressing or releasing the button
dbounce = 20
# max ms between clicks for a double click event
DCgap = 250
# ms hold period: how long to wait for press+hold event
holdTime = 2000
# ms long hold period: how long to wait for press+hold event
longHoldTime = 5000

# Button click type
PRESS_NONE = 0x00
PRESS_CLICK = 0x01
PRESS_DCLICK = 0x02
PRESS_LONG = 0x04
PRESS_HOLD = 0x08


class Button:
    def __init__(self, buttonType):
        self.buttonType = buttonType

        # Button variables
        # value read from button
        this.buttonVal = True
        # buffered value of the button's previous state
        this.buttonLast = True
        # whether we're waiting for a double click (down)
        this.DCwaiting = False
        # whether to register a double click on next release,
        # or whether to wait and click
        this.DConUp = False
        # whether it's OK to do a single click
        this.singleOK = True
        # time the button was pressed down
        this.downTime = -1
        # time the button was released
        this.upTime = -1
        # whether to ignore the button release because the
        # click+hold was triggered
        this.ignoreUp = False
        # when held, whether to wait for the up event
        this.waitForUp = False
        # whether not the hold event happened already
        this.holdEventPast = False
        # whether the long hold event happened already
        this.longHoldEventPast = False

    # Check to see if button pressed or held
    # Return Values
    # 1) Click: rapid press and release
    # 2) Double-Click: two clicks in quick succession
    # 3) Press and Hold: holding the button down
    # 4) Long Press and Hold: holding the button down for a long time
    def checkButton():
        int event = PRESS_NONE
        # Read the state of the button
        this.buttonVal = digitalRead(buttonPin)
        # Button pressed down
        if (this.buttonVal == LOW and this.buttonLast == HIGH and
                (millis() - this.upTime) > debounce):
            this.downTime = millis()
            this.ignoreUp = False
            this.waitForUp = False
            this.singleOK = True
            this.holdEventPast = False
            this.longHoldEventPast = False
            if (millis()-this.upTime) < DCgap
            and not this.DConUp and this.DCwaiting:
                this.DConUp = True
            else:
                this.DConUp = False
            this.DCwaiting = False
        # Button released
        else if (this.buttonVal and not this.buttonLast and
                (millis() - this.downTime) > debounce):
            if not this.ignoreUp:
                this.upTime = millis()
                if not this.DConUp:
                    this.DCwaiting = True
                else:
                    event = PRESS_DCLICK
                    this.DConUp = False
                    this.DCwaiting = False
                    this.singleOK = False

        # Test for normal click event: DCgap expired
        if this.buttonVal and ((millis()-this.upTime) >= DCgap)
        and this.DCwaiting and not this.DConUp and this.singleOK:
            event = PRESS_CLICK
            this.DCwaiting = False

        # Test for hold
        if (not this.buttonVal and (millis() - this.downTime) >= holdTime):
            # Trigger "normal" hold
            if not this.holdEventPast:
                event = PRESS_LONG
                this.waitForUp = True
                this.ignoreUp = True
                this.DConUp = False
                this.DCwaiting = False
                # this.downTime = millis();
                this.holdEventPast = true

            # Trigger "long" hold
            if ((millis() - this.downTime) >= longHoldTime):
                if (not this.longHoldEventPast):
                    event = PRESS_HOLD
                    this.longHoldEventPast = true

        this.buttonLast = this.buttonVal
        return (this.buttonType, event)
