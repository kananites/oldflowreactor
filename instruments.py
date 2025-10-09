import numpy as np
import serial
import time

from abc import ABC
from abc import abstractmethod
from attr import attr
from attr import attrs
from math import exp


@attrs
class MFCStatus:
    channel: str = attr()
    abs_pressure: float = attr()
    temperature: float = attr()
    volumetric_flow: float = attr()
    standard_mass_flow: float = attr()
    setpoint: float = attr()
    gas_type: str = attr()

    @staticmethod
    def parse_raw_response(response):
        columns = response.strip().split()
        columns = [elem for elem in columns if b'MOV' not in elem]
        # needed to do this with old BB9 for some reason, no longer needed (08-16-23)
        # columns = columns[:-1]
        # assert len(columns) == 7, columns
        # Handle malformed responses gracefully
        if len(columns) != 7:
            raise ValueError(f"Invalid response format: expected 7 columns, got {len(columns)}. Response: {columns}")

        # if columns[6].endswith(b'\\r\\x00'): # for old BB3
        #for new BB9 (08-16-23)
        if columns[6].endswith(b'\\r'):
            columns[6] = columns[6][:-6]

        return MFCStatus(
            channel=columns[0].decode('utf-8'),
            abs_pressure=float(columns[1]),
            temperature=float(columns[2]),
            volumetric_flow=float(columns[3]),
            standard_mass_flow=float(columns[4]),
            setpoint=float(columns[5]),
            gas_type=columns[6].decode('utf-8'),
        )


class TempController(ABC):
    @abstractmethod
    def get_temp(self):
        pass

    @abstractmethod
    def get_power_usage(self):
        pass

    @abstractmethod
    def get_set_temp(self):
        pass

    @abstractmethod
    def set_set_temp(self, temp: float):
        pass


class MFCController(ABC):
    @abstractmethod
    def get_state(self) -> MFCStatus:
        pass

    @abstractmethod
    def set_flow(self, flow_rate: float):
        pass


@attrs
class SerialMFCController(MFCController):
    ser: serial.Serial = attr()
    address: str = attr()

    def get_state(self):
        # not sure why, but queries need to be bracketed by '\r' for it recognize the command
        self.ser.write(b'\r%s\r' % bytes(self.address, 'utf-8'))
        response = self.ser.readline().strip()
        return MFCStatus.parse_raw_response(response)

    # def set_flow(self, flow_rate):
    #     # not sure why, but queries need to be bracketed by '\r' for it recognize the command
    #     self.ser.write(b'\r%sS%.2f\r' % (
    #         bytes(self.address, 'utf-8'),
    #         flow_rate,
    #     ))
    #     response = self.ser.readline().strip()
    #     status = MFCStatus.parse_raw_response(response)
    #     assert abs(status.setpoint - flow_rate) < 0.01, response

    def set_flow(self, flow_rate, max_retries=3):
        """Set flow rate with retry logic for handling communication errors"""
        for attempt in range(max_retries):
            try:
                # not sure why, but queries need to be bracketed by '\r' for it recognize the command
                self.ser.write(b'\r%sS%.2f\r' % (
                    bytes(self.address, 'utf-8'),
                    flow_rate,
                ))
                response = self.ser.readline().strip()
                
                # Check if we got a valid response
                if not response:
                    raise ValueError(f"Empty response from Alicat MFC (attempt {attempt + 1}/{max_retries})")
                
                status = MFCStatus.parse_raw_response(response)
                
                # Verify the setpoint was set correctly
                if abs(status.setpoint - flow_rate) >= 0.01:
                    raise ValueError(f"Setpoint mismatch: expected {flow_rate}, got {status.setpoint} (attempt {attempt + 1}/{max_retries})")
                
                # Success - return the status
                return status
                
            except Exception as e:
                if attempt == max_retries - 1:
                    # Last attempt failed, raise the error
                    raise RuntimeError(f"Failed to set Alicat MFC flow rate after {max_retries} attempts. Last error: {e}")
                else:
                    # Wait before retrying
                    time.sleep(0.1)
                    continue

@attrs
class SerialTempController(TempController):
    ser: serial.Serial = attr()
    address: str = attr()

    def get_power_usage(self):
        self.ser.write(b'Z(%s)\r' % bytes(self.address, 'utf-8'))
        response = self.ser.readline().strip()
        try:
            return float(response)
        except:
            print("Couldn't parse", response)
            return -1

    def get_temp(self):
        self.ser.write(b'T(%s)\r' % bytes(self.address, 'utf-8'))
        response = self.ser.readline().strip()
        return float(response)

    def get_set_temp(self):
        self.ser.write(b'P(%s)\r' % bytes(self.address, 'utf-8'))
        response = self.ser.readline().strip()
        return float(response)

    def set_set_temp(self, temp: float):
        self.ser.write(b'S(%s,%.1f)\r' % (bytes(self.address, 'utf-8'), temp))
        response = self.ser.readline().strip()
        echoed_temp = float(response)
        assert abs(echoed_temp - temp) < 0.01, response


@attrs
class DummyTempController(TempController):
    last_temp: float = attr(default=20)
    last_record_time = attr(factory=time.time)

    k = attr(default=0.5)

    set_temp = attr(default=20)

    def get_temp(self):
        now = time.time()

        dt = now - self.last_record_time

        temp_now = self.set_temp + \
            (self.last_temp - self.set_temp) * exp(-self.k * dt)

        self.last_temp = temp_now
        self.last_record_time = now

        return temp_now + 0.2 * np.random.uniform(-1, 1)

    def get_power_usage(self):
        return 3.1415

    def get_set_temp(self):
        return self.set_temp

    def set_set_temp(self, temp):
        # Record the temp before the change
        self.get_temp()

        self.set_temp = temp
