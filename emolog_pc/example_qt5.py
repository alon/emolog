#!/usr/bin/env python

# embedding_in_qt4.py --- Simple Qt4 application embedding matplotlib canvases
#
# Copyright (C) 2005 Florent Rougon
#               2006 Darren Dale
#
# This file is an example program for matplotlib. It may be used and
# modified with no restriction; raw copies as well as modified versions
# may be distributed without limitation.

from __future__ import unicode_literals
import sys
import os
from datetime import datetime

from Qt import QtGui, QtCore, QtWidgets

from numpy import sin
import pyqtgraph as pg

progname = os.path.basename(sys.argv[0])
progversion = "0.1"


class ValuesGenerator:
    def callback(self, t):
        st = sin(t * 100)
        st2 = st * st
        return 4 + st, 2 + st + st2, 4 - st, 2 - st2 + st


vg = ValuesGenerator()
callback = vg.callback


class MyPlotWindow(pg.PlotWidget):
    """A canvas that updates itself every second with a new plot."""

    def __init__(self):
        pg.PlotWidget.__init__(self, title="my plot widget")
        timer = QtCore.QTimer(self)
        self.t = []
        self.vals = []
        self.start = datetime.now()
        timer.timeout.connect(self.update_figure)
        timer.start(200)

    def update_figure(self):
        now = datetime.now()
        dt = (now - self.start).total_seconds()
        t0 = self.t[-1] if len(self.t) > 0 else 0
        t = [t0 + float(i) * 200 / dt for i in range(200)]
        self.call_callback(t)
        self.redraw()

    def call_callback(self, t):
        # Build a list of 4 random integers between 0 and 10 (both inclusive)

        self.t = (self.t + t)[-5000:]
        new_vals = callback(t)
        #new_vals = [1, 1.2]
        print(f'len(self.vals) = {len(self.vals)}')
        print(f'len(new_vals) = {len(new_vals)}')
        cur_vals = self.vals
        del self.vals[:]
        for vs, new_x in zip(cur_vals, new_vals):
            print(f'len(vs) = {len(vs)}')
            print(f'len(new_x = {len(new_x)}')
            self.vals.append((vs + new_x)[-5000:])

    def redraw(self):
        args = sum([[self.t, l] for l in self.vals], [])
        self.plot(*args, clear=True)
        #self.axes.set_ylim([-2, 10])


class ApplicationWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle("application main window")

        self.file_menu = QtWidgets.QMenu('&File', self)
        self.file_menu.addAction('&Quit', self.fileQuit,
                                 QtCore.Qt.CTRL + QtCore.Qt.Key_Q)
        self.menuBar().addMenu(self.file_menu)

        self.help_menu = QtWidgets.QMenu('&Help', self)
        self.menuBar().addSeparator()
        self.menuBar().addMenu(self.help_menu)

        self.help_menu.addAction('&About', self.about)

        self.main_widget = QtWidgets.QWidget(self)

        l = QtWidgets.QVBoxLayout(self.main_widget)
        plot_widget = MyPlotWindow()
        l.addWidget(plot_widget)

        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        self.statusBar().showMessage("All hail streamplot!", 2000)

    def fileQuit(self):
        self.close()

    def closeEvent(self, ce):
        self.fileQuit()

    def about(self):
        QtGui.QMessageBox.about(self, "About",
                                """embedding_in_qt4.py example
Copyright 2005 Florent Rougon, 2006 Darren Dale

This program is a simple example of a Qt4 application embedding matplotlib
canvases.

It may be used and modified with no restriction; raw copies as well as
modified versions may be distributed without limitation."""
                                )

def main():
    qApp = QtWidgets.QApplication(sys.argv)

    aw = ApplicationWindow()
    aw.show()
    sys.exit(qApp.exec_())


if __name__ == '__main__':
    main()
