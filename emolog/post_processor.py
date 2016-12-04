import pandas as pd
import numpy as np
import shutil
import openpyxl

import time # TEMP for profiling
import matplotlib.pyplot as plt # TEMP

tick_time_ms = 0.05     # 50 us = 0.05 ms
step_size_mm = 4.0
template_filename = "results template.xlsx"

def post_process(csv_filename):
    start = time.time()

    data = pd.read_csv(csv_filename)
    data = clean_column_names(data)
    data = remove_unneeded_columns(data)
    data = data.set_index('Ticks')
    data = only_full_cycles(data)
    data = add_time_column(data)
    data = data.join(calc_step_times_and_vel(data), how='left')
    data = reorder_columns(data)
    data = interpolate_missing_data(data)

    end = time.time()
    print("processing time: {}".format(end-start))

    start = time.time()
    save_to_excel(data, csv_filename)
    end = time.time()
    print("save to excel time: {}".format(end-start))



friendly_col_names = {} # TODO

def clean_column_names(data):
    data.columns = [remove_prefix(c, 'controller.state.') for c in data.columns]
    data.columns = [c.replace("_", " ") for c in data.columns]
    data.columns = [c[0].upper() + c[1:] for c in data.columns]
    return data


def remove_prefix(x, prefix):
    if x.startswith(prefix):
        return x[len(prefix):]
    return x


def remove_unneeded_columns(data):
    data.drop(['Sequence', 'Timestamp'], inplace=True, axis=1)
    return data


def only_full_cycles(data):
    dir_numeric = data['Actual dir'].replace(['UP', 'DOWN'], [1, -1])
    cycle_start_indexes = data[dir_numeric.diff() != 0].index
    start_i = cycle_start_indexes[1]

    # the end of the last valid cycle, is one valid index before the start of the last (incomplete) cycle
    end_i = cycle_start_indexes[-1]     # start of the last, incomplete cycle
    end_i = data.index[data.index.get_loc(cycle_start_indexes[-1]) - 1] # move one valid index before it

    series = pd.Series(data=np.arange(1, len(cycle_start_indexes)), index=cycle_start_indexes[1:])
    data['Half cycle'] = series
    data['Half cycle'].fillna(method='ffill', inplace=True)
    data = data[start_i: end_i]
    data.index -= data.first_valid_index()

    return data


def add_time_column(data):
    data['Time [ms]'] = data.index * tick_time_ms
    return data


def calc_step_times_and_vel(data):
    # TODO this assumes no tick jumps, confirm working or fix for data that includes jumps
    pos = data['Position']
    pos_change_indexes = (pos[pos.diff() != 0].index - 1).tolist()
    # pos_change_indexes = pos[pos.diff() != 0].index

    pos_change_indexes.append(pos.last_valid_index())
    step_times = np.diff(pos_change_indexes)
    ret = pd.DataFrame(data=step_times, index=pos_change_indexes[1:], columns=['Step time [ms]'])
    ret['Step time [ms]'] *= tick_time_ms
    ret = ret.reindex(index=data.index, method='backfill')
    ret['Velocity'] = step_size_mm / ret['Step time [ms]']
    return ret


def reorder_columns(data):
    all_cols = data.columns.tolist()
    first_cols = ['Time [ms]', 'Position', 'Step time [ms]', 'Velocity', 'Motor state', 'Actual dir', 'Required dir']
    rest_of_cols = [c for c in all_cols if c not in first_cols]
    data = data[first_cols + rest_of_cols]
    return data


def interpolate_missing_data(data):
    # TODO: instead of hard-coding columns to interpolate, consider analyzing where it's needed (or just everywhere?)
    cols_to_interpolate = ['Last flow rate lpm', 'Temp ext']
    data.loc[:, cols_to_interpolate] = data.loc[:, cols_to_interpolate].fillna(method='ffill')
    return data


def save_to_excel(data, csv_filename):
    #data = data[1:5000] # TEMP since it's taking so long...
    output_filename = csv_filename[:-4] + '.xlsx'
    shutil.copy(template_filename, output_filename)

    # use xlsxwriter, fast but can't use the template
    #writer = pd.ExcelWriter(output_filename, engine='xlsxwriter')

    # use openpyxl, slow but uses the template
    book = openpyxl.load_workbook(output_filename)
    writer = pd.ExcelWriter(output_filename, engine='openpyxl')
    writer.book = book
    writer.sheets = dict((ws.title, ws) for ws in book.worksheets)

    data.to_excel(excel_writer=writer, sheet_name='Data')
    writer.save()

if __name__ == '__main__':
    post_process('D:\\Projects\\Comet ME Pump Drive\\run logs\\emo_002.csv')

