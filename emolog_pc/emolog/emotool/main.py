#!/bin/env python

# import os
# os.environ['PYTHONASYNCIODEBUG'] = '1'
# import logging
# logging.getLogger('asyncio').setLevel(logging.DEBUG)

import argparse
import os
import sys
import string
import logging
import csv
import struct
import random
import asyncio
from functools import reduce
from time import time, sleep
from socket import socket
from subprocess import Popen
from configparser import ConfigParser
from shutil import which

from ..lib import Client, SamplerSample, AckTimeout
from ..dwarf import FileParser
from ..util import version, coalesce_meth
from .post_processor import post_process
from .main_window import run_forever


logger = logging.getLogger()


def with_errors(s):
    # TODO - find a library for this? using error distance
    #  deleted element
    for i in range(0, len(s)):
        yield s[:i] + s[i + 1:]
    # rotated adjacent elements
    for i in range(0, len(s) - 1):
        yield s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if len(s) > 3:
        # 26**3 is already ~ 1e5 is too much
        return
    # single complete alphabet typing errors - this is really large..
    for i in range(0, len(s)):
        for other in string.ascii_lowercase:
            yield s[:i] + other + s[i + 1:]


def dwarf_get_variables_by_name(filename, names):
    file_parser = FileParser(filename=filename)
    sampled_vars = {}
    found = set()
    elf_vars = list(file_parser.visit_interesting_vars_tree_leafs())
    elf_var_names = [v.get_full_name() for v in elf_vars]
    lower_to_actual = {name.lower(): name for name in elf_var_names}
    elf_var_names_set_lower = set(lower_to_actual.keys())
    logger.debug('candidate variables found in ELF file:')
    for v in elf_vars:
        v_name = v.get_full_name()
        logger.debug("candidate var: {}".format(v_name))
        if v_name in names:
            if v.address == v.ADDRESS_TYPE_UNSUPPORTED:
                logger.error("Address type not supported for requested variable '{}'".format(v_name))
                raise SystemExit
            sampled_vars[v_name] = v
            found.add(v_name)
    given = set(names)
    if given != found:
        logger.error("the following variables were not found in the ELF:\n{}".format(", ".join(list(given - found))))
        elf_name_to_options = {name: set(with_errors(name)) for name in elf_var_names_set_lower}
        missing_lower = [name.lower() for name in given - found]
        missing_lower_to_actual = {name.lower(): name for name in given - found}
        missing_to_errors = {name: set(with_errors(name)) for name in missing_lower}
        for name in missing_lower:
            options = [elf_name for elf_name, elf_options in elf_name_to_options.items() if
                       len(missing_to_errors[name] & elf_options) > 0]
            if len(options) > 0:
                print("{} is close to {}".format(missing_lower_to_actual[name],
                                                 ", ".join(lower_to_actual[x] for x in options)))
        raise SystemExit
    logger.info("Registering variables from {}".format(filename))
    for v in sampled_vars.values():
        logger.info("   {}".format(v.get_full_name()))
    return sampled_vars


async def start_fake_sine(ticks_per_second, port):
    # Run in a separate process so it doesn't hog the CPython lock
    # Use our executable to work with a development environment (python executable)
    # or pyinstaller (emotool.exe)
    if sys.argv[0].endswith('python'):
        assert sys.argv[1] == 'emotool.py', f"unknown case: sys.argv[1] == {sys.argv[1]}"
        cmdline = sys.argv[:2]
    elif which(sys.argv[0]):
        cmdline = [sys.argv[0]]
    else:
        cmdline = ['python', sys.argv[0]]
    print(f"{sys.argv!r} ; which said {which(sys.argv[0])}")
    create_process(cmdline + ['--embedded', str(ticks_per_second), str(port)])


