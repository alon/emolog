import pandas as pd
import numpy as np
from collections import OrderedDict
from math import pi
import os

import time     # TEMP for profiling

tick_time_ms = 0.05     # 50 us = 0.05 ms
step_size_mm = 4.0
bore_diameter_mm = 26 # TODO

def post_process(csv_filename):
    start_time = time.time()

    data = pd.read_csv(csv_filename)
    data.columns = [clean_col_name(c) for c in data.columns]
    data = remove_unneeded_columns(data)
    data = data.set_index('Ticks')
    data = only_full_cycles(data)
    data = add_time_column(data)
    data = data.join(calc_step_times_and_vel(data), how='left')
    data = reorder_columns(data)
    data = interpolate_missing_data(data)
    end_time = time.time()
    print("Basic processing time: {:.2f} seconds".format(end_time - start_time))

    start_time = time.time()
    summary_stats = calc_summary_stats(data)
    half_cycle_stats = calc_half_cycle_stats(data)
    end_time = time.time()
    print("Statistics generation time: {:.2f} seconds".format(end_time - start_time))

    start_time = time.time()
    output_filename = csv_filename[:-4] + '.xlsx'
    save_to_excel(data, summary_stats, half_cycle_stats, output_filename)
    end_time = time.time()
    print("save to excel time: {:.2f} seconds".format(end_time - start_time))
    return output_filename


output_col_names = \
    {
        'Step time': 'Step Time\n[m/s]',
        'Velocity': 'Velocity\n[m/s]',
        'Motor state': 'Motor State',
        'Actual dir': 'Actual\nDirection',
        'Required dir': 'Required\nDirection',
        'Ref sensor': 'Ref\nSensor',
        'Dc bus v': 'DC Bus\n[V]',
        'Total i': 'Total I\n[A]',
        'Temp ext': 'Motor\nTemperature',
        'Last flow rate lpm': 'Flow Rate\n[LPM]',
        'Half cycle': 'Half-Cycle #'
    }
output_col_names_inv = {v: k for (k, v) in output_col_names.items()}

def std_name_to_output_name(name):
    if name in output_col_names:
        return output_col_names[name]
    return name


def output_name_to_std_name(output_name):
    if output_name in output_col_names_inv:
        return output_col_names_inv[output_name]
    return output_name



def clean_col_name(name):
    name = remove_prefix(name, 'controller.state.')
    name = name.replace("_", " ")
    name = name[0].upper() + name[1:]
    return name


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

    # the end of the last valid cycle, is one *valid index* before the start of the last (incomplete) cycle
    # note that it's not necessarily means minus 1 (with missing ticks)
    end_i = data.index[data.index.get_loc(cycle_start_indexes[-1]) - 1] # move one valid index before it

    data['Half cycle'] = pd.Series(data=np.arange(1, len(cycle_start_indexes)), index=cycle_start_indexes[1:])
    data['Half cycle'].fillna(method='ffill', inplace=True)
    data = data.loc[start_i: end_i]
    data.index -= data.first_valid_index()  # reindex starting from ticks = 0

    return data


def add_time_column(data):
    data['Time'] = data.index * tick_time_ms
    return data


def calc_step_times_and_vel(data):
    # TODO this assumes no tick jumps, confirm working or fix for data that includes jumps
    pos = data['Position']
    pos_change_indexes = (pos[pos.diff() != 0].index - 1).tolist()
    # pos_change_indexes = pos[pos.diff() != 0].index

    pos_change_indexes.append(pos.last_valid_index())
    step_times = np.diff(pos_change_indexes)
    ret = pd.DataFrame(data=step_times, index=pos_change_indexes[1:], columns=['Step time'])
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


def interpolate_missing_data(data):
    # TODO: instead of hard-coding columns to interpolate, consider analyzing where it's needed (or just everywhere?)
    cols_to_interpolate = ['Last flow rate lpm', 'Temp ext']
    data.loc[:, cols_to_interpolate] = data.loc[:, cols_to_interpolate].fillna(method='ffill')
    return data


