#!/bin/env python

import os
import sys
from argparse import ArgumentParser
from linecache import getlines
from configparser import ConfigParser

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QPushButton, QWidget, QApplication, QLabel

import xlsxwriter as xlwr
import xlrd
from xlsxwriter.utility import xl_rowcol_to_cell

from .ppxl_util import (
HALF_CYCLE_CELL_TO_FORMULA,
HALF_CYCLE_PREDEFINED_TITLES,
HALF_CYCLE_PREDEFINED_CELL_NAMES,
HALF_CYCLE_TITLE_TO_CELL_NAME,
HALF_CYCLE_CELL_TO_TITLE_NAME,
HALF_CYCLE_FORMULA_TITLES,
)

PARAMETERS_SHEET_NAME = 'Parameters'
HALF_CYCLES_SHEET_NAME = 'Half-Cycles'

DIRECTION_TEXT = 'Direction'
DOWN_AVERAGES_TEXT = 'DOWN Averages'
UP_AVERAGES_TEXT = 'UP Averages'
ALL_AVERAGES_TEXT = 'ALL Averages'
HALF_CYCLE_SUMMARY_TEXT = 'Half-Cycle Summary'

CONFIG_FILENAME = 'summary.ini'
OUTPUT_FILENAME = 'summary.xlsx'


def read_xlsx(d):
    entries = [entry for entry in os.scandir(d) if entry.is_file() and entry.path.endswith('xlsx')]
    filenames = list(sorted([entry.path for entry in entries]))
    return filenames


def get_readers(filenames):
    readers = [xlrd.open_workbook(filename=filename) for filename in filenames]
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


class Render():
    """
    Utilities for creating rows or columns from shorter descriptions
    """
    @staticmethod
    def points(points):
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

    @staticmethod
    def points_add(deltas):
        data = []
        ind = 0
        for d, v in deltas:
            ind += d
            data.append((ind, v))
        return Render.points(data)

    @staticmethod
    def subset(subset, d, default=None):
        return [d.get(param, default) for param in subset]


class IntAlloc():
    def __init__(self, init=0):
        self.val = init

    def inc(self, delta):
        self.val += delta
        return self.val


def summarize_dir(d, config):
    filenames = read_xlsx(d)
    output_filename = summarize_files(filenames=filenames, output_path=d, config=config)
    return output_filename


def enum_cum_len(vs, initial=0):
    if len(vs) == 0:
        return
    acc = initial
    for v in vs:
        yield acc, v
        acc += len(v)


class Output:
    def __init__(self, filename):
        self.filename = filename
        self.cell_formats = []
        self.data = []

    def add(self, row, col, value, cell_format):
        self.data.append((row, col, value, cell_format))

    def add_row(self, row, col, data, cell_format):
        for i, value in enumerate(data):
            self.add(row=row, col=col + i, value=value, cell_format=cell_format)

    def add_col(self, row, col, data, cell_format):
        for i, value in enumerate(data):
            self.add(row=row + i, col=col, value=value, cell_format=cell_format)

    def add_format(self, **kw):
        """
        Identical to add_format(properties=kw)
        :param kw:
        :return:
        """
        self.cell_formats.append(kw)
        return len(self.cell_formats) - 1

    def write(self):
        writer = xlwr.Workbook(self.filename)
        formats = {i: writer.add_format(properties=properties) for i, properties in enumerate(self.cell_formats)}
        summary_out = writer.add_worksheet('Summary')
        for row, col, value, format in self.data:
            summary_out.write(row, col, value, formats[format]) # cannot use named arguments due to (row, col, *args) def
        writer.close()


def dunion(d1, d2):
    d = dict(d1)
    d.update(d2)
    return d


