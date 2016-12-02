import pandas as pd
import numpy as np

import matplotlib.pyplot as plt

tick_time_ms = 0.05     # 50 us = 0.05 ms
step_size_mm = 4.0

def post_process(csv_file):
    data = pd.read_csv(csv_file)
    data = cleanup_data(data)
    data = only_full_cycles(data)
    data = data.join(calc_step_times_and_vel(data), how ='left')

    ax = plt.gca()
    ax2 = ax.twinx()
    ax.plot(data['position'], 'b')
    ax2.plot(data['velocity'], 'r')
    ax2.set_ylim(ymin = 0, ymax = 1.0)
    plt.show()

    pass

def cleanup_data(data):
    data.columns = [remove_prefix(c, 'controller.state.') for c in data.columns]

    data.loc[data['required_dir'] == 255, 'required_dir'] = -1
    data.loc[data['actual_dir'] == 255, 'actual_dir'] = -1

    data.drop(['sequence', 'timestamp'], inplace = True, axis = 1)

    data['time'] = data['ticks'] * tick_time_ms

    return data


def remove_prefix(x, prefix):
    if x.startswith(prefix):
        return x[len(prefix):]
    return x


def only_full_cycles(data):
    start_i = 0
    end_i = data.last_valid_index()
    first_dir = data['actual_dir'][start_i]
    last_dir = data['actual_dir'][end_i]
    while data['actual_dir'][start_i] == first_dir:
        start_i += 1
    while data['actual_dir'][end_i] == last_dir:
        end_i -= 1
    return data[start_i : end_i]


def calc_step_times_and_vel(data):
    # TODO this assumes no tick jumps, confirm working or fix for data that includes jumps
    pos = data['position']
    pos_change_indexes = (pos[pos.diff() != 0].index - 1).tolist()
    pos_change_indexes.append(pos.last_valid_index())
    step_times = np.diff(pos_change_indexes)
    ret = pd.DataFrame(data = step_times, index = pos_change_indexes[1:], columns = ['step times'])
    ret['step times'] *= tick_time_ms
    ret = ret.reindex(index=data.index, method='backfill')
    ret['velocity'] = step_size_mm / ret['step times']
    return ret

if __name__ == '__main__':
    post_process("motor_run_example.csv")

