import matplotlib.pyplot as plt
import pandas as pd
import maya
import datetime
import sys

from abc import ABC
from abc import abstractmethod
from attr import attr
from attr import attrs
from math import exp
from tzolkin import SynchronousSchedule

plt.style.use('monitor.mplstyle')
datestring = maya.now().datetime().strftime("%m-%d-%y")

TC_LOG_FILENAME = '%s-TC.csv' % datestring
MFC_LOG_FILENAME = '%s-MFC.csv' % datestring

tc_fig, tc_ax = plt.subplots()
tc_fig.suptitle("TC Live Log")

mfc_fig, mfc_ax = plt.subplots()
mfc_fig.suptitle("MFC Live Log")

plt.ion()
plt.show(block=False)

def calc_delta_hrs(df,column_header):
    df['Time_in_s'] = pd.to_datetime(df[column_header], unit='s')
    df['delta_t'] = df.loc[:,'Time_in_s']-df.loc[0,'Time_in_s']
    df['elapsed_hours'] = df['delta_t'].dt.total_seconds()/3600
    return

def plot_logs():
    try:
        tc_ax.clear()
        with open(TC_LOG_FILENAME) as tc_log_f:
            tc_df = pd.read_csv(
                tc_log_f, names=['Time', 'Setpoint', 'Actual T(1)', 'Actual T(2)'], parse_dates=['Time'])
            calc_delta_hrs(tc_df, 'Time')
            last_log_time = (tc_df['Time_in_s'].iloc[-1]-datetime.datetime(1970,1,1)).total_seconds()
            print('Time since last update', maya.now()-maya.MayaDT(last_log_time))
            tc_df.plot(x='elapsed_hours', y=1, ax=tc_ax)
            tc_df.plot(x='elapsed_hours', y=2, ax=tc_ax)
            tc_df.plot(x='elapsed_hours', y=3, ax=tc_ax)
            tc_ax.legend(['Setpoint', 'External Control TC', 'Internal Monitor TC'])
            tc_ax.set_xlabel('Elapsed Time [h]')
            tc_ax.set_ylabel('Temperature [C]')
    except Exception as e:
        print("Failed to plot TC")
        print(e)

    try:
        mfc_ax.clear()
        with open(MFC_LOG_FILENAME) as mfc_log_f:
            mfc_df = pd.read_csv(
                mfc_log_f, names=['Time', 'MFC','Abs Pressure','Temperature','Volumetric Flow','Standard Mass Flow','Setpoint', 'Gas Type'], parse_dates=['Time'])
            calc_delta_hrs(mfc_df, 'Time')
            mfc_A_df = mfc_df[mfc_df['MFC'] == 'A']
            mfc_B_df = mfc_df[mfc_df['MFC'] == 'B']
            mfc_C_df = mfc_df[mfc_df['MFC'] == 'C']

            mfc_A_df.plot(x = 'elapsed_hours', y = 'Standard Mass Flow', ax = mfc_ax)
            mfc_B_df.plot(x = 'elapsed_hours', y = 'Standard Mass Flow', ax = mfc_ax)
            mfc_C_df.plot(x = 'elapsed_hours', y = 'Standard Mass Flow', ax = mfc_ax)

            mfc_ax.legend(['MFC_A', 'MFC_B', 'MFC_C'])
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
schedule.every("@s").do(plot_logs)
schedule.every("@s").do(check_if_we_should_autoexit)

schedule.start_blocking()
