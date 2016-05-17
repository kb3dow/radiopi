# NOTE: Code taken from
# http:##jmsarduino.blogspot.com/2009/10/4-way-button-click-double-click-hold.html
# 4-Way Button: Click, Double-Click, Press+Hold, and Press+Long-Hold
# By Jeff Saltzman
# Oct. 13, 2009

# Return Values
# 1) Click: rapid press and release
# 2) Double-Click: two clicks in quick succession
# 3) Press and Hold: holding the button down
# 4) Long Press and Hold: holding the button down for a long time

'''
void loop()
{
    ## Get button event and act accordingly
    int b = checkButton();
    if (b == 1) clickEvent();
    if (b == 2) doubleClickEvent();
    if (b == 3) holdEvent();
    if (b == 4) longHoldEvent();
}
'''


'''
    MULTI-CLICK: One Button, Multiple Events

    Oct 12, 2009
    Run checkButton() to retrieve a button event:
    Click
    Double-Click
    Hold
    Long Hold
'''

import time
current_milli_time = lambda: int(round(time.time() * 1000))

# Button timing variables
dbounce = 20    # ms debounce period to prevent flickering when pressing
# or releasing the button
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


def checkButton():
    int event = 0
    # Read the state of the button
    buttonVal = digitalRead(buttonPin)
    # Button pressed down
    if (buttonVal == LOW and buttonLast == HIGH
            and (millis() - upTime) > debounce):
        downTime = millis()
        ignoreUp = False
        waitForUp = False
        singleOK = True
        holdEventPast = False
        longHoldEventPast = False
        if ((millis()-upTime) < DCgap
                and DConUp is False
                and DCwaiting is True):
            DConUp = True
        else:
            DConUp = False
        DCwaiting = False
    # Button released
    else if (buttonVal == HIGH
            and buttonLast == LOW
            and (millis() - downTime) > debounce):
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