class EmoToolClient(Client):
    # must be singleton!
    # to allow multiple instances, some refactoring is needed, namely around the transport and subprocess
    # currently the serial subprocess only accepts a connection once, and the transport is never properly released
    # until the final cleanup. This means multiple instances will fail to communicate.

    instance = None

    def __init__(self, verbose, dump, window):
        if EmoToolClient.instance is not None:
            raise Exception("EmoToolClient is a singleton, can't create another instance")
        super(EmoToolClient, self).__init__(verbose=verbose, dump=dump)
        self.csv = None
        self.csv_filename = None
        self.first_ticks = None
        self.last_ticks = None
        self.min_ticks = None
        self.names = None
        self.samples_received = 0
        self.ticks_lost = 0
        self.max_ticks = None
        self._running = False
        self.fd = None
        self.window = window
        EmoToolClient.instance = self  # for singleton

    def reset(self, csv_filename, names, min_ticks, max_ticks):
        self.csv = None
        self.csv_filename = csv_filename
        self.first_ticks = None
        self.last_ticks = None
        self.min_ticks = min_ticks
        self.names = names
        self.samples_received = 0
        self.ticks_lost = 0
        self.max_ticks = max_ticks
        self._running = True

    @property
    def running(self):
        return self._running

    @property
    def total_ticks(self):
        if self.first_ticks is None or self.last_ticks is None:
            return 0
        return self.last_ticks - self.first_ticks

    def initialize_file(self):
        if self.csv:
            return
        self.fd = open(self.csv_filename, 'w+')
        self.csv = csv.writer(self.fd, lineterminator='\n')
        self.csv.writerow(['sequence', 'ticks', 'timestamp'] + self.names)

    def stop(self):
        self._running = False

    def handle_sampler_samples(self, msgs):
        """
        Write to CSV, add points to plots
        :param msgs: [(seq, ticks, {name: value})]
        :return: None
        """
        if not self._running:
            return
        if not self.csv:
            self.initialize_file()
        # TODO - decode variables (integer/float) in emolog VariableSampler
        now = time() * 1000
        self.csv.writerows([[seq, ticks, now] +
                          [variables.get(name, '') for name in self.names] for seq, ticks, variables in msgs])
        self.fd.flush()
        if self.window:
            for msg in msgs:
                self.plot(msg)
        self.samples_received += len(msgs)
        for seq, ticks, variables in msgs:
            if self.last_ticks is not None and ticks - self.last_ticks != self.min_ticks:
                print("{:8.5}: ticks jump {:6} -> {:6} [{:6}]".format(
                    now / 1000, self.last_ticks, ticks, ticks - self.last_ticks))
                self.ticks_lost += ticks - self.last_ticks - self.min_ticks
            self.last_ticks = ticks
        if self.first_ticks is None:
            self.first_ticks = self.last_ticks
        if self.max_ticks is not None and self.total_ticks + 1 >= self.max_ticks:
            self.stop()

    def plot(self, msg):
        (_seq, ticks, variables) = msg
        self.do_plot((ticks, list(variables.items())))

    @coalesce_meth(hertz=10) # Limit refreshes, they can be costly
    def do_plot(self, msgs):
        self.window.log_variables(msgs=msgs)


def iterate(prefix, initial):
    while True:
        yield '{}_{:03}.csv'.format(prefix, initial)
        initial += 1


def next_available(folder, prefix):
    filenames = iterate(prefix, 1)
    for filename in filenames:
        candidate = os.path.join(folder, filename)
        if not os.path.exists(candidate):
            return candidate


def decode_little_endian_float(s):
    return struct.unpack('<f', s)[0]


def return_enum_decoder(size):
    if size == 4:
        return lambda q: struct.unpack('<l', q)[0]
    elif size == 2:
        return lambda q: struct.unpack('<h', q)[0]
    return ord


def array_decoder(array, elem_decoder, length, elem_size):
    res = '{ '
    for i in range(length):
        elem = elem_decoder(array[i * elem_size: (i + 1) * elem_size])
        if isinstance(elem, float):
            elem_str = "{:.3f}".format(elem)
        else:
            elem_str = "{}".format(elem)
        res += elem_str
        res += ', '
    res = res[:-2]  # throw away last comma
    res += ' }'
    return res


