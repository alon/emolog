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

import asyncio

from Qt import QtGui, QtCore, QtWidgets
from Qt.QtWidgets import QApplication, QProgressBar
from quamash import QEventLoop, QThreadExecutor

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
        self.t = []
        self.vals = []
        self.start = datetime.now()

    def add_point(self, x):
        now = datetime.now()
        t = (now - self.start).total_seconds()
        self.t.append(t)
        self.vals.append(x)
        self.redraw()

    def redraw(self):
        if len(self.t) == 0 or len(self.vals) == 0:
            return
        if len(self.t) != len(self.vals):
            print(f"error: {len(self.t)} != {len(self.vals)}")
            return
        print(f"drawing #{len(self.t)} elements")
        self.plot(self.t, self.vals, clear=True)
        #self.axes.set_ylim([min(self.vals), max(self.vals)])
        #self.axes.set_xlim([min(self.t), max(self.t)])


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
        self.plot_widget = plot_widget

        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        self.statusBar().showMessage("All hail streamplot!", 2000)

    def add_point(self, x):
        self.plot_widget.add_point(x)

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


class MyClient(asyncio.Protocol):
    def connection_lost(self, exc):
        print("connection lost")

    def connection_made(self, transport):
        self.transport = transport
        print("connection made")

    def data_received(self, data):
        print("got data; {}".format(repr(data)))
        self.aw.add_point(len(data))


async def amain(app, loop, aw):
    client = MyClient()
    port = 9988
    print("connecting to localhost:{}".format(port))
    def create_client():
        client = MyClient()
        client.aw = aw
        return client
    await loop.create_connection(create_client, '127.0.0.1', port)


def main():
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    aw = ApplicationWindow()
    aw.show()
    loop.run_until_complete(amain(app, loop, aw))
    loop.run_forever()
    #sys.exit(qApp.exec_())


if __name__ == '__main__':
    main()
