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

from serial.tools.list_ports import comports
import colorama


SERIAL_AUTO_VENDOR_ID = 0x0403
SERIAL_AUTO_PRODUCT_ID = 0x6010

def find_serial():
    available = comports()
    if len(available) == 0:
        print("no com ports available - is board powered and connected?")
        raise SystemExit
    available = [ser for ser in available if ser.vid == SERIAL_AUTO_VENDOR_ID and ser.pid == SERIAL_AUTO_PRODUCT_ID]
    if len(available) == 0:
        print("no com port matching vendor/product ids available - is board powered and connected?")
        raise SystemExit
    if len(available) > 1:
        # pick the lowest interface in multiple interface devices
        if hasattr(available[0], 'device_path'):
            device = min([(x.device_path.split('/')[:-1], x) for x in available])[1]
        else:
            device = min([(x.device, x) for x in available])[1]
    else:
        device = available[0]
    comport = device.device
    print("automatic comport selection: {}".format(comport))
    return comport


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
    def __init__(self, serial, s):
        self.serial = serial
        self.socket = s
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 20 * 1024 * 1024)

    def shortcut(self):
        """connect the serial port to the tcp port by copying everything
           from one side to the other"""
        self.alive = True
        self.thread_read = threading.Thread(target=self.reader)
        self.thread_read.setDaemon(1)
        self.thread_read.start()
        self.writer()

    def reader(self):
        """loop forever and copy serial->socket"""
        while self.alive:
            try:
                #read one, blocking
                data = self.serial.read(1)
                #look if there is more
                n = self.serial.inWaiting()
                if n:
                    #and get as much as possible
                    data = data + self.serial.read(n)
                if data:
                    #if b'EM\x03' in data: print("probably an ACK")
                    #send it over TCP
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
                data = self.socket.recv(1)
                if not data:
                    break
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
                      help="Serial URL or port, a number, default = '/dev/tty0'", type=str, default='auto')
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

    options = parser.parse_args()

    if options.serial == 'auto':
        options.serial = find_serial()

    access_list = set([ip.strip(" ") for ip in options.acl.split(',')])

    log.info("TCP/IP to Serial redirector (Ctrl-C to quit)")

    try:
        ser = serial.serial_for_url(
            options.serial,
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
        pass

    signal.signal(signal.SIGINT, signal_handler)

    try:
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
