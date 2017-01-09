import sys
from collections import OrderedDict
from math import pi, isnan
import os

import pandas as pd
import numpy as np

import time     # for profiling

tick_time_ms = 0.05     # 50 us = 0.05 ms
step_size_mm = 4.0
bore_diameter_mm = 26   # TODO is this correct?

cruising_after_num_steps = 5


def post_process(csv_filename):
    start_time = time.time()
    data = pd.read_csv(csv_filename)
    data.columns = [clean_col_name(c) for c in data.columns]
    data = remove_unneeded_columns(data)
    data = data.set_index('Ticks')
    data = partition_to_half_cycles(data)
    data = add_time_column(data)
    data = data.join(calc_step_times_and_vel(data), how='left')
    data = mark_cruising(data)
    data = reorder_columns(data)
    data = interpolate_missing_data(data)
    end_time = time.time()
    print("Basic processing time: {:.2f} seconds".format(end_time - start_time))

    start_time = time.time()
    half_cycle_stats = calc_half_cycle_stats(data)
    half_cycle_summary = calc_half_cycle_summary(half_cycle_stats)
    motor_state_stats = calc_motor_state_stats(data)
    position_stats = calc_position_stats(data)
    summary_stats = calc_summary_stats(data, half_cycle_stats)
    end_time = time.time()
    print("Statistics generation time: {:.2f} seconds".format(end_time - start_time))

    start_time = time.time()
    output_filename = csv_filename[:-4] + '.xlsx'
    save_to_excel(data, summary_stats, half_cycle_stats, half_cycle_summary, motor_state_stats, position_stats, output_filename)
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
        'Half cycle': 'Half-Cycle #',
        'Duty cycle': 'Duty Cycle'
    }
output_col_names_inv = {v: k for (k, v) in output_col_names.items()}


data_col_formats = \
    {
        'Time': {'width': 8, 'format': 'time'},
        'Position': {'width': 8, 'format': 'general'},
        'Step time': {'width': 9, 'format': 'time'},
        'Velocity': {'width': 8, 'format': 'frac'},
        'Motor state': {'width': 17, 'format': 'general'},
        'Actual dir': {'width': 9, 'format': 'general'},
        'Required dir': {'width': 9, 'format': 'general'},
        'Ref sensor': {'width': 6, 'format': 'general'},
        'Dc bus v': {'width': 7, 'format': 'frac'},
        'Total i': {'width': 7, 'format': 'frac'},
        'Temp ext': {'width': 12, 'format': 'frac'},
        'Last flow rate lpm': {'width': 9, 'format': 'frac'},
        'Half cycle': {'width': 11, 'format': 'general'},
        'Duty cycle': {'width': 8, 'format': 'percent'},
    }


half_cycle_col_formats = \
    {
        'Half-Cycle': {'width': 6, 'format': 'general'},
        'Direction': {'width': 15, 'format': 'general'},
        'Time [ms]': {'width': 7, 'format': 'time'},
        'Min. Position [steps]': {'width': 8, 'format': 'general'},
        'Max. Position [steps]': {'width': 8, 'format': 'general'},
        'Travel Range [steps]': {'width': 7, 'format': 'general'},
        'Average Velocity [m/s]': {'width': 8, 'format': 'frac'},
        'Cruising Velocity [m/s]': {'width': 8, 'format': 'frac'},
        'Flow Rate [LPM]': {'width': 8, 'format': 'frac'},
        'Coasting Distance [steps]': {'width': 8, 'format': 'general'},
        'Coasting Duration [ms]': {'width': 8, 'format': 'time'},
        'Coasting Duration [%]': {'width': 8, 'format': 'percent'},
        'Average Current [A]': {'width': 8, 'format': 'frac'},
        'Cruising Current [A]': {'width': 8, 'format': 'frac'},
        'Coasting Current [A]': {'width': 8, 'format': 'frac'},
        'Peak Current [A]': {'width': 8, 'format': 'frac'}
    }


