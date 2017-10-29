import os
import sys

import xlsxwriter as xlwr
import xlrd


PARAMETERS_SHEET_NAME = 'Parameters'
HALF_CYCLES_SHEET_NAME = 'Half-Cycles'

DIRECTION_TEXT = 'Direction'
DOWN_AVERAGES_TEXT = 'DOWN Averages'
UP_AVERAGES_TEXT = 'UP Averages'
ALL_AVERAGES_TEXT = 'ALL Averages'
HALF_CYCLE_SUMMARY_TEXT = 'Half-Cycle Summary'


def get_readers_and_filenames(dir):
    entries = [entry for entry in os.scandir(dir) if entry.is_file() and entry.path.endswith('xlsx')]
    filenames = [entry.path for entry in entries]
    readers = [xlrd.open_workbook(filename=entry.path) for entry in entries]
    data = [(reader, filename) for reader, filename in zip(readers, filenames) if
               HALF_CYCLES_SHEET_NAME in reader.sheet_names()]
    readers, filenames = [x[0] for x in data], [x[1] for x in data]
    return readers, filenames


def verify_cell_at(sheet, row, col, contents):
    value = sheet.cell(rowx=row, colx=col).value
    if value != contents:
        print(f"expected sheet {hc.name}[{row},{col}] to be {contents} but found {value}")
        raise SystemExit


def find_row(sheet, col, text, max_row=200):
    for i in range(max_row):
        if sheet.cell(rowx=i, colx=col).value == text:
            return i
    print(f"{sheet.name}: could not find a row containing {text} in column {col}")
    raise SystemExit


def colvals(sheet, col):
    return [x.value for x in sheet.col(col)]


def rowvals(sheet, col):
    return [x.value for x in sheet.row(col)]


def get_parameters(reader):
    parameters = reader.sheet_by_name(PARAMETERS_SHEET_NAME)
    keys = colvals(parameters, 0)
    values = colvals(parameters, 1)
    return dict(zip(keys, values))


def get_summary_data(reader):
    hc = reader.sheet_by_name(HALF_CYCLES_SHEET_NAME)
    half_cycle_summary_row_number = find_row(hc, col=0, text=HALF_CYCLE_SUMMARY_TEXT)
    titles_row_number = half_cycle_summary_row_number + 1
    down_averages_row_number = half_cycle_summary_row_number + 2
    up_averages_row_number = half_cycle_summary_row_number + 3
    all_averages_row_number = half_cycle_summary_row_number + 4
    for row, text in [
        (titles_row_number, DIRECTION_TEXT),
        (down_averages_row_number, DOWN_AVERAGES_TEXT),
        (up_averages_row_number, UP_AVERAGES_TEXT),
        (all_averages_row_number, ALL_AVERAGES_TEXT),
    ]:
        verify_cell_at(hc, row=row, col=1, contents=text)
    rowxs = [titles_row_number, down_averages_row_number, up_averages_row_number, all_averages_row_number]
    summary_titles, down, up, all = [rowvals(hc, rowx)[2:] for rowx in rowxs]
    return dict(titles=summary_titles, down=down, up=up, all=all)


def small_int_dict(arrays):
    """
    Allocate an integer starting with 0 for each new key found in the <arrays>
    going over them one by one. An example:

    small_int_dict([['a', 'b'], ['a', 'c']]) => {'a': 0, 'b': 1, 'c': 2}
    :param arrays: [[Object]]
    :return: dict(Object -> int)
    """
    ret = {} # val -> int
    for i, arr in enumerate(arrays):
        for val in arr:
            if val not in ret:
                ret[val] = len(ret)
    return ret


def layout(points):
    """
    Take points = [(index, text)] and place them in a single row, i.e.:
    [(2, 'a'), (5, 'b')] => [None, None, 'a', None, None, 'b']
    :param points:
    :return:
    """
    max_i = max(i for i, v in points)
    ret = [None] * (max_i + 1)
    for i, v in points:
        ret[i] = v
    return ret


def consolidate(dir):
    """
    read all .xls files in the directory that have a 'Half-Cycles' sheet, and
    create a new consolidated_{start_date}_{end_date}.xls file from them
    :param dir:
    :return:
    """
    output_filename = 'consolidated.xlsx'
    if os.path.exists(output_filename):
        print(f"not overwriting {output_filename}")
        return
    readers, filenames = get_readers_and_filenames(dir)

    if len(readers) == 0:
        print("no files found")
        return

    all_parameters = [get_parameters(reader) for reader in readers]
    all_parameter_names = [p.keys() for p in all_parameters]
    known_parameters = small_int_dict(all_parameter_names)

    all_summaries = [get_summary_data(reader) for reader in readers]
    all_summary_titles = [x['titles'] for x in all_summaries]
    known_summary_titles = small_int_dict(all_summary_titles)

    # compute titles - we have a left col for the 'Up/Down/All' caption
    summary_titles = list(known_summary_titles.keys())
    parameter_names = list(known_parameters.keys())
    N_par = len(parameter_names)
    N_sum = len(summary_titles)
    top_titles = layout([(N_par, 'Down'), (N_par + N_sum, 'Up'), (N_par + 2 * N_sum, 'All')])
    titles = parameter_names + (3 * summary_titles)

    # writing starts here. write titles
    writer = xlwr.Workbook(output_filename)
    summary_out = writer.add_worksheet('Summary')
    summary_out.write_column(row=1, col=0, data=top_titles)
    summary_out.write_column(row=1, col=1, data=titles)

    # write column for each file
    for reader_i, (parameters, summary) in enumerate(zip(all_parameters, all_summaries)):
        params_values = [parameters.get(param, None) for param in known_parameters]
        s_up, s_down, s_all = [
            {k: v for k, v in zip(summary['titles'], summary[key])}
            for key in ('up', 'down', 'all')]
        summary_rows = [[sum_row.get(title, None) for title in known_summary_titles]
                        for sum_row in (s_up, s_down, s_all)]
        summary_values = sum(summary_rows, [])
        filename = os.path.split(filenames[reader_i])[-1]
        data = [filename] + params_values + summary_values
        summary_out.write_column(row=0, col=reader_i + 2, data=data)


def main():
    dir = os.getcwd() if len(sys.argv) < 2 else sys.argv[1]
    consolidate(dir)


if __name__ == '__main__':
    main()
