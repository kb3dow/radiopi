import time

# NOTE: Code taken from
# http:##jmsarduino.blogspot.com/2009/10/4-way-button-click-double-click-hold.html
# 4-Way Button: Click, Double-Click, Press+Hold, and Press+Long-Hold
# By Jeff Saltzman
# Oct. 13, 2009


# TODO: Move to a utils.py file later
# Current time in milli seconds. Taken from
# http://stackoverflow.com/questions/5998245/get-current-time-in-milliseconds-in-python
def millis():
    return int(round(time_.time() * 1000))

# Button timing variables
# ms debounce period to avoid flickering when pressing or releasing the button
dbounce = 20
DCgap = 250  # max ms between clicks for a double click event
holdTime = 2000  # ms hold period: how long to wait for press+hold event
longHoldTime = 5000  # ms long hold period:
# how long to wait for press+hold event

# Other button variables
buttonVal = True  # value read from button
buttonLast = True  # buffered value of the button's previous state
DCwaiting = False  # whether we're waiting for a double click (down)
DConUp = False  # whether to register a double click on next release,
# or whether to wait and click
singleOK = True  # whether it's OK to do a single click
downTime = -1  # time the button was pressed down
upTime = -1  # time the button was released
ignoreUp = False  # whether to ignore the button release because the
# click+hold was triggered
waitForUp = False  # when held, whether to wait for the up event
holdEventPast = False  # whether not the hold event happened already
longHoldEventPast = False  # whether the long hold event happened already


# Check to see if button pressed or held
# Return Values
# 1) Click: rapid press and release
# 2) Double-Click: two clicks in quick succession
# 3) Press and Hold: holding the button down
# 4) Long Press and Hold: holding the button down for a long time
def checkButton():
    int event = 0
    # Read the state of the button
    buttonVal = digitalRead(buttonPin)
    # Button pressed down
    if (buttonVal == LOW and buttonLast == HIGH and
            (millis() - upTime) > debounce):
        downTime = millis()
        ignoreUp = False
        waitForUp = False
        singleOK = True
        holdEventPast = False
        longHoldEventPast = False
        if (millis()-upTime) < DCgap and not DConUp and DCwaiting:
            DConUp = True
        else:
            DConUp = False
        DCwaiting = False
    # Button released
    else if (buttonVal and not buttonLast and
             (millis() - downTime) > debounce):
        if not ignoreUp:
            upTime = millis()
            if not DConUp:
                DCwaiting = True
            else:
                event = 2
                DConUp = False
                DCwaiting = False
                singleOK = False

    # Test for normal click event: DCgap expired
    if buttonVal and ((millis()-upTime) >= DCgap)
    and DCwaiting and not DConUp and singleOK:
        event = 1
        DCwaiting = False

    # Test for hold
    if (not buttonVal and (millis() - downTime) >= holdTime):
        # Trigger "normal" hold
        if not holdEventPast:
            event = 3
            waitForUp = True
            ignoreUp = True
            DConUp = False
            DCwaiting = False
            # downTime = millis();
            holdEventPast = true

        # Trigger "long" hold
        if ((millis() - downTime) >= longHoldTime):
            if (not longHoldEventPast):
                event = 4
                longHoldEventPast = true

    buttonLast = buttonVal
    return event
