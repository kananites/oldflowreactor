import serial
from instruments import SerialTempController

with serial.Serial('COM3', 9600, timeout = 0.5) as tc_serial:
    tc1 = SerialTempController(tc_serial, "1")
    tc2 = SerialTempController(tc_serial, "2")
    tc1.set_set_temp(25)
    tc2.set_set_temp(25)