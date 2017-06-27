#!/bin/env python

# import os
# os.environ['PYTHONASYNCIODEBUG'] = '1'
# import logging
# logging.getLogger('asyncio').setLevel(logging.DEBUG)

import argparse
import configparser
import asyncio
import csv
import logging
import os
import random
import string
import struct
import sys
from socket import socketpair
from subprocess import Popen
from time import sleep, clock  # more accurate on windows, vs time.time on linux

import emolog
import post_processor
from dwarf import FileParser

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


def dwarf_get_variables_by_name(filename, names, verbose):
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
        logger.debug("candidate {}".format(v_name))
        if v_name in names:
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


async def start_fake_sine():
    loop = asyncio.get_event_loop()
    rsock, wsock = socketpair()
    await loop.create_connection(emolog.FakeSineEmbedded, sock=rsock)
    return wsock


class EmoToolClient(emolog.Client):
    instance = None

    def __init__(self, csv_filename, verbose, names, dump, min_ticks,
                 max_ticks):
        super(EmoToolClient, self).__init__(verbose=verbose, dump=dump)
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
        EmoToolClient.instance = self  # ugly reference for KeboardInterrupt handling

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

    def handle_sampler_sample(self, msg):
        if not self.running:
            return
        self.initialize_file()
        # todo - decode variables (integer/float) in emolog VariableSampler
        vs = msg.variables
        self.csv.writerow([msg.seq, msg.ticks, clock() * 1000] +
                          [vs[name] if name in vs else '' for name in self.names])
        self.fd.flush()
        self.samples_received += 1
        if self.last_ticks is not None and msg.ticks - self.last_ticks != self.min_ticks:
            print("{:8.5}: ticks jump {:6} -> {:6} [{:6}]".format(
                clock(), self.last_ticks, msg.ticks, msg.ticks - self.last_ticks))
            self.ticks_lost += msg.ticks - self.last_ticks - self.min_ticks
        self.last_ticks = msg.ticks
        if self.first_ticks is None:
            self.first_ticks = self.last_ticks
        if self.max_ticks and self.total_ticks + 1 >= self.max_ticks:
            self.stop()


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


def variable_to_decoder(v):
    type_name = v.get_type_str()
    size = v.size
    if type_name.startswith('enum '):
        name_to_val = v.get_enum_dict()
        max_unsigned_val = 1 << (size * 8)
        val_to_name = {v % max_unsigned_val: k for k, v in name_to_val.items()}
        enum_decoder = return_enum_decoder(size)
        return lambda q: val_to_name[enum_decoder(q)]
    elif type_name.endswith('float'):
        if size == 4:
            return decode_little_endian_float
    # might be broken since s which is dwarf.dwarf.VarDescriptor.get_type_name()
    # doesn't necessarily end with 'int' / 'float'
    else:
        # Note: will support both int and enum
        if size == 4:
            return lambda q: struct.unpack('<l', q)[0]
        elif size == 2:
            return lambda q: struct.unpack('<h', q)[0]
        elif size == 1:
            return ord
    logger.error("type names supported: int, float. looked for: {}, {}".format(s, size))
    raise SystemExit


def an_int(x):
    try:
        b = int(x)
    except:
        return False
    return True


def setup_logging(filename, silent):
    if silent:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.DEBUG)

    if filename:
        fileHandler = logging.FileHandler(filename=filename)
        fileHandler.setLevel(level=logging.DEBUG)
        fileFormatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fileHandler.setFormatter(fileFormatter)
        logger.addHandler(fileHandler)

    streamFormatter = logging.Formatter('%(message)s')
    streamHandler = logging.StreamHandler()
    streamHandler.setLevel(level=logging.INFO)
    streamHandler.setFormatter(streamFormatter)

    logger.addHandler(streamHandler)

    logger.debug('debug first')
    logger.info('info first')