def variable_to_decoder(v, type_name, size):
    # NOTE: function accepts type_name and size as parameters instead of directly getting those from v so that
    # it would be able to call itself recursively with the element of an array
    if type_name.startswith('enum '):
        name_to_val = v.get_enum_dict()
        max_unsigned_val = 1 << (size * 8)
        val_to_name = {v % max_unsigned_val: k for k, v in name_to_val.items()}
        enum_decoder = return_enum_decoder(size)
        return lambda q: val_to_name[enum_decoder(q)]

    elif type_name.startswith('array of '):
        # this currently flattens multi-dimensional arrays to a long one dimensional array
        elem_type = type_name[9:]
        bounds = v.get_array_sizes()
        array_len = reduce(lambda x, y: x * y, bounds)
        elem_size = int(size / array_len)
        assert(elem_size * array_len == size)
        elem_decoder = variable_to_decoder(v=v, type_name=elem_type, size=elem_size)
        return lambda q: array_decoder(array=q, elem_decoder=elem_decoder, length=array_len, elem_size=elem_size)

    elif type_name.endswith('float'):
        if size == 4:
            return decode_little_endian_float

    elif type_name.endswith('bool'):
        return lambda q: 'True' if ord(q) else 'False'

    else:  # TODO this should be "if it's an int". also should handle signed/unsigned correctly
        if size == 4:
            return lambda q: struct.unpack('<l', q)[0]
        elif size == 2:
            return lambda q: struct.unpack('<h', q)[0]
        elif size == 1:
            return ord

    logger.error("type names supported: int, float. looked for: '{}', size = {}".format(type_name, size))
    raise SystemExit


def setup_logging(filename, silent):
    if silent:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.DEBUG)

    if filename:
        file_handler = logging.FileHandler(filename=filename)
        file_handler.setLevel(level=logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    stream_formatter = logging.Formatter('%(message)s')
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level=logging.INFO)
    stream_handler.setFormatter(stream_formatter)

    logger.addHandler(stream_handler)

    logger.debug('debug first')
    logger.info('info first')


def start_serial_process(serial, baudrate, hw_flow_control, port):
    """
    Block until serial2tcp is ready to accept a connection
    """
    serial2tcp_cmd = create_python_process_cmdline('serial2tcp.py')
    if hw_flow_control is True:
        serial2tcp_cmd += ['-r']
    serial2tcp_cmd += ' -b {} -p {} -P {}'.format(baudrate, serial, port).split()

    serial_subprocess = create_process(serial2tcp_cmd)
    return serial_subprocess


def create_python_process_cmdline(script):
    emolog_pc_path = os.path.dirname(os.path.realpath(__file__))
    script_path = os.path.join(emolog_pc_path, script)
    return ['python', script_path]


def create_python_process_cmdline_command(command):
    return ['python', '-c', command]


async def start_transport(client):
    loop = asyncio.get_event_loop()
    port = random.randint(10000, 50000)
    if args.fake:
        await start_fake_sine(args.ticks_per_second, port)
    else:
        start_serial_process(serial=args.serial, baudrate=args.baud, hw_flow_control=args.hw_flow_control, port=port)
    attempt = 0
    while attempt < 10:
        attempt += 1
        sleep(0.1)
        s = socket()
        try:
            s.connect(('127.0.0.1', port))
        except:
            pass
        else:
            s.close()
            break
    client_transport, client2 = await loop.create_connection(lambda: client, '127.0.0.1', port)
    assert client2 is client


args = None
processes = []

def create_process(cmdline):
    print(f"starting subprocess: {cmdline}")
    process = Popen(cmdline)
    processes.append(process)
    return process


def cancel_outstanding_tasks():
    for task in asyncio.Task.all_tasks():
        logger.warning('canceling task {}'.format(task))
        task.cancel()


def windows_try_getch():
    import msvcrt
    if msvcrt.kbhit():
        return msvcrt.getch()
    return None  # be explicit


if sys.platform == 'win32':
    try_getch_message = "Press any key to stop capture early..."
    try_getch = windows_try_getch
else:
    try_getch_message = "Press Ctrl-C to stop capture early..."
    def try_getch():
        return None