def summarize_files(filenames, output_path, config):
    """
    read all .xls files in the directory that have a 'Half-Cycles' sheet, and
    create a new summary.xls file from them
    :param dir:
    :return: written xlsx filename full path
    """
    readers, filenames = get_readers(filenames) # the initial filenames contains xlsx that are not produced by the post processor
    N = len(readers)

    if N == 0:
        print("no files found")
        return

    output_filename = allocate_unused_file_in_directory(os.path.join(output_path, OUTPUT_FILENAME))

    user_defined_fields = [x for x in config.user_defined_fields if x not in HALF_CYCLE_PREDEFINED_TITLES]
    half_cycle_directions = config.half_cycle_directions
    half_cycle_fields = config.half_cycle_fields

    print("reading parameters")
    all_parameters = [get_parameters(reader) for reader in readers]

    print("reading summaries")
    all_summaries = [get_summary_data(reader) for reader in readers]

    # compute titles - we have a left col for the 'Up/Down/All' caption
    summary_titles = half_cycle_fields
    parameter_names = HALF_CYCLE_PREDEFINED_TITLES + [x for x in config.parameters]
    N_par = len(parameter_names)
    N_sum = len(summary_titles)
    N_user = len(user_defined_fields)
    top_titles = [None] * N_par + sum([[d] * N_sum for d in half_cycle_directions], [])
    titles = parameter_names + (len(half_cycle_directions) * summary_titles)

    # aggregate all data to output: tuples of row, col, format, value
    output = Output(output_filename)

    # formats for titles and cells
    title_format = output.add_format(text_wrap=True, align='left', bold=True)
    col_format = output.add_format(text_wrap=True, align='left', num_format='0.000')
    user_format = output.add_format(align='left', num_format='0.000')

    # check we have all inputs required for the formula presented
    formulae = [HALF_CYCLE_CELL_TO_FORMULA[HALF_CYCLE_TITLE_TO_CELL_NAME[k]] for k in summary_titles
                if k in HALF_CYCLE_FORMULA_TITLES]
    cell_names = lambda ff: [x for x in ff.__code__.co_varnames if x.endswith('_cell')]
    required_cell_names = set(sum([cell_names(f) for f in formulae], []))

    available_cell_names = {HALF_CYCLE_TITLE_TO_CELL_NAME[x] for x in set(HALF_CYCLE_TITLE_TO_CELL_NAME.keys()) & set(titles)}

    if required_cell_names - available_cell_names:
        missing_names = list(sorted(required_cell_names - available_cell_names))
        print(f"missing cells: {missing_names}")
        missing_titles = [HALF_CYCLE_CELL_TO_TITLE_NAME[n] for n in missing_names]
        print(f"equivalent titles:{missing_titles}")
        return

    row = IntAlloc()
    # create titles
    output.add_row(col=row.val + 1, row=0, data=[''] * N_user + top_titles, cell_format=title_format)
    output.add_row(col=row.val + 1, row=1, data=user_defined_fields + titles, cell_format=title_format)
    row.inc(2)

    # write column for each file
    def cells_from_d(keys, row, col):
        return {HALF_CYCLE_TITLE_TO_CELL_NAME[k]:
                                  xl_rowcol_to_cell(row=row, col=col + i) for i, k in enumerate(keys)
                if k in HALF_CYCLE_TITLE_TO_CELL_NAME}

    param_left_col = 1 + N_user + N_par # 1 - for file name; TODO: make this declarative (place cells on board with name, than use name)

    for reader_i, (parameters, summary) in enumerate(zip(all_parameters, all_summaries)):
        params_values = Render.subset(subset=parameter_names, d=parameters)
        sum_per_dir = [
            {k: HALF_CYCLE_CELL_TO_FORMULA.get(HALF_CYCLE_TITLE_TO_CELL_NAME.get(k, None), v) for k, v in zip(summary['titles'], summary[key.lower()])}
            for key in half_cycle_directions]
        cell_locations = {k: xl_rowcol_to_cell(row=row.val, col=1 + i) for i, k in enumerate(HALF_CYCLE_PREDEFINED_CELL_NAMES)}
        summary_rows_with_unfilled_formula = [
            (Render.subset(summary_titles, sum_row), dunion(cell_locations, cells_from_d(keys=summary_titles, row=row.val, col=col)))
                        for col, sum_row in enum_cum_len(sum_per_dir, initial=param_left_col)]
        for values, cells in summary_rows_with_unfilled_formula:
            assert len(cells.values()) == len(set(cells.values())), "error: allocated same cell to two variables"
        summary_rows = [[x(**cells) if callable(x) else x for x in values]
                        for values, cells in summary_rows_with_unfilled_formula]
        summary_values = sum(summary_rows, [])
        filename = os.path.split(filenames[reader_i])[-1]
        data = [filename] + [''] * N_user + params_values + summary_values
        output.add_row(col=0, row=reader_i + 2, data=data, cell_format=col_format)
    #summary_out.set_row(firstrow=0, lastrow=2, width=8)
    #summary_out.set_row(firstrow=2, lastrow=N + 3, width=8)
    output.write()
    return output_filename


