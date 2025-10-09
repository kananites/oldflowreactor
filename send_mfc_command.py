import serial
import time

from instruments import SerialMFCController
from serial_wrapper import SerialWrapper

ser = SerialWrapper.create('COM6', 19200)

mfcs = {
    channel: SerialMFCController(ser, channel)
    for channel in ['a', 'b', 'c']
}

mfcs['a'].set_flow(20)
time.sleep(1)
mfcs['b'].set_flow(20)
time.sleep(1)
mfcs['c'].set_flow(2.5)