def calc_summary_stats(data):
    res = OrderedDict()
    res['Total Time [ms]'] = (data.last_valid_index() - data.first_valid_index() + 1) * tick_time_ms
    res['Number of Samples'] = len(data)
    index_diff = np.diff(data.index)
    res['Lost Samples'] = sum(index_diff) - len(index_diff)
    res['Number of Half-Cycles'] = data['Half cycle'].max()

    res['UP Travel Time [ms]'] = data['Actual dir'].value_counts()['UP'] * tick_time_ms
    res['DOWN Travel Time [ms]'] = data['Actual dir'].value_counts()['DOWN'] * tick_time_ms
    res['UP Travel [% of total]'] = res['UP Travel Time [ms]'] / (res['UP Travel Time [ms]'] + res['DOWN Travel Time [ms]'])
    res['DOWN Travel [% of total]'] = res['DOWN Travel Time [ms]'] / (res['UP Travel Time [ms]'] + res['DOWN Travel Time [ms]'])

    top_positions = data[data['Actual dir'] == 'UP'].groupby('Half cycle')['Position'].max()
    bottom_positions = data[data['Actual dir'] == 'DOWN'].groupby('Half cycle')['Position'].min()
    res['Top Position Average [steps]'] = top_positions.mean()
    res['Top Position Std. Dev. [steps]'] = top_positions.std()
    res['Bottom Position Average [steps]'] = bottom_positions.mean()
    res['Bottom Position Std. Dev. [steps]'] = bottom_positions.std()
    res['Travel Range Average [steps]'] = res['Top Position Average [steps]'] - res['Bottom Position Average [steps]']
    res['Travel Range Average [mm]'] = res['Travel Range Average [steps]'] * step_size_mm

    res['Coasting Time [% of total time]'] = data['Motor state'].value_counts(normalize=True)['M_STATE_ALL_OFF']

    res['Average Current [A]'] = data['Total i'].mean()
    res['Average Current going UP [A]'] = data[data['Actual dir'] == 'UP']['Total i'].mean()
    res['Average Current going DOWN [A]'] = data[data['Actual dir'] == 'DOWN']['Total i'].mean()
    res['Average Current Excluding Coasting [A]'] = data[data['Motor state'] != 'M_STATE_ALL_OFF']['Total i'].mean()
    res['Average Current During Coasting [A]'] = data[data['Motor state'] == 'M_STATE_ALL_OFF']['Total i'].mean()

    return res


def calc_half_cycle_stats(data):
    """
    Statistics to calculate:

    Half Cycle #
    Direction
    Time [ms]
    Min. Position [steps]
    Max. Position [steps]
    Travel Range [steps]
    Average Velocity [m/s]
    Middle Section Velocity [m/s]
    Flow Rate [LPM]
    Coasting Duration [ms]
    Coasting Distance [steps]
    Coasting Percentage [%]
    Average Current [A]
    Average Current Excluding Coasting [A]
    Average Current During Coasting [A]
    """
    res = []
    for (hc_num, hc) in data.groupby('Half cycle'):
        hc_stats = OrderedDict()
        hc_stats['Half Cycle #'] = hc_num
        assert(len(hc['Actual dir'].unique()) == 1)     # a half-cycle should have a constant 'Actual dir'
        hc_stats['Direction'] = hc['Actual dir'].iloc[0]
        hc_stats['Time [ms]'] = (hc.last_valid_index() - hc.first_valid_index() + 1) * tick_time_ms
        hc_stats['Min. Position [steps]'] = hc['Position'].min()
        hc_stats['Max. Position [steps]'] = hc['Position'].max()
        hc_stats['Travel Range'] = hc_stats['Max. Position [steps]'] - hc_stats['Min. Position [steps]'] + 1
        hc_stats['Average Velocity [m/s]'] = hc_stats['Travel Range'] * step_size_mm / hc_stats['Time [ms]']
        hc_stats['Middle Section Velocity [m/s]'] = 'TODO' # TODO
        water_displacement_mm3 = pi * (bore_diameter_mm / 2.0)**2 * hc_stats['Travel Range'] * step_size_mm
        hc_stats['Flow Rate [LPM]'] = water_displacement_mm3 / 1e6 / (hc_stats['Time [ms]'] / 1000.0 / 60.0)
        coasting = hc[hc['Motor state'] == 'M_STATE_ALL_OFF']
        hc_stats['Coasting Distance [steps]'] = coasting['Position'].max() - coasting['Position'].min()
        hc_stats['Coasting Duration [ms]'] = len(coasting) * tick_time_ms
        hc_stats['Coasting Duration [% of half-cycle]'] = hc_stats['Coasting Duration [ms]'] / hc_stats['Time [ms]']
        hc_stats['Average Current [A]'] = hc['Total i'].mean()
        hc_stats['Average Current Excluding Coasting [A]'] = hc[hc['Motor state'] != 'M_STATE_ALL_OFF']['Total i'].mean()
        hc_stats['Average Current During Coasting [A]'] = coasting['Total i'].mean()
        res.append(hc_stats)
    return res


def save_to_excel(data, summary_stats, half_cycle_stats, output_filename):
    #data = data[1:5000] # TEMP since it's taking so long...
    data.columns = [std_name_to_output_name(c) for c in data.columns]

    writer = pd.ExcelWriter(output_filename, engine='xlsxwriter')
    data.to_excel(excel_writer=writer, sheet_name='Data', header=False, startrow=1)
    workbook = writer.book
    data_sheet = writer.sheets['Data']

    set_header(workbook, data_sheet, data.columns.tolist())
    set_column_formats(workbook, data_sheet, data.columns.tolist())

    add_graphs(workbook, data)
    add_summary_sheet(workbook, summary_stats)
    add_half_cycles_sheet(workbook, half_cycle_stats)

    writer.save()