motor_states_col_formats = \
    {
        'Direction': {'width': 9, 'format': 'general'},
        'State': {'width': 17, 'format': 'general'},
        'Phases State (A,B,C)': {'width': 7, 'format': 'general'},
        'Average Velocity [m/s]': {'width': 8, 'format': 'frac'},
        'Velocity Std. Dev [m/s]': {'width': 8, 'format': 'frac'},
        'Average Current [A]': {'width': 8, 'format': 'frac'},
        'Current Std. Dev [A]': {'width': 8, 'format': 'frac'}
    }


position_stats_col_formats = \
    {
        'Direction': {'width': 9, 'format': 'general'},
        'Position': {'width': 7, 'format': 'general'},
        'Average Velocity [m/s]': {'width': 8, 'format': 'frac'},
        'Velocity Std. Dev [m/s]': {'width': 8, 'format': 'frac'},
        'Average Current [A]': {'width': 8, 'format': 'frac'},
        'Current Std. Dev [A]': {'width': 8, 'format': 'frac'}
    }


motor_state_to_phases = {
    'M_STATE_S0': '(+, -, 0)',
    'M_STATE_S1': '(+, 0, -)',
    'M_STATE_S2': '(0, +, -)',
    'M_STATE_S3': '(-, +, 0)',
    'M_STATE_S4': '(-, 0, +)',
    'M_STATE_S5': '(0, -, +)',
    'M_STATE_ALL_OFF': '(0, 0, 0)'
}


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
    name = remove_prefix(name, 'duty_cycle.')
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


def partition_to_half_cycles(data):
    dir_numeric = data['Required dir'].replace(['UP', 'DOWN'], [1, -1])
    cycle_start_indexes = data[dir_numeric.diff() != 0].index

    # no direction changes at all: do not truncate data. all data is the same half-cycle.
    if len(cycle_start_indexes) <= 1:
        data['Half cycle'] = pd.Series(data=[1] * len(data))
        data.index -= data.first_valid_index()  # reindex starting from ticks = 0
        return data

    # one direction change: probably two incomplete cycles
    if len(cycle_start_indexes) == 2:
        data['Half cycle'] = pd.Series(data=np.arange(1, len(cycle_start_indexes) + 1), index=cycle_start_indexes)
        data['Half cycle'].fillna(method='ffill', inplace=True)
        data.index -= data.first_valid_index()  # reindex starting from ticks = 0
        return data

    start_i = cycle_start_indexes[1]
    # the end of the last valid cycle, is one *valid index* before the start of the last (incomplete) cycle
    # note that it's not necessarily means minus 1 (with missing ticks)
    end_i = data.index[data.index.get_loc(cycle_start_indexes[-1]) - 1]  # move one valid index before it

    data['Half cycle'] = pd.Series(data=np.arange(1, len(cycle_start_indexes)), index=cycle_start_indexes[1:])
    data['Half cycle'].fillna(method='ffill', inplace=True)
    data = data.loc[start_i: end_i]
    data.index -= data.first_valid_index()  # reindex starting from ticks = 0

    return data


def add_time_column(data):
    data['Time'] = data.index * tick_time_ms
    return data


def calc_step_times_and_vel(data):
    # this assumes no lost samples. Output is incorrect when samples are missing.
    pos = data['Position']
    pos_change_indexes = (pos[pos.diff() != 0].index - 1).tolist()

    pos_change_indexes.append(pos.last_valid_index())
    step_times = np.diff(pos_change_indexes)
    ret = pd.DataFrame(data=step_times, index=pos_change_indexes[1:], columns=['Step time'])
    ret['Step time'] *= tick_time_ms
    ret = ret.reindex(index=data.index, method='backfill')
    ret['Velocity'] = step_size_mm / ret['Step time']
    return ret


def mark_cruising(data):
    data['Cruising'] = True
    # the coasting phase should not be considered cruising
    data.loc[data['Motor state'] == 'M_STATE_ALL_OFF', 'Cruising'] = False
    # The acceleration phase should not be considered cruising
    for (hc_num, hc) in data.groupby('Half cycle'):
        first_pos = hc.iloc[0]['Position']
        startup_indexes = np.abs(hc['Position'] - first_pos) < cruising_after_num_steps
        startup_indexes = startup_indexes.reindex(data.index, fill_value=False)
        data.loc[startup_indexes, 'Cruising'] = False
    return data


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


