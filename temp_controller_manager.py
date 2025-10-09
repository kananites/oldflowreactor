import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import serial
import time
import maya

from abc import ABC
from abc import abstractmethod
from attr import attr
from attr import attrs
from math import exp
from tzolkin import SynchronousSchedule

from temp_ramp import DEG_C
from temp_ramp import MINUTE
from temp_ramp import HOUR
from temp_ramp import SECOND
from temp_ramp import TempRamp
from instruments import SerialTempController
from serial_wrapper import SerialWrapper


print("Setting Up")

datestring = maya.now().datetime().strftime("%m-%d-%y")
LOG_FILENAME = '%s-TC.csv' % datestring
# LOG_FILENAME = '05-20-25-TC.csv'

# HOLD_TIME  20 * MINUTE
HOLD_TIME = 15 * HOUR #62 during hold, 3 or 4 during ramp
RAMP_RATE = 5 * DEG_C / MINUTE
# RAMP_RATE = 10 * DEG_C / MINUTE #forquick heating
# temp_ramp = TempRamp(
#     [25,     350,     375,     400,
#         425,     450,     475,     500,    25],
#     [0] + [HOLD_TIME] * 7,
#     [RAMP_RATE] * 7 + [0],
# )

# temp_ramp = TempRamp(
#     [25,     250,     300,     350,
#         400,     450,     500,    25],
#     [0] + [HOLD_TIME] * 6,
#     [RAMP_RATE] * 6 + [0],
# )

# temp_ramp = TempRamp(
#     [25,    400,    450,     500,   550,    600,    650,    700, 500,  25],
#     [0] + [HOLD_TIME] *8 ,
#     [RAMP_RATE] * 8 + [0],
# )

# temp_ramp = TempRamp(
#     [25,    450,     500,   550,    600,    650,    700,   25],
#     [0] + [HOLD_TIME] *6 ,
#     [RAMP_RATE] * 6 + [0],
# )

temp_ramp = TempRamp(
    [25,   450,    500,   550,    600,    650,   700, 25],
    [0] + [4 * HOUR] + [4 * HOUR] + [4 * HOUR] + [4 * HOUR] + [4 * HOUR] + [4 * HOUR],
    [RAMP_RATE] * 6 + [0],
)

# temp_ramp = TempRamp(
#     [25,    450,   500,   550,    600,    650,   700,    500,   25],
#     [0] + [HOLD_TIME] * 6 + [12 * HOUR],
#     [RAMP_RATE] * 7 + [0],
# )

# temp_ramp = TempRamp(
#     [25,    700,   25],
#     [0] + [5 * HOUR],
#     [RAMP_RATE] * 1 + [0],
# )

# temp_ramp = TempRamp(
#     [25,    475,   500,    525,    550,    575,   25],
#     [0] + [HOLD_TIME] * 5,
#     [RAMP_RATE] * 5 + [0],
# )

# temp_ramp = TempRamp(
#     [25,    500,    700,   500,   25],
#     [0] + [HOLD_TIME] * 2 + [6*HOUR],
#     [RAMP_RATE] * 3 + [0],
# )
# temp_ramp = TempRamp(
#     [25,     350,     375,     400,
#         425,     450,     475,     500,    400,   25],
#     [0] + [HOLD_TIME] * 7 + [48*HOUR],
#     [RAMP_RATE] * 8 + [0],
# )

# temp_ramp = TempRamp(
#     [25,     450,   25],
#     [0] + [HOLD_TIME] *1,
#     [RAMP_RATE] * 1 + [0],
# )

# temp_ramp = TempRamp(
#     [25,    300,    600,    300,     25],
#     [0] + [6*HOUR] + [20*HOUR] + [3*HOUR],
#     [RAMP_RATE] * 3 + [0],
# )
# temp_ramp = TempRamp(
#     [25,     25],
#     [0] ,
#     [0],
# )
# temp_ramp = TempRamp(
#     [25,     500,     700,     500,     700,     500,     700,     500,    700,     500,   25],
#     [0] + [4*HOUR] + [12*HOUR] + [4*HOUR] + [12*HOUR] + [4*HOUR] + [12*HOUR] + [4*HOUR] + [12*HOUR] + [12*HOUR],
#     [RAMP_RATE] * 9 + [0],
# )

# temp_ramp = TempRamp(
#     [190,     625,     550,     675,    550,    25],
#     [0] + [6*HOUR] + [HOLD_TIME] * 3,
#     [RAMP_RATE] * 4 + [0],
# )

print("Expected runtime: %.2f hours" % (max(temp_ramp.ramp_points()[0]) / HOUR))

ramp_start_time = time.time()
ramp_control_times, ramp_control_temps = temp_ramp.control_points()
ramp_control_times = np.array(ramp_control_times)


tc_serial = SerialWrapper.create('COM3', 9600)
print("Serial Connection Opened")

temp_controller1 = SerialTempController(tc_serial, "1")
temp_controller2 = SerialTempController(tc_serial, "2") #should be 2 for reading internal TC, but we've removed it for now

log_f = open(LOG_FILENAME, 'a')

#log_fig, log_ax = plt.subplots()
#log_fig.suptitle("Live Log")

#plt.ion()
#plt.show(block=False)

def log_temp_status():
    print("Logging Temp")
    log_f.write("%s, %.1f, %.1f, %.1f\n" % (
        maya.now().datetime().strftime("%m-%d-%YT%H:%M:%S.%f"),
        temp_controller1.get_set_temp(),
        temp_controller1.get_temp(),
        temp_controller2.get_temp(),
    ))
    log_f.flush()


def plot_temp_log():
    print("Plotting Log")
    with open(LOG_FILENAME) as log_f:
        df = pd.read_csv(
            log_f, names=['Time', 'Setpoint', 'Actual T(1)', 'Actual T(2)'])
        print(df)
        print("DF Loaded Plotting")
        log_ax.clear()
        df.plot(x=0, y=1, ax=log_ax)
        df.plot(x=0, y=2, ax=log_ax)
        df.plot(x=0, y=3, ax=log_ax)


def update_set_point():
    print("Updating Set Point")
    desired_set_point_idx = np.argmax(
        ramp_control_times > (time.time() - ramp_start_time) * SECOND / MINUTE
    ) - 1
    desired_set_point = ramp_control_temps[desired_set_point_idx]

    # TODO(woursler): This whole system is a massive hack.
    if desired_set_point != temp_controller1.get_set_temp():
        temp_controller1.set_set_temp(desired_set_point)


print("Making Schedule")

# Run scheduled events with possible error of 0.1 seconds.
schedule = SynchronousSchedule(0.1, sleep=plt.pause)
schedule.every("@s").do(update_set_point)  # TODO(woursler): Fix this up?
schedule.every("@s").do(log_temp_status)
#schedule.every("@s").do(plot_temp_log)

print("Starting to execute schedule")

schedule.start_blocking()

print("Cleaning Up")

log_f.close()
tc_serial.close()