def set_header(wb, ws, cols):
    header_format = wb.add_format({'text_wrap': True, 'bold': True})
    header_format.set_text_wrap()
    ws.set_row(row=0, height=30, cell_format=header_format)   # header row has different format
    for (col_num, col_name) in enumerate(cols):
        ws.write(0, col_num + 1, col_name)


def set_column_formats(wb, ws, cols):
    frac_format = wb.add_format({'num_format': '0.000'})
    time_format = wb.add_format({'num_format': '0.00'})
    general_format = wb.add_format()

    col_formats = {
        'Time':               (8, time_format),
        'Position':           (8, general_format),
        'Step time':          (9, time_format),
        'Velocity':           (8, frac_format),
        'Motor state':        (16, general_format),
        'Actual dir':         (9, general_format),
        'Required dir':       (9, general_format),
        'Ref sensor':         (6, general_format),
        'Dc bus v':           (7, frac_format),
        'Total i':            (7, frac_format),
        'Temp ext':           (12, frac_format),
        'Last flow rate lpm': (9, frac_format),
        'Half cycle':         (11, general_format)
    }
    col_formats = {(std_name_to_output_name(c)): f for (c, f) in col_formats.items()}

    for col in cols:
        if col in col_formats:
            col_index = cols.index(col) + 1     # +1 since column A is the index (Ticks)
            ws.set_column(col_index, col_index, col_formats[col][0], col_formats[col][1])


def add_graphs(wb, data):
    time_col = 1
    min_row = 1
    max_row = data.last_valid_index() + 1
    short_max_row = 500.0 / tick_time_ms

    pos_col = data.columns.tolist().index(std_name_to_output_name('Position')) + 1
    vel_col = data.columns.tolist().index(std_name_to_output_name('Velocity')) + 1
    current_col = data.columns.tolist().index(std_name_to_output_name('Total i')) + 1

    x_axis = {'min_row': min_row,
              'max_row': max_row,
              'col': time_col}

    y_axes = []
    y_axes.append({'name': 'Position',
                   'min_row': min_row,
                   'max_row': max_row,
                   'col': pos_col,
                   'secondary': False,
                   'line_width': 1
                   })

    y_axes.append({'name': 'Velocity',
                   'min_row': min_row,
                   'max_row': max_row,
                   'col': vel_col,
                   'secondary': True,
                   'line_width': 1
                   })


    add_scatter_graph(wb, 'Data', x_axis, y_axes, 'Pos & Vel - Full')

    # short time graph
    x_axis['max_row'] = short_max_row
    for y_axis in y_axes:
        y_axis['max_row'] = short_max_row
        y_axis['line_width'] = 1.5
    y_axes.append({'name': 'Current',
                   'min_row': min_row,
                   'max_row': short_max_row,
                   'col': current_col,
                   'secondary': True,
                   'line_width': 1
                   })

    add_scatter_graph(wb, 'Data', x_axis, y_axes, 'Pos, Vel, Current - 0.5s')


def add_scatter_graph(wb, data_sheet_name, x_axis, y_axes, chart_sheet_name):
    sheet = wb.add_chartsheet()
    chart = wb.add_chart({'type': 'scatter', 'subtype': 'straight'})
    for y_axis in y_axes:
        chart.add_series({
            'name': y_axis['name'],
            'categories':   [data_sheet_name, x_axis['min_row'], x_axis['col'], x_axis['max_row'], x_axis['col']],
            'values':       [data_sheet_name, y_axis['min_row'], y_axis['col'], y_axis['max_row'], y_axis['col']],
            'y2_axis':      y_axis['secondary'],
            'line':         {'width': y_axis['line_width']}
        })
    chart.set_x_axis({'label_position': 'low',
                      'min': 0,
                      'max': x_axis['max_row'] * tick_time_ms})
    sheet.set_chart(chart)
    sheet.set_zoom(145)
    sheet.name = chart_sheet_name


def add_summary_sheet(wb, summary_stats):
    sheet = wb.add_worksheet('Analysis Summary')
    row = 0
    for field_name, field_value in summary_stats.items():
        sheet.write(row, 0, field_name)
        sheet.write(row, 1, field_value)
        row += 1


def add_half_cycles_sheet(wb, half_cycle_stats):
    sheet = wb.add_worksheet('Half-Cycles Analysis')

    # write header row
    col = 0
    for field_name, field_value in half_cycle_stats[0].items():
        sheet.write(0, col, field_name)
        col += 1

    row = 1
    for hc_stat in half_cycle_stats:
        col = 0
        for field_name, field_value in hc_stat.items():
            sheet.write(row, col, field_value)
            col += 1
        row += 1


if __name__ == '__main__':
    input_filename = 'solar_panels_emo_012.csv'
    out_filename = post_process(input_filename)
    os.startfile(out_filename)

