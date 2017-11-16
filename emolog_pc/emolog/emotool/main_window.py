import sys
import time
from bisect import bisect_left
from collections import defaultdict
from argparse import ArgumentParser
from struct import unpack
from pickle import loads

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtNetwork import QTcpSocket
from PyQt5.QtCore import QDataStream
import pyqtgraph as pg
import pyqtgraph.console

from numpy import zeros, nan

from ..util import version

from ..cython_util import to_dicts, coalesce_meth

# for kernprof
import builtins
if 'profile' not in builtins.__dict__:
    builtins.__dict__['profile'] = lambda x: x


SIZEOF_UINT32 = 4


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.socket = QTcpSocket()
        self.socket.connectToHost('localhost', args.port)
        self.socket.readyRead.connect(self.readFromEmotool)
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
        
        self.incoming = b''
        self.next_message_size = None

    @coalesce_meth(10) # Limit refreshes, they can be costly
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

    def readFromEmotool(self):
        """
        This is a temporary measure - instead of the better solution:
         serial2tcp process <-> app
        We have
         serial2tcp process <-> emotool <-> app
        Just to avoid rewriting the emotool parts to drop asyncio support so they can be reused for app and emotool.
        
        Quick transport costs calculation (copy cost):
        20000 msg/second
        msg size < 100 bytes
        < 2 MB /second
        """
        self.incoming += self.socket.readAll()
        N = len(self.incoming)
        i = 0
        messages = []
        while i < N:
            if self.next_message_size is None:
                if N - i < SIZEOF_UINT32:
                    break
                self.next_message_size, = unpack('<i', self.incoming[i : i + SIZEOF_UINT32])
                i += SIZEOF_UINT32
            if self.next_message_size > N - i:
                break
            data = self.incoming[i : i + self.next_message_size]
            i += self.next_message_size
            messages.extend(loads(data))
            self.next_message_size = None
        self.incoming = self.incoming[i:]
        if len(messages) > 0:
            self.log_variables(messages)


    def fileQuit(self):
        self.close()

    def closeEvent(self, ce):
        self.fileQuit()


def main():
    """helper to start qt event loop and use it as the main event loop
    """
    app = QtWidgets.QApplication(sys.argv)
    parser = ArgumentParser()
    parser.add_argument('--port', type=int, default=10000, help='port emotool is listening on, right now samples only')
    args = parser.parse_args()
    window = MainWindow(args)
    window.show()
    app.exec_()


if __name__ == '__main__':
    main()