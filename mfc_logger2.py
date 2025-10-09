import serial
import maya
import time

from attr import attr, attrs
from instruments import SerialMFCController
from serial_wrapper import SerialWrapper

datestring = maya.now().datetime().strftime("%m-%d-%y")
f = open('%s-MFC.csv' % datestring, 'a')

ser = SerialWrapper.create('COM4', 19200)

mfcs = [
    SerialMFCController(ser, 'a'),
    SerialMFCController(ser, 'b'),
    SerialMFCController(ser, 'c'),
    SerialMFCController(ser, 'd'),
]

# mfc_b = mfcs[1]
# MFC_B_RESET_FLOW = 0
# MFC_B_OPERATIONAL_FLOW = 20
# MFC_B_RESET_DURATION = 30
# MFC_B_RESET_COOLDOWN_SECS = 60
# MFC_B_LAST_RESET_TIME = maya.now()  # Give some leeway when we start.

while True:
    # have to wait in between queries or else it gets confused and returns gibberish
    time.sleep(10)
    for mfc in mfcs:
        print("Getting MFC State", mfc.address)
        mfc_status = mfc.get_state()
        print("Got state")

        channel: str = attr()
        abs_pressure: float = attr()
        temperature: float = attr()
        volumetric_flow: float = attr()
        standard_mass_flow: float = attr()
        setpoint: float = attr()
        gas_type: str = attr()

        f.write("%s,%s,%.2f,%.2f,%.2f,%.2f,%.2f,%s\n" % (
            maya.now().datetime().strftime("%m-%d-%YT%H:%M:%S.%f"),
            mfc_status.channel,
            mfc_status.abs_pressure,
            mfc_status.temperature,
            mfc_status.volumetric_flow,
            mfc_status.standard_mass_flow,
            mfc_status.setpoint,
            mfc_status.gas_type,
        ))
        f.flush()

    # Check if we need to reset MFC B
    # mfc_b_status = mfc_b.get_state()
    # if maya.now() > MFC_B_LAST_RESET_TIME.add(seconds=MFC_B_RESET_COOLDOWN_SECS) and mfc_b_status.standard_mass_flow > 1.2 * mfc_b_status.setpoint:
    #     MFC_B_LAST_RESET_TIME = maya.now()
    #     print("MFC[B] Anomaly Detected. Resetting. Logging Interrupted.", MFC_B_LAST_RESET_TIME)
    #     mfc_b.set_flow(MFC_B_RESET_FLOW)
    #     time.sleep(MFC_B_RESET_DURATION)
    #     mfc_b.set_flow(MFC_B_OPERATIONAL_FLOW)
    #     print("Logging Resumed.")

f.close()