def calc_summary_stats(data, hc_stats):
    """
    add:
    'DC Bus Voltage Average [V]'
    'DC Bus Voltage Min. [V]'
    'DC Bus Voltage Max. [V]'
    'DC Bus Voltage Std. Dev. [V]'

    'Samples before cropping'
    'Samples after cropping' (which is what's displayed now)
    'Samples cropped'

    temperature (avg, std). when we can transmit all temperatures (incl. board), make this another tab.

    peak current.
    current during cruising.
    """
    res = OrderedDict()
    res['Total Time [ms]'] = (data.last_valid_index() - data.first_valid_index() + 1) * tick_time_ms
    res['Number of Samples'] = len(data)
    index_diff = np.diff(data.index)
    res['Lost Samples'] = sum(index_diff) - len(index_diff)
    res['Lost samples [%]'] = res['Lost Samples'] / res['Number of Samples']
    res['Number of Half-Cycles'] = data['Half cycle'].max()
    res['separator 1'] = ''

    res['Average Current [A]'] = data['Total i'].mean()
    res['Average Current going UP [A]'] = data[data['Actual dir'] == 'UP']['Total i'].mean()
    res['Average Current going DOWN [A]'] = data[data['Actual dir'] == 'DOWN']['Total i'].mean()
    res['Cruising Current [A]'] = data[data['Cruising'] == True]['Total i'].mean()
    res['Coasting Current [A]'] = data[data['Motor state'] == 'M_STATE_ALL_OFF']['Total i'].mean()

    return res


def calc_half_cycle_stats(data):
    res = []
    for (hc_num, hc) in data.groupby('Half cycle'):
        hc_stats = OrderedDict()
        hc_stats['Half-Cycle'] = hc_num
        assert(len(hc['Required dir'].unique()) == 1)     # a half-cycle should have a constant 'Required dir'
        hc_stats['Direction'] = hc['Required dir'].iloc[0]
        hc_stats['Time [ms]'] = (hc.last_valid_index() - hc.first_valid_index() + 1) * tick_time_ms
        hc_stats['Min. Position [steps]'] = hc['Position'].min()
        hc_stats['Max. Position [steps]'] = hc['Position'].max()
        hc_stats['Travel Range [steps]'] = hc_stats['Max. Position [steps]'] - hc_stats['Min. Position [steps]']
        hc_stats['Average Velocity [m/s]'] = hc_stats['Travel Range [steps]'] * step_size_mm / hc_stats['Time [ms]']
        cruising = hc[hc['Cruising'] == True]
        cruising_range = cruising['Position'].max() - cruising['Position'].min()
        cruising_time = (cruising.last_valid_index() - cruising.first_valid_index() + 1) * tick_time_ms
        hc_stats['Cruising Velocity [m/s]'] = cruising_range * step_size_mm / cruising_time
        water_displacement_mm3 = pi * (bore_diameter_mm / 2.0)**2 * hc_stats['Travel Range [steps]'] * step_size_mm
        hc_stats['Flow Rate [LPM]'] = water_displacement_mm3 / 1e6 / (hc_stats['Time [ms]'] / 1000.0 / 60.0)
        coasting = hc[hc['Motor state'] == 'M_STATE_ALL_OFF']
        if len(coasting) > 0:
            hc_stats['Coasting Distance [steps]'] = coasting['Position'].max() - coasting['Position'].min()
            hc_stats['Coasting Duration [ms]'] = len(coasting) * tick_time_ms
            hc_stats['Coasting Duration [%]'] = hc_stats['Coasting Duration [ms]'] / hc_stats['Time [ms]']
        else:
            hc_stats['Coasting Distance [steps]'] = 'N/A'
            hc_stats['Coasting Duration [ms]'] = 'N/A'
            hc_stats['Coasting Duration [%]'] = 'N/A'
        hc_stats['Average Current [A]'] = hc['Total i'].mean()
        hc_stats['Cruising Current [A]'] = hc[hc['Cruising'] == True]['Total i'].mean()
        if len(coasting) > 0:
            hc_stats['Coasting Current [A]'] = coasting['Total i'].mean()
        else:
            hc_stats['Coasting Current [A]'] = 'N/A'
        hc_stats['Peak Current [A]'] = hc['Total i'].max()

        res.append(hc_stats)
    return pd.DataFrame(res)


