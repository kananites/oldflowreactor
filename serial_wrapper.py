import serial
import time
import maya

from attr import attr
from attr import attrs


@attrs
class SerialWrapper:
    raw_serial: serial.Serial = attr()
    log_f = attr()

    @staticmethod
    def timestamp():
        return maya.now().datetime().strftime("%m-%d-%YT%H:%M:%S.%f")

    def write(self, data):
        self.log_f.write("#%s# > %s\n" % (
            SerialWrapper.timestamp(),
            data,
        ))
        self.log_f.flush()
        self.raw_serial.write(data)

    # TODO(woursler): Handle exceptions
    def readline(self):
        response = self.raw_serial.readline()
        self.log_f.write("#%s# < %s\n" % (
            SerialWrapper.timestamp(),
            response,
        ))
        self.log_f.flush()
        return response

    @staticmethod
    def create(port, baud_rate, serial_log_f=None):
        if serial_log_f is None:
            datestring = maya.now().datetime().strftime("%m-%d-%y")
            log_fname = "%s-%s.log" % (datestring, port)
            serial_log_f = open(log_fname, 'a')

        raw_serial = serial.Serial(port, baud_rate, timeout=0.5)

        serial_log_f.write("#%s# # Opening %s at %d baud\n" % (
            SerialWrapper.timestamp(),
            port,
            baud_rate
        ))
        serial_log_f.flush()

        return SerialWrapper(
            raw_serial,
            serial_log_f,
        )
