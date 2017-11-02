import sys
import asyncio
import time
from bisect import bisect_left
from collections import defaultdict

from PyQt5 import QtGui, QtCore, QtWidgets
from quamash import QEventLoop
import pyqtgraph as pg
import pyqtgraph.console

from numpy import zeros, nan

from ..util import version

from ..cython_util import to_dicts

# for kernprof
import builtins
if 'profile' not in builtins.__dict__:
    builtins.__dict__['profile'] = lambda x: x


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"EmoTool - {version()}")
        self.main_widget = QtWidgets.QTabWidget(self)
        plot_tab = QtWidgets.QWidget(self.main_widget)
        self.main_widget.addTab(plot_tab, "plot")
        l = QtWidgets.QVBoxLayout(plot_tab)
        self.plot_widget = plot_widget = pg.PlotWidget()
        l.addWidget(plot_widget)
        self.plot_widget = plot_widget
        # TODO - make a menu action, not open by default
        c = pg.console.ConsoleWidget(namespace=globals(), text="test console")
        self.main_widget.addTab(c, "debug")
        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        self.statusBar().showMessage("Starting", 2000)

        self.ticks = defaultdict(list)
        self.vals = defaultdict(list)
        self.data_items = defaultdict(pg.PlotDataItem)

    @profile
    def log_variables(self, msgs):
        """
        Show points on log window. both @ticks and @vars are arrays

        :param msgs: [(ticks_scalar, [(name, value)])]
        :return:
        """
        new_ticks, new_vals = to_dicts(msgs)
        # TODO - better logic. Right now just shows last second, no zoom in possible. Plus second[ticks] is fixed
        last_tick = msgs[-1][0]
        cutoff_tick = last_tick - 8000
        for name in set(self.ticks.keys()) | set(new_ticks.keys()):
            if name not in self.data_items:
                item = self.data_items[name]
                self.plot_widget.addItem(item)
            else:
                item = self.data_items[name]
            ticks = self.ticks[name]
            vals = self.vals[name]
            i_cutoff = bisect_left(ticks, cutoff_tick)
            del ticks[:i_cutoff]
            del vals[:i_cutoff]
            ticks.extend(new_ticks[name])
            vals.extend(new_vals[name])
            item.setData(ticks, vals)
        first_tick = min([ticks[0] for ticks in self.ticks.values()])
        self.plot_widget.setXRange(first_tick, last_tick)

    def fileQuit(self):
        self.close()

    def closeEvent(self, ce):
        self.fileQuit()


def run_forever(main, create_main_window):
    """helper to start qt event loop and use it as the main event loop
    """
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    if create_main_window:
        window = MainWindow()
        window.show()
    else:
        window = None
    return main(loop, window)
