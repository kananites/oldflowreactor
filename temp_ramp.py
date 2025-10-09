import matplotlib.pyplot as plt
import numpy as np

from attr import attr
from attr import attrs
from typing import List

DEG_C = 1

SECOND = 1/60
MINUTE = 1
HOUR = 60


MAX_ERROR_DURING_RAMP = 0.1 * DEG_C


def flex_arange(start, stop, step):
    if start > stop:
        return flex_arange(stop, start, step)[::-1]

    xs = list(np.arange(start, stop, step))
    if xs[-1] != stop:
        xs.append(stop)

    return xs


@attrs
class TempRamp:
    temps: List[float] = attr()  # In deg C
    hold_times: List[float] = attr()  # In minutes
    ramp_rates: List[float] = attr()  # In deg C / minutes

    def ramp_points(self):
        curr_time = 0

        times = []
        temps = []

        for start_temp, hold_time, ramp_rate, end_temp in zip(
                self.temps,
                self.hold_times,
                self.ramp_rates,
                self.temps[1:],
        ):
            times.append(curr_time)
            temps.append(start_temp)

            if hold_time > 0:
                curr_time += hold_time

                times.append(curr_time)
                temps.append(start_temp)

            # Now the ramp
            if ramp_rate > 0:
                curr_time += abs(end_temp - start_temp) / ramp_rate

        times.append(curr_time)
        temps.append(self.temps[-1])

        return times, temps

    def control_points(self):
        times, temps = self.ramp_points()

        control_times = []
        control_temps = []

        for time0, time1, temp0, temp1 in zip(
            times,
            times[1:],
            temps,
            temps[1:],
        ):
            if time0 == time1:
                control_times.append(time1)
                control_temps.append(temp1)
                continue

            if temp0 == temp1:
                continue

            ramp_temps = flex_arange(temp0, temp1, step=MAX_ERROR_DURING_RAMP)

            if temp0 < temp1:
                ramp_times = np.interp(
                    ramp_temps, [temp0, temp1], [time0, time1])
            else:
                ramp_times = np.interp(ramp_temps, [temp1, temp0], [
                                       time0, time1])[::-1]

            control_times.extend(ramp_times)
            control_temps.extend(ramp_temps)

        return control_times, control_temps


if __name__ == '__main__':
    HOLD_TIME = 4 * HOUR
    RAMP_RATE = 5 * DEG_C / MINUTE
    temp_ramp = TempRamp(
        [25, 300,     325,     350,     375,     400,
            425,     450,     475,     500,    350,   25],
        [0] + [HOLD_TIME] * 10,
        [RAMP_RATE] * 10 + [0],
    )

    plt.plot(*temp_ramp.ramp_points())
    plt.scatter(*temp_ramp.control_points(), marker='o', color='red')

    plt.show()