async def cleanup(client):
    if not hasattr(client, 'transport') or client.transport is None:
        cancel_outstanding_tasks()
        return
    if not args.no_cleanup:
        logger.info("sending sampler stop")
        try:
            await client.send_sampler_stop()
        except:
            logger.info("exception when sending sampler stop in cleanup()")
    client.exit_gracefully()
    if client.transport is not None:
        client.transport.close()
    for process in processes:
        if hasattr(process, 'send_ctrl_c'):
            process.send_ctrl_c()
        else:
            process.terminate()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Emolog protocol capture tool. Implements emolog client side, captures a given set of variables to a csv file')
    parser.add_argument('--fake', default=False, action='store_true',
                        help='debug only - fake a client - no serial nor elf required')
    parser.add_argument('--serial', default='auto', help='serial port to use')
    parser.add_argument('--baud', default=8000000, help='baudrate, using RS422 up to 12000000 theoretically', type=int)
    parser.add_argument('--hw_flow_control', default=False, action='store_true', help='use CTS/RTS signals for flow control')
    parser.add_argument('--elf', default=None, help='elf executable running on embedded side')
    parser.add_argument('--var', default=[], action='append',
                        help='add a single var, example "foo,1,0" = "varname,ticks,tickphase"')
    parser.add_argument('--snapshotfile', help='file containing variable definitions to be taken once at startup')
    parser.add_argument('--varfile', help='file containing variable definitions, identical to multiple --var calls')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--out', help='Output file name. ".csv" extension is added if missing. '
                                     'File is overwritten if already exists.')
    group.add_argument('--out_prefix', default='emo', help='Output file prefix. Output is saved to the first free '
                                                           '(not already existing) file of the format "prefix_xxx.csv", '
                                                           'where xxx is a sequential number starting from "001"')
    parser.add_argument('--verbose', default=True, action='store_false', dest='silent',
                        help='turn on verbose logging; affects performance under windows')
    parser.add_argument('--log', default=None, help='log messages and other debug/info logs to this file')
    parser.add_argument('--runtime', type=float, default=3.0, help='quit after given seconds')
    parser.add_argument('--no-cleanup', default=False, action='store_true', help='do not stop sampler on exit')
    parser.add_argument('--dump')
    parser.add_argument('--ticks-per-second', default=1000000 / 50, type=float,
                        help='number of ticks per second. used in conjunction with runtime')
    parser.add_argument('--debug', default=False, action='store_true', help='produce more verbose debugging output')
    parser.add_argument('--profile', default=False, action='store_true', help='produce profiling output in profile.txt via cProfile')
    parser.add_argument('--truncate', default=False, action="store_true", help='Only save first 5000 samples for quick debug runs.')
    parser.add_argument('--no-processing', default=False, action="store_true", help="Don't run the post processor after sampling" )
    parser.add_argument('--no_processing', default=False, action="store_true", help="Don't run the post processor after sampling" )

    # GUI
    parser.add_argument('--no-gui', default=True, action='store_false', dest='gui', help='disable graphical user interface')
    parser.add_argument('--no_gui', default=True, action='store_false', dest='gui', help='disable graphical user interface')
    parser.add_argument('--wait-for-gui', default=False, action='store_true', help='wait for user closing the main window before quitting')

    # Embedded
    parser.add_argument('--embedded', default=False, action='store_true', help='debugging: be a fake embedded target')

    ret, unparsed = parser.parse_known_args()

    if not ret.fake:
        if not ret.elf and not ret.embedded:
            # elf required unless fake_sine in effect
            parser.print_usage()
            print(f"{sys.argv[0]}: error: the following missing argument is required: --elf")
            raise SystemExit
    else:
        # fill in fake vars
        ret.var = [
            # name, ticks, phase
            'a,1,0',
            'b,1,0',
            'c,1,0',
            'd,1,0',
            'e,1,0',
            'f,1,0',
            'g,1,0',
            'h,1,0',
        ]
    return ret


def bandwidth_calc(variables):
    """
    :param variables: list of dictionaries
    :return: average baud rate (considering 8 data bits, 1 start & stop bits)
    """
    packets_per_second = args.ticks_per_second # simplification: assume a packet every tick (upper bound)
    header_average = packets_per_second * SamplerSample.empty_size()
    payload_average = sum(args.ticks_per_second / v['period_ticks'] * v['size'] for v in variables)
    return (header_average + payload_average) * 10


