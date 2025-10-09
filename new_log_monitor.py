import humanize
import matplotlib.pyplot as plt
import maya
import numpy as np
import os
import sys

from attr import attr
from attr import attrs
from box import Box
from typing import List
from tzolkin import SynchronousSchedule


@attrs
class LivingLog:
    f_name = attr()

    cursor = attr(default=0)

    def new_entries(self) -> List[str]:
        f_size = os.stat(self.f_name).st_size
        assert f_size >= self.cursor, "File Shrunk! Not append only"

        if f_size == self.cursor:
            return []

        with open(self.f_name) as f_handle:
            f_handle.seek(self.cursor)
            rest_of_file = f_handle.read()
            if rest_of_file[-1] != '\n':
                return []
            lines = rest_of_file.split('\n')[:-1]
            self.cursor = f_handle.tell()
            return lines


plt.style.use('monitor.mplstyle')

REFERENCE_TIME = maya.now()
REFERENCE_DATESTRING = REFERENCE_TIME.datetime().strftime("%m-%d-%y")

# TC_LOG_FILENAME = r'%s-TC.csv' % REFERENCE_DATESTRING
TC_LOG_FILENAME = r'09-17-25-TC.csv' #% REFERENCE_DATESTRING
MFC_LOG_FILENAME = r'09-17-25-MFC.csv' #% REFERENCE_DATESTRING

# TC Constants and Objects
TC_LOG_HEADERS = ['timestamp', 'setpoint', 'internal_tc', 'external_tc']
TC_DATA_HEADERS = ['reltime', 'Setpoint',
                   'Internal Control TC', 'External Monitor TC']
tc_log = LivingLog(TC_LOG_FILENAME)
tc_data = np.zeros((0, len(TC_DATA_HEADERS)))
tc_fig, tc_ax = plt.subplots()
tc_fig.suptitle("TC Live Log")

tc_last_comm_time = None

# MFC Constants and Objects
MFC_LOG_HEADERS = ['timestamp', 'mfc_channel', 'abs_pressure',
                   'temp', 'vol_flow', 'flow', 'setpoint', 'gas_type']
# MFC_CHANNELS = ['A', 'B', 'C','D']
MFC_CHANNELS = ['D']
MFC_DATA_HEADERS = ['reltime', 'Flow', 'Setpoint']
mfc_log = LivingLog(MFC_LOG_FILENAME)
mfc_data = {
    mfc_channel: np.zeros((0, len(MFC_DATA_HEADERS)))
    for mfc_channel in MFC_CHANNELS
}
mfc_fig, mfc_ax = plt.subplots()
mfc_fig.suptitle("MFC Live Log")

# Link t-axes
#tc_ax.get_shared_x_axes().join(tc_ax, mfc_ax
# Start interactive plotting mode.
plt.ion()
plt.show(block=False)


def process_tc_log_entry(entry):
    global tc_last_comm_time
    entry = Box(zip(TC_LOG_HEADERS, entry.split(',')))
    parsed_timestamp = maya.parse(entry.timestamp)

    tc_last_comm_time = max(parsed_timestamp, tc_last_comm_time) \
        if tc_last_comm_time is not None \
        else parsed_timestamp

    reltime = (parsed_timestamp - REFERENCE_TIME).total_seconds() / 60 ** 2
    return np.array([
        reltime,
        float(entry.setpoint),
        float(entry.internal_tc),
        float(entry.external_tc)
    ])


def process_mfc_log_entry(entry):
    entry = Box(zip(MFC_LOG_HEADERS, entry.split(',')))
    parsed_timestamp = maya.parse(entry.timestamp)
    reltime = (parsed_timestamp - REFERENCE_TIME).total_seconds() / 60 ** 2
    return entry.mfc_channel, np.array([
        reltime,
        float(entry.flow),
        float(entry.setpoint),
    ])


def update_tc_plot():
    global tc_data
    try:
        new_entries = tc_log.new_entries()
        human_time_ago = humanize.naturaldelta(maya.now() - tc_last_comm_time) + " ago" \
            if tc_last_comm_time is not None \
            else "never!!!"
        print("Last communicated with the TC", human_time_ago)

        if len(new_entries) == 0:
            return

        tc_data_shard = np.array([
            process_tc_log_entry(entry)
            for entry in new_entries
        ])

        tc_data = np.vstack([tc_data, tc_data_shard])

        tc_ax.clear()

        tc_ax.plot(tc_data[:, 0], tc_data[:, 1], label=TC_DATA_HEADERS[1])
        tc_ax.plot(tc_data[:, 0], tc_data[:, 2], label=TC_DATA_HEADERS[2])
        tc_ax.plot(tc_data[:, 0], tc_data[:, 3], label=TC_DATA_HEADERS[3])

        tc_ax.legend()
        tc_ax.set_xlabel('Elapsed Time [h]')
        tc_ax.set_ylabel('Temperature [C]')

    except Exception as e:
        print("Failed to plot TC")
        print(e)


def update_mfc_plot():
    global mfc_data
    try:
        mfc_data_shards = {
        }
        for entry in mfc_log.new_entries():
            mfc_channel, shard_row = process_mfc_log_entry(entry)
            if mfc_channel not in mfc_data_shards:
                mfc_data_shards[mfc_channel] = []
            mfc_data_shards[mfc_channel].append(shard_row)

        for mfc_channel, mfc_data_shard in mfc_data_shards.items():
            assert mfc_channel in mfc_data
            mfc_data[mfc_channel] = np.vstack([
                mfc_data[mfc_channel],
                np.array(mfc_data_shard)
            ])

        mfc_ax.clear()

        # Plot the setpoints first so they're behind.
        for mfc_channel, mfc_channel_data in mfc_data.items():
            mfc_ax.plot(
                mfc_channel_data[:, 0], mfc_channel_data[:, 2], linestyle = 'dashed', label="MFC[%s] Setpoint" % mfc_channel)

        for mfc_channel, mfc_channel_data in mfc_data.items():
            mfc_ax.plot(
                mfc_channel_data[:, 0], mfc_channel_data[:, 1], label="MFC[%s] Flow" % mfc_channel)

        mfc_ax.legend()
        mfc_ax.set_xlabel('Elapsed Time [h]')
        mfc_ax.set_ylabel('Flow Rate [sccm]')

    except Exception as e:
        print("Failed to plot MFC")
        print(e)


def check_if_we_should_autoexit():
    if len(plt.get_fignums()) == 0:
        sys.exit()


# Run scheduled events with possible error of 0.1 seconds.
schedule = SynchronousSchedule(0.1, sleep=plt.pause)
schedule.every("@s").do(update_tc_plot)
schedule.every("@s").do(update_mfc_plot)
schedule.every("@s").do(check_if_we_should_autoexit)
schedule.start_blocking()
