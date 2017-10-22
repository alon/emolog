import sys
import asyncio
import time
from bisect import bisect_left

from Qt import QtGui, QtCore, QtWidgets
from quamash import QEventLoop
import pyqtgraph as pg
import pyqtgraph.console

from util import version


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"EmoTool - {version()}")
        self.main_widget = QtWidgets.QTabWidget(self)
        plot_tab = QtWidgets.QWidget(self.main_widget)
        self.main_widget.addTab(plot_tab, "plot")
        l = QtWidgets.QVBoxLayout(plot_tab)
        plot_widget = pg.PlotWidget()
        l.addWidget(plot_widget)
        self.plot_widget = plot_widget
        # TODO - make a menu action, not open by default
        c = pg.console.ConsoleWidget(namespace=globals(), text="test console")
        self.main_widget.addTab(c, "debug")
        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        self.statusBar().showMessage("Starting", 2000)

        self.ticks = []
        self.vals = []

    def log_variables(self, ticks, vars):
        """
        Show points on log window. both @ticks and @vars are arrays

        :param ticks: [ticks]
        :param vars: [[(name, value)]]
        :return:
        """
        if max(len(vs) for vs in vars) > 1:
            print("TODO: ignoring everything except first variable")
        vals = [vs[0][1] for vs in vars]
        # TODO - better logic. Right now just shows last second, no zoom in possible. Plus second[ticks] is fixed
        cutoff_ticks = ticks[-1] - 5000
        i_cutoff = bisect_left(self.ticks, cutoff_ticks)
        self.ticks = self.ticks[i_cutoff:] + ticks # list concatenation
        self.vals = self.vals[i_cutoff:] + vals # list concatenation
        self.plot_widget.plot(self.ticks, self.vals, clear=True)
        self.plot_widget.setXRange(self.ticks[-1] - 8000, self.ticks[-1])

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
