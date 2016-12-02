#(C)2002-2003 Chris Liechti <cliechti@gmx.net>
#redirect data from a TCP/IP connection to a serial port and vice versa
#requires Python 2.2 'cause socket.sendall is used

import sys
import os
import serial
import threading
import socket
import logging
import signal
from argparse import ArgumentParser

import colorama

import serial_util


log = logging.getLogger('serial2tcp')
log.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
ch.setFormatter(formatter)
log.addHandler(ch)

colorama.init()

RED_START = "\033[1;31m"
RED_END = "\033[0;0m"

verbose = False

class Redirector:
    def __init__(self, serial, socket):
        self.serial = serial
        self.socket = socket

    def shortcut(self):
        """connect the serial port to the tcp port by copying everything
           from one side to the other"""
        self.alive = True
        self.thread_read = threading.Thread(target=self.reader)
        self.thread_read.setDaemon(1)
        self.thread_read.start()
        self.writer()

    def verbose_log(self, s):
        if verbose:
            print(s)

    def reader(self):
        """loop forever and copy serial->socket"""
        while self.alive:
            try:
                #read one, blocking
                data = self.serial.read(1)
                #look if there is more
                n = self.serial.inWaiting()
                if len(data) > 0:
                    self.verbose_log("{}serial read{}: got 1 byte and {} more ready".format(RED_START, RED_END, n))
                if n:
                    #and get as much as possible
                    data = data + self.serial.read(n)
                if data:
                    #send it over TCP
                    self.verbose_log("socket write: writing {} bytes".format(len(data)))
                    self.socket.sendall(data)
            except socket.error as msg:
                log.error(msg)
                #probably got disconnected
                break
        self.alive = False

    def writer(self):
        """loop forever and copy socket->serial"""
        while self.alive:
            try:
                self.verbose_log("socket read: waiting for data")
                data = self.socket.recv(1024)
                if not data:
                    break
                self.verbose_log("socket read: read {} bytes, writing to serial".format(len(data)))
                self.serial.write(data)  # get a bunch of bytes and send them
            except socket.error as msg:
                log.error(repr(msg))
                break
            except Exception as e:
                log.critical(repr(e))
                break

        self.alive = False
        self.thread_read.join()

    def stop(self):
        """Stop copying"""
        if self.alive:
            self.alive = False
            self.thread_read.join()

if __name__ == '__main__':
    descr = 'WARNING: You have to allow connections only from the addresses' \
            'in the "--allow-list" option. e.g.' \
            '--allow-list="10.0.0.1, 172.16.0.1, 192.168.0.1"\n' \
            'NOTICE: This service supports only ' \
            'one tcp connection per instance.'

    usage = "USAGE: %(prog)s [options]\n\nSimple Serial to Network (TCP/IP)" \
            "redirector."

    parser = ArgumentParser(usage=usage, description=descr)
    parser.add_argument("-p", "--port", dest="serial",
                      help="Serial port, a number, defualt = '/dev/tty0'", type=str, default='auto')
    parser.add_argument("-b", "--baud", dest="baudrate",
                      help="Baudrate, default 115200", default=115200, type=int)
    parser.add_argument("-r", "--rtscts", dest="rtscts",
                      help="Enable RTS/CTS flow control (default off)", action='store_true', default=False)
    parser.add_argument("-x", "--xonxoff", dest="xonxoff",
                      help="Enable software flow control (default off)", action='store_true', default=False)
    parser.add_argument("-P", "--localport", dest="port",
                      help="TCP/IP port on which to run the server (default 9100)", type=int, default=9100)
    parser.add_argument("-l", "--listen", dest="listen",
                      help="Listen address on which to run the server (default '127.0.0.1')", type=str, default='127.0.0.1')
    parser.add_argument(
        '--access-list', dest='acl', type=str, default="127.0.0.1",
        help="List of IP addresses e.g '127.0.0.1, 192.168.0.2'")
    parser.add_argument(
        '--verbose', dest='verbose', action='store_true', default=False,
        help='Be verbose')

    options = parser.parse_args()

    if options.serial == 'auto':
        options.serial = serial_util.find_serial()

    verbose = options.verbose

    access_list = set([ip.strip(" ") for ip in options.acl.split(',')])

    log.info("TCP/IP to Serial redirector (Ctrl-C to quit)")

    try:
        ser = serial.Serial(
            port=options.serial,
            baudrate=options.baudrate,
            rtscts=options.rtscts,
            xonxoff=options.xonxoff,
            #required so that the reader thread can exit
            timeout=1
            )
    except serial.SerialException as e:
        log.fatal("Could not open serial port %s: %s" % (options.serial, e))
        sys.exit(1)

    # TODO: necessary?
    ser.flushInput()
    ser.flushOutput()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind((options.listen, options.port))
    srv.listen(1)

    def signal_handler(signal, frame):
        try:
            srv.close()
        except Exception as e:
            log.warning(repr(e))
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    while 1:
        try:
            print("Waiting for connection...")
            connection, addr = srv.accept()
            address, port = addr
            log.info('Connecting with tcp://{0}:{1}'.format(address, port))
            if address in access_list:
                #enter console->serial loop
                r = Redirector(ser, connection)
                r.shortcut()
            else:
                log.error('Address {0} not in access list.'.format(address))
        except socket.error as msg:
            log.error(msg)
        finally:
            try:
                connection.close()
                log.info('Disconnecting')
            except NameError:
                pass
            except Exception as e:
                log.warning(repr(e))