def start_subprocess(serial, baudrate, port):
    """
    Block until serial2tcp is ready to accept a connection
    """
    p = Popen('python serial2tcp.py -r -b {} -p {} -P {}'.format(
        baudrate, serial, port).split())
    sleep(0.1)
    return p


async def start_transport(args, client, serial_process):
    loop = asyncio.get_event_loop()
    if args.fake_sine:
        client_end = await start_fake_sine()
        client_transport, client = await loop.create_connection(lambda: client, sock=client_end)
        return
    port = random.randint(10000, 50000)
    serial_process[0] = start_subprocess(serial=args.serial, baudrate=args.baud, port=port)
    client_transport, client2 = await loop.create_connection(lambda: client, '127.0.0.1', port)
    assert client2 is client


args = None
serial_process = [None]


def cancel_outstanding_tasks():
    for task in asyncio.Task.all_tasks():
        logger.warn('canceling task {}'.format(task))
        task.cancel()


def windows_try_getch():
    import msvcrt
    if msvcrt.kbhit():
        return msvcrt.getch()
    return None  # be explicit


if sys.platform == 'win32':
    try_getch_message = 'Press any key to exit'
    try_getch = windows_try_getch
else:
    try_getch_message = "Press Ctrl-C to exit"
    def try_getch():
        return None


async def cleanup(client):
    if not hasattr(client, 'transport'):
        cancel_outstanding_tasks()
        return
    if not args.no_cleanup:
        logger.debug("sending sampler stop")
        try:
            await client.send_sampler_stop()
        except:
            pass
    client.exit_gracefully()
    if client.transport is not None:
        client.transport.close()
    if serial_process[0] is not None:
        p = serial_process[0]
        if hasattr(p, 'send_ctrl_c'):
            p.send_ctrl_c()
        else:
            p.terminate()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Emolog protocol capture tool. Implements emolog client side, captures a given set of variables to a csv file')
    parser.add_argument('--fake-sine', default=False, action='store_true',
                        help='debug only - use a fake sine producing client')
    parser.add_argument('--serial', default='auto', help='serial port to use')
    parser.add_argument('--elf', default=None, required=True, help='elf executable running on embedded side')
    parser.add_argument('--var', default=[], action='append',
                        help='add a single var, example "foo,float,1,0" = "varname,vartype,ticks,tickphase"')
    parser.add_argument('--varfile', help='file containing variable definitions, identical to multiple --var calls')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--out', help='Output file name. ".csv" extension is added if missing. '
                                     'File is overwritten if already exists.')
    group.add_argument('--out_prefix', default='emo', help='Output file prefix. Output is saved to the first free '
                                                           '(not already existing) file of the format "prefix_xxx.csv", '
                                                           'where xxx is a sequential number starting from "001"')
    parser.add_argument('--verbose', default=True, action='store_false', dest='silent',
                        help='turn on verbose logging; affects performance under windows')
    parser.add_argument('--log', default=None, help='log messages and other debug/info logs here')
    parser.add_argument('--runtime', type=float, default=3.0, help='quit after given seconds')
    parser.add_argument('--baud', default=8000000, help='baudrate, using RS422 up to 12000000 theoretically', type=int)
    parser.add_argument('--no-cleanup', default=False, action='store_true', help='do not stop sampler on exit')
    parser.add_argument('--dump')
    parser.add_argument('--ticks-per-second', default=1000000 / 50,
                        help='number of ticks per second. used in conjunction with runtime')
    parser.add_argument('--debug', default=False, action='store_true', help='produce more verbose debugging output')
    parser.add_argument('--profile', default=False, action='store_true', help='produce profiling output in profile.txt via cProfile')
    return parser.parse_args()


def bandwidth_calc(variables):
    """
    :param variables: list of dictionaries
    :return: average baud rate (considering 8 data bits, 1 start & stop bits)
    """
    packets_per_second = args.ticks_per_second # simplification: assume a packet every tick (upper bound)
    header_average = packets_per_second * emolog.SamplerSample.empty_size()
    payload_average = sum(args.ticks_per_second / v['period_ticks'] * v['size'] for v in variables)
    return (header_average + payload_average) * 10