def calc_half_cycle_summary(hc_stats):
    summary = hc_stats.groupby('Direction').mean()
    summary = summary.reindex(columns=hc_stats.columns)
    summary.loc['ALL'] = hc_stats.mean()
    summary['Direction'] = summary.index + ' Averages'
    summary.drop(['Half-Cycle'], inplace=True, axis=1)
    summary = summary.fillna('N/A')
    return summary


def calc_motor_state_stats(data):
    res = []
    for ((direction, state), data_in_state) in data.groupby(['Required dir', 'Motor state']):
        stats = OrderedDict()
        if state != 'M_STATE_ALL_OFF':
            filt_data = data_in_state[data_in_state['Cruising'] == True]
        else:
            filt_data = data_in_state

        stats['Direction'] = direction
        stats['State'] = state
        stats['Phases State (A,B,C)'] = motor_state_to_phases[state]
        stats['Average Velocity [m/s]'] = filt_data['Velocity'].mean()
        stats['Velocity Std. Dev [m/s]'] = filt_data['Velocity'].std()

        stats['Average Current [A]'] = filt_data['Total i'].mean()
        stats['Current Std. Dev [A]'] = filt_data['Total i'].std()
        res.append(stats)
    return pd.DataFrame(res)


def calc_position_stats(data):
    res = []
    for ((direction, pos), data_in_pos) in data.groupby(['Required dir', 'Position']):
        stats = OrderedDict()
        stats['Direction'] = direction
        stats['Position'] = pos
        stats['Average Velocity [m/s]'] = data_in_pos['Velocity'].mean()
        stats['Velocity Std. Dev [m/s]'] = data_in_pos['Velocity'].std()

        stats['Average Current [A]'] = data_in_pos['Total i'].mean()
        stats['Current Std. Dev [A]'] = data_in_pos['Total i'].std()
        res.append(stats)
    return pd.DataFrame(res)


def save_to_excel(data, summary_stats, half_cycle_stats, half_cycle_summary, motor_state_stats, position_stats, output_filename):
    # data = data[1:5000]     # TEMP since it's taking so long...
    writer = pd.ExcelWriter(output_filename, engine='xlsxwriter')
    workbook = writer.book
    wb_formats = add_workbook_formats(workbook)

    add_data_sheet(writer, data, wb_formats)
    add_graphs(workbook, data)
    add_summary_sheet(workbook, summary_stats, wb_formats)
    add_half_cycles_sheet(writer, half_cycle_stats, half_cycle_summary, wb_formats)
    add_motor_state_sheet(writer, motor_state_stats, wb_formats)
    add_positions_sheet(writer, position_stats, wb_formats)
    writer.save()


def add_workbook_formats(wb):
    formats = \
        {
            'frac': wb.add_format({'num_format': '0.000'}),
            'time': wb.add_format({'num_format': '0.00'}),
            'percent': wb.add_format({'num_format': '0.00%'}),
            'general': wb.add_format(),
            'header': wb.add_format({'text_wrap': True, 'bold': True}),
            'title': wb.add_format({'font_size': 14, 'bold': True})
        }
    return formats


def add_data_sheet(writer, data, wb_formats):
    data.to_excel(excel_writer=writer, sheet_name='Data', header=False, startrow=1)
    data_sheet = writer.sheets['Data']
    set_data_header(data_sheet, data.columns.tolist(), wb_formats)
    set_column_formats(data_sheet, [''] + data.columns.tolist(), wb_formats, data_col_formats)


def set_data_header(ws, cols, wb_formats):
    ws.set_row(row=0, height=30, cell_format=wb_formats['header'])
    for (col_num, col_name) in enumerate(cols):
        ws.write(0, col_num + 1, std_name_to_output_name(col_name))
    ws.freeze_panes(1, 0)


def set_column_formats(ws, cols, wb_formats, col_name_to_format):
    for col in cols:
        if col in col_name_to_format:
            col_index = cols.index(col)
            format_dict = col_name_to_format[col]
            ws.set_column(col_index, col_index, format_dict['width'], wb_formats[format_dict['format']])


