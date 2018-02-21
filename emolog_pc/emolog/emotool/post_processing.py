import os
import pandas as pd


def load_and_clean(input_csv_filename, prefixes_to_remove):
    data = pd.read_csv(input_csv_filename)
    data.columns = [clean_col_name(c, prefixes_to_remove) for c in data.columns]
    data = remove_unneeded_columns(data)
    data = data.set_index('Ticks')
    data = interpolate_missing_data(data)
    params = process_params_snapshot(input_csv_filename, prefixes_to_remove)
    return data, params


def std_name_to_output_name(name, output_col_names):
    if name in output_col_names:
        return output_col_names[name]
    return name


def output_name_to_std_name(output_name, output_col_names_inv):
    if output_name in output_col_names_inv:
        return output_col_names_inv[output_name]
    return output_name


def clean_col_name(name, prefixes):
    for prefix in prefixes:  # remove all annoying prefixes that may exist
        name = remove_prefix(name, prefix)
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


def add_time_column(data, tick_time_ms):
    data.loc[:, 'Time'] = data.index * tick_time_ms
    return data


def reorder_columns(data, first_cols):
    all_cols = data.columns.tolist()
    rest_of_cols = [c for c in all_cols if c not in first_cols]
    existing_first_cols = [c for c in first_cols if c in all_cols]
    data = data[existing_first_cols + rest_of_cols]
    return data


def interpolate_missing_data(data):
    data = data.fillna(method='ffill')
    return data


def process_params_snapshot(input_csv_filename, prefixes_to_remove):
    snapshot_csv_filename = input_csv_filename[:-4] + '_params.csv'
    if not os.path.isfile(snapshot_csv_filename):
        return None
    params = pd.read_csv(snapshot_csv_filename)
    assert(len(params) == 1)
    params.columns = [clean_col_name(c, prefixes_to_remove) for c in params.columns]
    params.drop(['Sequence', 'Timestamp', 'Ticks'], inplace=True, axis=1)
    return params


def add_workbook_formats(wb):
    formats = \
        {
            'frac': wb.add_format({'num_format': '0.000', 'align': 'left'}),
            'time': wb.add_format({'num_format': '0.00', 'align': 'left'}),
            'percent': wb.add_format({'num_format': '0.00%', 'align': 'left'}),
            'general': wb.add_format({'align': 'left'}),
            'header': wb.add_format({'text_wrap': True, 'bold': True}),
            'title': wb.add_format({'font_size': 14, 'bold': True}),
            'note': wb.add_format({'font_size': 12, 'italic': True, 'text_wrap': True}),
            'user_param': wb.add_format({'font_size': 12, 'bg_color': '#B8CCE4'})
        }
    return formats


def add_data_sheet(writer, data, wb_formats, data_col_formats, output_col_names):
    data.to_excel(excel_writer=writer, sheet_name='Data', header=False, startrow=1)
    data_sheet = writer.sheets['Data']
    set_data_header(data_sheet, data.columns.tolist(), wb_formats, output_col_names)
    set_column_formats(data_sheet, [''] + data.columns.tolist(), wb_formats, data_col_formats)


def add_params_sheet(wb, params, wb_formats):
    sheet = wb.add_worksheet('Parameters')
    row = 0
    sheet.set_column(0, 0, width=32)
    sheet.set_column(1, 1, width=32)
    for col in params.columns:
        sheet.write(row, 0, col, wb_formats['header'])
        sheet.write(row, 1, params[col][params.first_valid_index()], wb_formats['general'])
        row += 1


def set_data_header(ws, cols, wb_formats, output_col_names):
    ws.set_row(row=0, height=30, cell_format=wb_formats['header'])
    for (col_num, col_name) in enumerate(cols):
        ws.write(0, col_num + 1, std_name_to_output_name(col_name, output_col_names))
    ws.freeze_panes(1, 0)


def set_column_formats(ws, cols, wb_formats, col_name_to_format):
    for col in cols:
        if col in col_name_to_format:
            col_index = cols.index(col)
            format_dict = col_name_to_format[col]
            ws.set_column(col_index, col_index, format_dict['width'], wb_formats[format_dict['format']])


def add_scatter_graph(wb, data, data_sheet_name, chart_sheet_name, x_axis_col_name, requested_columns, col_formats,
                      min_row, max_row, axes_ranges):
    sheet = wb.add_chartsheet()
    chart = wb.add_chart({'type': 'scatter', 'subtype': 'straight'})
    x_axis_col = data.columns.tolist().index(x_axis_col_name)

    existing_columns = [c for c in requested_columns if c in data.columns and c != x_axis_col_name]
    for col_name in existing_columns:
        col_num = data.columns.tolist().index(col_name) + 1
        col_params = {'name': col_name,
                      'categories': [data_sheet_name, min_row, x_axis_col, max_row, x_axis_col],
                      'values': [data_sheet_name, min_row, col_num, max_row, col_num],
                      }
        # add either known column formats or the default format
        col_params.update(col_formats.get(col_name, col_formats['default']))
        chart.add_series(col_params)

    chart.set_x_axis({'label_position': 'low',
                      'min': axes_ranges['x']['min'],
                      'max': axes_ranges['x']['max'],
                      'line': {'none': True},
                      })
    chart.set_y_axis({'major_gridlines': {'visible': False},
                      'min': axes_ranges['y']['min'],
                      'max': axes_ranges['y']['max'],
                      })
    chart.set_y2_axis({'major_gridlines': {'visible': True},
                       'min': axes_ranges['y2']['min'],
                       'max': axes_ranges['y2']['max'],
                       })
    sheet.set_chart(chart)
    sheet.set_zoom(145)
    sheet.name = chart_sheet_name
