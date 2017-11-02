#!/bin/env python

import os
import sys
from argparse import ArgumentParser

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QPushButton, QWidget, QApplication, QLabel

import xlsxwriter as xlwr
import xlrd


PARAMETERS_SHEET_NAME = 'Parameters'
HALF_CYCLES_SHEET_NAME = 'Half-Cycles'

DIRECTION_TEXT = 'Direction'
DOWN_AVERAGES_TEXT = 'DOWN Averages'
UP_AVERAGES_TEXT = 'UP Averages'
ALL_AVERAGES_TEXT = 'ALL Averages'
HALF_CYCLE_SUMMARY_TEXT = 'Half-Cycle Summary'

USER_DEFINED_FIELDS = ["Pump Head [m]", "Damper used?", "PSU or Solar Panels", "MPPT used?", "General Notes"]

OUTPUT_FILENAME = 'summary.xlsx'


def read_xlsx(d):
    entries = [entry for entry in os.scandir(d) if entry.is_file() and entry.path.endswith('xlsx')]
    filenames = [entry.path for entry in entries]
    return filenames


def get_readers(filenames):
    readers = [xlrd.open_workbook(filename=filename) for filename in filenames]
    data = [(reader, filename) for reader, filename in zip(readers, filenames) if
               HALF_CYCLES_SHEET_NAME in reader.sheet_names()]
    readers, filenames = [x[0] for x in data], [x[1] for x in data]
    return readers


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
    def subset(key_ind_dict, d, default=None):
        return [d.get(param, default) for param in key_ind_dict]


class IntAlloc():
    def __init__(self):
        self.val = 0

    def inc(self, delta):
        self.val += delta
        return self.val


def summarize_dir(d):
    output_filename = os.path.join(d, OUTPUT_FILENAME)
    filenames = read_xlsx(d)
    summarize_files(filenames=filenames, output_filename=output_filename)


def summarize_files(filenames, output_filename):
    """
    read all .xls files in the directory that have a 'Half-Cycles' sheet, and
    create a new summary.xls file from them
    :param dir:
    :return: written xlsx filename full path
    """
    readers = get_readers(filenames)
    N = len(readers)

    if N == 0:
        print("no files found")
        return

    print("reading parameters")
    all_parameters = [get_parameters(reader) for reader in readers]
    all_parameter_names = [p.keys() for p in all_parameters]
    known_parameters = small_int_dict(all_parameter_names)

    print("reading summaries")
    all_summaries = [get_summary_data(reader) for reader in readers]
    all_summary_titles = [x['titles'] for x in all_summaries]
    known_summary_titles = small_int_dict(all_summary_titles)

    # compute titles - we have a left col for the 'Up/Down/All' caption
    summary_titles = list(known_summary_titles.keys())
    parameter_names = list(known_parameters.keys())
    N_par = len(parameter_names)
    N_sum = len(summary_titles)
    top_titles = Render.points_add([(N_par, 'Down'), (N_sum, 'Up'), (N_sum, 'All')])
    titles = parameter_names + (3 * summary_titles)

    # writing starts here. write titles
    writer = xlwr.Workbook(output_filename)

    # formats for titles and cells
    title_format = writer.add_format(
        properties=dict(text_wrap=True, align='left', bold=True))
    col_format = writer.add_format(
        properties=dict(text_wrap=True, align='left', num_format='0.000'))
    user_format = writer.add_format(
        properties=dict(align='left', num_format='0.000'))

    # create sheet
    summary_out = writer.add_worksheet('Summary')

    row = IntAlloc()
    # write user defined fields
    for field in USER_DEFINED_FIELDS:
        summary_out.write_row(row=row.val, col=0, data=[field], cell_format=title_format)
        summary_out.write_row(row=row.val, col=1, data=[''], cell_format=user_format)
        row.inc(1)

    # create titles
    summary_out.write_column(row=row.val + 1, col=0, data=top_titles, cell_format=title_format)
    summary_out.write_column(row=row.val + 1, col=1, data=titles, cell_format=title_format)

    # write column for each file
    for reader_i, (parameters, summary) in enumerate(zip(all_parameters, all_summaries)):
        params_values = Render.subset(key_ind_dict=known_parameters, d=parameters)
        s_up, s_down, s_all = [
            {k: v for k, v in zip(summary['titles'], summary[key])}
            for key in ('up', 'down', 'all')]
        summary_rows = [Render.subset(known_summary_titles, sum_row)
                        for sum_row in (s_up, s_down, s_all)]
        summary_values = sum(summary_rows, [])
        filename = os.path.split(filenames[reader_i])[-1]
        data = [filename] + params_values + summary_values
        summary_out.write_column(row=row.val, col=reader_i + 2, data=data, cell_format=col_format)
    summary_out.set_column(firstcol=0, lastcol=2, width=8)
    summary_out.set_column(firstcol=2, lastcol=N + 3, width=8)
    writer.close()
    return output_filename


def find_similar_vacancy(base):
    i = 1
    d = os.path.dirname(base)
    filename_with_ext = os.path.basename(base)
    noext, ext = filename_with_ext.rsplit('.', 1)
    fname = base
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


class GUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.files = []
        self.output = None

    def summarize(self):
        summarize_files(self.files, self.output)
        raise SystemExit


    def initUI(self):
        self.setAcceptDrops(True)

        self.summarize_button = button(parent=self, title='Summarize', callback=self.summarize)
        self.summarize_button.move(100, 65)
        self.summarize_button.hide()

        self.drag_label = QLabel('drag files over here', self)
        self.drag_label.move(50, 65)

        self.setWindowTitle('Post Process xlsx summarizer')
        self.setGeometry(300, 300, 280, 150)

    def dragEnterEvent(self, e):
        e.accept()

    def dropEvent(self, e):
        # TODO: hide the drag label, show a button instead to do consolidation
        # get the relative position from the mime data
        mime = e.mimeData().text()
        file_colon_doubleslash = 'file://'
        files = [x[len(file_colon_doubleslash):] for x in mime.split('\r\n') if x.startswith(file_colon_doubleslash)]
        if len(files) == 0:
            print("no files dragged")
            return
        directory = os.path.dirname(files[0])
        self.output = find_similar_vacancy(os.path.join(directory, OUTPUT_FILENAME))
        if os.path.exists(self.output):
            # TODO - show error in gui
            print("failed to find an output filename that doesn't already exist")
            return
        print(f"writing output to {self.output}")
        self.summarize_button.text = f"write {os.path.basename(self.output)}"
        for file in files:
            if not os.path.exists(file):
                print(f"no such file {file}")
            else:
                self.files.append(file)
        if len(self.files) > 0:
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
    output = summarize_dir(args.dir)
    if not output:
        return
    print(f"wrote {output}")
    os.system(f'xdg-open {output}')


if __name__ == '__main__':
    main()