def allocate_unused_file_in_directory(initial):
    """look for a file at the dirname(initial) with basename(initial)
    file name. If one already exists, try adding _1, then _2 etc. right
    before the extention
    """
    i = 1
    d = os.path.dirname(initial)
    filename_with_ext = os.path.basename(initial)
    noext, ext = filename_with_ext.rsplit('.', 1)
    fname = initial
    while os.path.exists(fname) and i < 1000:
        fname = os.path.join(d, f'{noext}_{i}.{ext}')
        i += 1
    return fname


def button(parent, title, callback):
    class Button(QPushButton):
        def mousePressEvent(self, e):
            QPushButton.mousePressEvent(self, e)
            callback()
    return Button(title, parent)


def paths_from_file_urls(urls):
    ret = []
    file_colon_doubleslash = 'file://'
    for x in urls:
        if not x.startswith(file_colon_doubleslash):
            continue
        x = x[len(file_colon_doubleslash):]
        if 'win' in sys.platform:
            # starts with an extra '/', remove it
            x = x[1:]
        if not os.path.exists(x):
            print(f"no such file: {x}")
            continue
        ret.append(x)
    return ret


class Config:
    def __init__(self, d):
        ini_filename = os.path.join(d, CONFIG_FILENAME)
        if os.path.exists(ini_filename):
            print(f"reading config from {ini_filename}")
            self.config = ConfigParser()
            self.config.read(ini_filename)
        else:
            self.config = None
        self.user_defined_fields = self._get_strings('user_defined', 'fields', ["Pump Head [m]", "Damper used?", "PSU or Solar Panels", "MPPT used?", "General Notes"])
        self.half_cycle_fields = self._get_strings('half_cycle', 'fields', default=['Average Velocity [m/s]', 'Flow Rate [LPM]'])
        self.half_cycle_directions = self._get_strings('half_cycle', 'directions', ['down', 'up', 'all'])
        self.parameters = self._get_strings('global', 'parameters', [])

    def _get(self, section, field, default):
        if self.config is not None and self.config.has_option(section, field):
            return self.config.get(section, field, raw=True) # avoid % interpolation, we want to have % values
        return default

    def _get_strings(self, section, field, default):
        if self.config is not None and self.config.has_option(section, field):
            return [x.strip() for x in [y for y in self.config.get(section, field, raw=True).split(',') if len(y) > 0]]
        return default

class GUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.files = set()
        self.output = None

    def summarize(self):
        config = Config(self.output)
        summarize_files(list(self.files), self.output, config=config)
        if hasattr(os, 'startfile'):
            os.startfile(self.output)
        else:
            os.system(f'xdg-open {self.output}')
        raise SystemExit


    def initUI(self):
        self.setAcceptDrops(True)

        self.summarize_button = button(parent=self, title='Summarize', callback=self.summarize)
        self.summarize_button.move(100, 65)
        self.summarize_button.hide()

        self.drag_label = QLabel('drag files here', self)
        self.drag_label.move(50, 65)

        self.setWindowTitle('Post Process xlsx summarizer')
        self.setGeometry(300, 300, 280, 150)

    def dragEnterEvent(self, e):
        e.accept()

    def dropEvent(self, e):
        # TODO: hide the drag label, show a button instead to do consolidation
        # get the relative position from the mime data
        mime = e.mimeData().text()
        files = paths_from_file_urls([x.strip() for x in mime.split('\n')])
        if len(files) == 0:
            print("no files dragged")
            return
        directory = os.path.dirname(files[0])
        self.output = directory
        if os.path.exists(self.output):
            self.status_label.setText('too many existing summarize.xlsx files, delete them')
            print("failed to find an output filename that doesn't already exist")
            return
        for file in files:
            if not os.path.exists(file):
                print(f"no such file {file}")
            else:
                self.files.add(file)
        if len(self.files) > 0:
            self.summarize_button.setText(f"{len(self.files)} to {self.output}")
            self.drag_label.hide()
            self.summarize_button.show()
        else:
            print("len(self.files) == 0")
        e.accept()


def start_gui():
    app = QApplication(sys.argv)
    ex = GUI()
    ex.show()
    app.exec_()


def main():
    parser = ArgumentParser()
    parser.add_argument('--dir')
    args = parser.parse_args()
    if args.dir is None:
        # gui mode
        start_gui()
        return

    # console mode
    output = summarize_dir(args.dir, Config(args.dir))
    if not output:
        return
    print(f"wrote {output}")
    os.system(f'xdg-open {output}')


if __name__ == '__main__':
    main()