def read_elf_variables(vars, varfile):
    if varfile is not None:
        with open(varfile) as fd:
            vars = vars + fd.readlines()
    split_vars = [[x.strip() for x in v.split(',')] for v in vars]
    for v, orig in zip(split_vars, args.var):
        if len(v) != 3 or not an_int(v[1]) or not an_int(v[2]):
            logger.error("problem with '--var' argument {!r}".format(orig))
            logger.error("--var parameter must be a 4 element comma separated list of: <name>,<period:int>,<phase:int>")
            raise SystemExit
    names = [name for name, ticks, phase in split_vars]
    name_to_ticks_and_phase = {name: (int(ticks), int(phase)) for name, ticks, phase in split_vars}
    dwarf_variables = dwarf_get_variables_by_name(args.elf, names, verbose=not args.silent)
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
            _type=variable_to_decoder(v)))
    return names, variables


async def initialize_client(args, client, serial_process, variables):
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
        except emolog.AckTimeout:
            retries -= 1
            logger.debug("retry {}".format(max_retries - retries))
    return retries != 0


CONFIG_FILE_NAME = 'local_machine_config.ini'
async def amain():
    global serial_process

    if os.path.exists(CONFIG_FILE_NAME):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE_NAME)
    else:
        print("Configuration file {} not found. "
              "This file is required for specifying local machine configuration such as the output folder."
              "\nExiting.".format(CONFIG_FILE_NAME))
        raise SystemExit

    setup_logging(args.log, args.silent)

    names, variables = read_elf_variables(vars=args.var, varfile=args.varfile)

    if args.out:
        if args.out[-4:] != '.csv':
            args.out = args.out + '.csv'
        csv_filename = os.path.join(config['folders']['output_folder'], args.out)
    else:   # either --out or --out_prefix must be specified
        csv_filename = next_available(config['folders']['output_folder'], args.out_prefix)

    print("================")
    print("Emotool starting")
    print("================")
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

    client = EmoToolClient(csv_filename=csv_filename, verbose=not args.silent, names=names, dump=args.dump,
                           min_ticks=min_ticks, max_ticks=max_ticks)
    await start_transport(args=args, client=client, serial_process=serial_process)
    if not await initialize_client(args=args, client=client, serial_process=serial_process, variables=variables):
        print("failed to initialize board, exiting.")
        raise SystemExit
    sys.stdout.flush()

    dt = 0.1 if args.runtime is not None else 1.0
    if try_getch_message:
        print(try_getch_message)
    while client.running:
        if try_getch():
            break
        await asyncio.sleep(dt)
    logger.debug("stopped at clock={} ticks={}".format(clock(), client.total_ticks))
    print("samples received: {}\nticks lost: {}".format(client.samples_received, client.ticks_lost))


def main():
    global args
    args = parse_args()

    loop = asyncio.get_event_loop()
    loop.set_debug(args.debug)

    def call_main():
        loop.run_until_complete(amain())

    if args.profile:
        import cProfile as profile
        profile.runctx("call_main()", globals(), locals(), "profile.txt")
        #import vprof.runner as runner
        #runner.run(call_main, 'cmhp')
    else:
        try:
            call_main()
        except KeyboardInterrupt:
            print("exiting on user ctrl-c")
        except Exception as e:
            logger.debug("got exception {!r}".format(e))
    client = EmoToolClient.instance
    loop.run_until_complete(cleanup(client))
    if not os.path.exists(client.csv_filename):
        print("no csv file created, exiting before post processing")
        return
    print("Running post processor (this may take some time)...")
    post_processor.post_process(client.csv_filename)
    print("Post processing done.")


if __name__ == '__main__':
    main()
