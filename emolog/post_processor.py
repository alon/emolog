import pandas as pd
import numpy as np
import shutil
import openpyxl

import time # TEMP for profiling
import matplotlib.pyplot as plt # TEMP

tick_time_ms = 0.05     # 50 us = 0.05 ms
step_size_mm = 4.0
template_filename = "results template.xlsx"
output_filename = "example output.xlsx"

def post_process(csv_file):
    start = time.time()

    data = pd.read_csv(csv_file)
    data = clean_column_names(data)
    data = parse_enum_columns(data)
    data = remove_unneeded_columns(data)
    data = data.set_index('Ticks')
    data = only_full_cycles(data)
    data = add_time_column(data)
    data = data.join(calc_step_times_and_vel(data), how ='left')
    data = reorder_columns(data)

    end = time.time()
    print("processing time: {}".format(end-start))

    start = time.time()
    save_to_excel(data)
    end = time.time()
    print("save to excel time: {}".format(end-start))



def clean_column_names(data):
    data.columns = [remove_prefix(c, 'controller.state.') for c in data.columns]
    data.columns = [c.replace("_", " ") for c in data.columns]
    data.columns = [c[0].upper() + c[1:] for c in data.columns]
    return data


def remove_prefix(x, prefix):
    if x.startswith(prefix):
        return x[len(prefix):]
    return x


def parse_enum_columns(data):
    # TODO: to be replaced with temp enum parser and later with emotool full enum parser
    data.loc[data['Required dir'] == 255, 'Required dir'] = -1
    data.loc[data['Actual dir'] == 255, 'Actual dir'] = -1
    return data


def remove_unneeded_columns(data):
    data.drop(['Sequence', 'Timestamp'], inplace=True, axis=1)
    return data


def only_full_cycles(data):
    start_i = data.first_valid_index()
    end_i = data.last_valid_index()
    first_dir = data['Actual dir'][start_i]
    last_dir = data['Actual dir'][end_i]
    while data['Actual dir'][start_i] == first_dir:
        start_i += 1
    while data['Actual dir'][end_i] == last_dir:
        end_i -= 1

    data = data[start_i: end_i]
    data.index -= data.first_valid_index()
    return data


def add_time_column(data):
    data['Time'] = data.index * tick_time_ms
    return data


def calc_step_times_and_vel(data):
    # TODO this assumes no tick jumps, confirm working or fix for data that includes jumps
    pos = data['Position']
    pos_change_indexes = (pos[pos.diff() != 0].index - 1).tolist()
    pos_change_indexes.append(pos.last_valid_index())
    step_times = np.diff(pos_change_indexes)
    ret = pd.DataFrame(data = step_times, index = pos_change_indexes[1:], columns = ['Step time'])
    ret['Step time'] *= tick_time_ms
    ret = ret.reindex(index=data.index, method='backfill')
    ret['Velocity'] = step_size_mm / ret['Step time']
    return ret


def reorder_columns(data):
    all_cols = data.columns.tolist()
    first_cols = ['Time', 'Position', 'Step time', 'Velocity', 'Motor state', 'Actual dir', 'Required dir']
    rest_of_cols = [c for c in all_cols if c not in first_cols]
    data = data[first_cols + rest_of_cols]
    return data


def save_to_excel(data):
    data = data[0:5000] # TEMP since it's taking so long...
    shutil.copy(template_filename, output_filename)

    book = openpyxl.load_workbook(output_filename)
    writer = pd.ExcelWriter(output_filename, engine='openpyxl')
    writer.book = book
    writer.sheets = dict((ws.title, ws) for ws in book.worksheets)

    data.to_excel(excel_writer=writer, sheet_name='Data')

    writer.save()

if __name__ == '__main__':
    post_process("motor_run_example.csv")