def add_graphs(wb, data):
    time_col = 1
    min_row = 1
    max_row = data.last_valid_index() + 1
    short_max_row = 500.0 / tick_time_ms

    pos_col = data.columns.tolist().index('Position') + 1
    vel_col = data.columns.tolist().index('Velocity') + 1
    current_col = data.columns.tolist().index('Total i') + 1

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

    if std_name_to_output_name('Duty cycle') in data.columns.tolist():
        duty_cycle_col = data.columns.tolist().index(std_name_to_output_name('Duty cycle')) + 1
        y_axes.append({'name': 'Duty Cycle',
                       'min_row': min_row,
                       'max_row': short_max_row,
                       'col': duty_cycle_col,
                       'secondary': True,
                       'line_width': 1.5
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


def add_summary_sheet(wb, summary_stats, wb_formats):
    sheet = wb.add_worksheet('Summary')
    row = 0
    sheet.set_column(0, 0, width=36, cell_format=wb_formats['header'])
    for field_name, field_value in summary_stats.items():
        if not field_name.startswith('separator'):
            sheet.write(row, 0, field_name)
            if isnan(field_value):
                field_value = 'N/A'
            sheet.write(row, 1, field_value)
        row += 1


def add_half_cycles_sheet(writer, half_cycle_stats, half_cycle_summary, wb_formats):
    half_cycle_stats.to_excel(excel_writer=writer,
                              sheet_name='Half-Cycles',
                              header=False,
                              index=False,
                              startrow=2)
    sheet = writer.sheets['Half-Cycles']
    set_column_formats(sheet, half_cycle_stats.columns.tolist(), wb_formats, half_cycle_col_formats)

    cur_row = 0
    sheet.write(cur_row, 0, "Half-Cycle List", wb_formats['title'])

    # write header row
    cur_row += 1
    sheet.set_row(row=cur_row, height=45, cell_format=wb_formats['header'])
    for (col_num, col_name) in enumerate(half_cycle_stats.columns):
        sheet.write(cur_row, col_num, col_name)

    # write summary rows
    cur_row = len(half_cycle_stats) + 3

    sheet.write(cur_row, 0, "Half-Cycle Summary", wb_formats['title'])
    cur_row += 1

    # repeat headers
    sheet.set_row(row=cur_row, height=45, cell_format=wb_formats['header'])
    for (col_num, col_name) in enumerate(half_cycle_summary.columns):
        sheet.write(cur_row, col_num + 1, col_name)

    cur_row += 1
    half_cycle_summary.to_excel(excel_writer=writer,
                                sheet_name='Half-Cycles',
                                header=False,
                                index=False,
                                startrow=cur_row,
                                startcol=1)


def add_motor_state_sheet(writer, motor_state_stats, wb_formats):
    motor_state_stats.to_excel(excel_writer=writer,
                               sheet_name='Motor States',
                               header=False,
                               index=False,
                               startrow=4)
    sheet = writer.sheets['Motor States']
    set_column_formats(sheet, motor_state_stats.columns.tolist(), wb_formats, motor_states_col_formats)

    cur_row = 0
    sheet.write(cur_row, 0, "Analysis by Motor State", wb_formats['title'])
    cur_row += 1
    subtitle = "Ignoring acceleration phase (first {} steps)".format(cruising_after_num_steps)
    sheet.write(cur_row, 0, subtitle, wb_formats['general'])

    # write header row
    cur_row += 2
    sheet.set_row(row=cur_row, height=45, cell_format=wb_formats['header'])
    for (col_num, col_name) in enumerate(motor_state_stats.columns):
        sheet.write(cur_row, col_num, col_name)

    wb = writer.book
    chart = wb.add_chart({'type': 'column'})
    chart.add_series({
        'name': 'DOWN',
        'categories': "='Motor States'!$B$5:$B$11",
        'values': "='Motor States'!$D$5:$D$11",
        'data_labels': {'value': True},
        'y_error_bars': {
            'type': 'custom',
            'plus_values': "='Motor States'!$E$5:$E$11",
            'minus_values': "='Motor States'!$E$5:$E$11"
        }
    })
    chart.add_series({
        'name': 'UP',
        'categories': "='Motor States'!$B$5:$B$11",
        'values': "='Motor States'!$D$12:$D$18",
        'data_labels': {'value': True},
        'y_error_bars': {
            'type': 'custom',
            'plus_values':  "='Motor States'!$E$12:$E$18",
            'minus_values': "='Motor States'!$E$12:$E$18"
        }
    })
    chart.set_size({'width': 880, 'height': 450})
    chart.set_title({'name': 'Average Velocity vs. Motor State & Direction'})

    sheet.insert_chart('I3', chart)


def add_positions_sheet(writer, position_stats, wb_formats):
    position_stats.to_excel(excel_writer=writer,
                            sheet_name='Positions',
                            header=False,
                            index=False,
                            startrow=3)
    sheet = writer.sheets['Positions']
    set_column_formats(sheet, position_stats.columns.tolist(), wb_formats, position_stats_col_formats)

    cur_row = 0
    sheet.write(cur_row, 0, "Analysis by Position", wb_formats['title'])

    # write header row
    cur_row += 2
    sheet.set_row(row=cur_row, height=45, cell_format=wb_formats['header'])
    for (col_num, col_name) in enumerate(position_stats.columns):
        sheet.write(cur_row, col_num, col_name)

    wb = writer.book
    vel_chart = wb.add_chart({'type': 'line'})
    down_first_row = 4
    down_last_row = down_first_row + len(position_stats[position_stats['Direction'] == 'DOWN']) - 1
    up_first_row = down_last_row + 1
    up_last_row = up_first_row + len(position_stats[position_stats['Direction'] == 'UP']) - 1

    vel_chart.add_series({
        'name': 'DOWN',
        'categories': "='Positions'!$B${}:$B${}".format(down_first_row, down_last_row),
        'values': "='Positions'!$C${}:$C${}".format(down_first_row, down_last_row),
        'y_error_bars': {
            'type': 'custom',
            'plus_values': "='Positions'!$D${}:$D${}".format(down_first_row, down_last_row),
            'minus_values': "='Positions'!$D${}:$D${}".format(down_first_row, down_last_row)
        }
    })
    vel_chart.add_series({
        'name': 'UP',
        'categories': "='Positions'!$B${}:$B${}".format(up_first_row, up_last_row),
        'values': "='Positions'!$C${}:$C${}".format(up_first_row, up_last_row),
        'y_error_bars': {
            'type': 'custom',
            'plus_values': "='Positions'!$D${}:$D${}".format(up_first_row, up_last_row),
            'minus_values': "='Positions'!$D${}:$D${}".format(up_first_row, up_last_row)
        }
    })
    vel_chart.set_size({'width': 880, 'height': 450})
    vel_chart.set_title({'name': 'Average Velocity vs. Position & Direction'})
    sheet.insert_chart('H3', vel_chart)

    cur_chart = wb.add_chart({'type': 'line'})
    cur_chart.add_series({
        'name': 'DOWN',
        'categories': "='Positions'!$B${}:$B${}".format(down_first_row, down_last_row),
        'values': "='Positions'!$E${}:$E${}".format(down_first_row, down_last_row),
        'y_error_bars': {
            'type': 'custom',
            'plus_values': "='Positions'!$F${}:$F${}".format(down_first_row, down_last_row),
            'minus_values': "='Positions'!$F${}:$F${}".format(down_first_row, down_last_row)
        }
    })
    cur_chart.add_series({
        'name': 'UP',
        'categories': "='Positions'!$B${}:$B${}".format(up_first_row, up_last_row),
        'values': "='Positions'!$E${}:$E${}".format(up_first_row, up_last_row),
        'y_error_bars': {
            'type': 'custom',
            'plus_values': "='Positions'!$F${}:$F${}".format(up_first_row, up_last_row),
            'minus_values': "='Positions'!$F${}:$F${}".format(up_first_row, up_last_row)
        }
    })
    cur_chart.set_size({'width': 880, 'height': 500})
    cur_chart.set_title({'name': 'Average Current vs. Position & Direction'})
    sheet.insert_chart('H26', cur_chart)


if __name__ == '__main__':
    if len(sys.argv) <= 1:
        # input_filename = r'Outputs\Noam with PSU emo_007.csv'
        input_filename = r'D:\Projects\Comet ME Pump Drive\run logs\emo_065.csv'
    else:
        input_filename = sys.argv[1]
    out_filename = post_process(input_filename)
    os.startfile(out_filename)