class DwarfFakeVariable:
    type_data = {float: dict(type_str='float', size=4)}

    next_address = 0

    @classmethod
    def allocate(cls, size):
        ret = cls.next_address
        cls.next_address += size
        return ret

    def __init__(self, name, type):
        self.type = type
        self.type_str = self.type_data[type]['type_str']
        self.name = name
        size = self.type_data[type]['size']
        self.address = DwarfFakeVariable.allocate(size)
        self.size = size

    def get_type_str(self):
        return self.type_str


def fake_dwarf(names):
    def fake_variable(name):
        return DwarfFakeVariable(name, type=float)
    return {name: fake_variable(name) for name in names}


def read_elf_variables(vars, varfile):
    if varfile is not None:
        with open(varfile) as fd:
            vars = vars + fd.readlines()
    split_vars = [[x.strip() for x in v.split(',')] for v in vars]
    for v, orig in zip(split_vars, args.var):  # TODO: bug - args.var isn't usually relevant
        if len(v) != 3 or not v[1].isdigit() or not v[2].isdigit():
            logger.error("problem with '--var' argument {!r}".format(orig))
            logger.error("--var parameter must be a 3 element comma separated list of: <name>,<period:int>,<phase:int>")
            raise SystemExit
    names = [name for name, ticks, phase in split_vars]
    name_to_ticks_and_phase = {name: (int(ticks), int(phase)) for name, ticks, phase in split_vars}
    if args.elf is None:
        dwarf_variables = fake_dwarf(names)
    else:
        dwarf_variables = dwarf_get_variables_by_name(args.elf, names)  # TODO does this really have to access args?
    if len(dwarf_variables) == 0:
        logger.error("no variables set for sampling")
        raise SystemExit
    variables = []
    for name in names:
        v = dwarf_variables[name]
        period_ticks, phase_ticks = name_to_ticks_and_phase[name]
        variables.append(dict(
            name=name,
            phase_ticks=phase_ticks,
            period_ticks=period_ticks,
            address=v.address,
            size=v.size,
            _type=variable_to_decoder(v=v, type_name=v.get_type_str(), size=v.size)))
    return names, variables


async def initialize_board(client, variables):
    logger.debug("about to send version")
    await client.send_version()
    retries = max_retries = 3
    while retries > 0:
        try:
            logger.debug("about to send sampler stop")
            await client.send_sampler_stop()
            logger.debug("about to send sampler set variables")
            await client.send_set_variables(variables)
            logger.debug("about to send sampler start")
            await client.send_sampler_start()
            logger.debug("client initiated, starting to log data at rate TBD")
            break
        except AckTimeout:
            retries -= 1
            logger.info("Ack Timeout. Retry {}".format(max_retries - retries))
    return retries != 0


def banner(s):
    print("=" * len(s))
    print(s)
    print("=" * len(s))


async def init_client(verbose, dump, window):
    client = EmoToolClient(verbose=verbose, dump=dump, window=window)
    await start_transport(client=client)
    return client


async def run_client(client, variables, allow_kb_stop):
    if not await initialize_board(client=client, variables=variables):
        logger.error("Failed to initialize board, exiting.")
        raise SystemExit
    sys.stdout.flush()
    logger.info('initialized board')

    dt = 0.1 if args.runtime is not None else 1.0
    if allow_kb_stop and try_getch_message:
        print(try_getch_message)
    while client.running:
        logger.info('beep')
        if allow_kb_stop and try_getch():
            break
        await asyncio.sleep(dt)
    await client.send_sampler_stop()


async def record_snapshot(client, csvfile, varsfile):
    names, variables = read_elf_variables(vars=[], varfile=varsfile)
    client.reset(csv_filename=csvfile, names=names, min_ticks=1, max_ticks=0)
    await run_client(client, variables, allow_kb_stop=False)


CONFIG_FILE_NAME = 'local_machine_config.ini'

