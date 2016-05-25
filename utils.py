import time


# Current time in milli seconds. Taken from
# http://stackoverflow.com/questions/5998245/get-current-time-in-milliseconds-in-python
def millis():
    return int(round(time_.time() * 1000))