async def amain(window):
    if not os.path.exists(CONFIG_FILE_NAME):
        print("Configuration file {} not found. "
              "This file is required for specifying local machine configuration such as the output folder.\n"
              "Please start from the example {}.example.\n"
              "Exiting.".format(CONFIG_FILE_NAME, CONFIG_FILE_NAME))
        raise SystemExit

    config = ConfigParser()
    config.read(CONFIG_FILE_NAME)

    setup_logging(args.log, args.silent)

    # TODO - fold this into window, make it the general IO object, so it decided to spew to stdout or to the GUI
    banner("Emotool {}".format(version()))

    names, variables = read_elf_variables(vars=args.var, varfile=args.varfile)

    output_folder = config['folders']['output_folder']
    if args.out:
        if args.out[-4:] != '.csv':
            args.out = args.out + '.csv'
        csv_filename = os.path.join(output_folder, args.out)
    else:   # either --out or --out_prefix must be specified
        csv_filename = next_available(output_folder, args.out_prefix)

    client = await init_client(verbose=not args.silent, dump=args.dump, window=window)
    logger.info('Client initialized')

    if args.snapshotfile:
        print("Taking snapshot of parameters")
        snapshot_output_filename = csv_filename[:-4] + '_params.csv'
        await record_snapshot(client=client, csvfile=snapshot_output_filename, varsfile=args.snapshotfile)
        print("parameters saved to: {}".format(snapshot_output_filename))

    print("")
    print("output file: {}".format(csv_filename))
    bandwidth_bps = bandwidth_calc(variables)
    print("upper bound on bandwidth: {} Mbps out of {} ({:.3f}%)".format(
        bandwidth_bps / 1e6,
        args.baud / 1e6,
        100 * bandwidth_bps / args.baud))
    max_ticks = args.ticks_per_second * args.runtime if args.runtime else None
    if max_ticks is not None:
        print("running for {} seconds = {} ticks".format(args.runtime, int(max_ticks)))
    min_ticks = min(var['period_ticks'] for var in variables)  # this is wrong, use gcd

    client.reset(csv_filename=csv_filename, names=names, min_ticks=min_ticks, max_ticks=max_ticks)
    start_time = time()
    await run_client(client=client, variables=variables, allow_kb_stop=True)

    logger.debug("stopped at time={} ticks={}".format(time(), client.total_ticks))
    total_time = time() - start_time
    print(f"samples received: {client.samples_received}\nticks lost: {client.ticks_lost}\ntime run {total_time}")
    return client


def start_gui(args):
    return run_forever(start_gui_callback, create_main_window=args.gui)


def start_gui_callback(loop, window):
    global args
    loop.set_debug(args.debug)

    def call_main():
        loop.run_until_complete(amain(window))

    if args.profile:
        import cProfile as profile
        profile.runctx("call_main()", globals(), locals(), "profile.txt")
    else:
        try:
            call_main()
        except KeyboardInterrupt:
            print("exiting on user ctrl-c")
        except Exception as e:
            logger.error("got exception {!r}".format(e))
    client = EmoToolClient.instance
    loop.run_until_complete(cleanup(client))
    if args.wait_for_gui:
        async def sleep_forever():
            while True:
                await asyncio.sleep(1000)
        loop.run_until_complete(sleep_forever())
    return client


def do_post_process(args, client):
    if client.csv_filename is None or not os.path.exists(client.csv_filename):
        print("no csv file created, exiting before post processing")
        return
    print()
    if args.no_processing is False:
        print("Running post processor (this may take some time)...")
        print("processing {}".format(client.csv_filename))
        post_process(client.csv_filename, truncate_data=args.truncate, verbose=True)
        print("Post processing done.")
    else:
        print("No post-processing was requested, exiting.")


def main(cmdline=None):
    global args # TODO - remove this global, pass explicitly
    if cmdline is not None:
        sys.argv = cmdline
    args = parse_args()
    if args.embedded:
        from .embedded import main as embmain
        embmain()
    client = start_gui(args)
    do_post_process(args, client)


if __name__ == '__main__':
    main()