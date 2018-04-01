#!/bin/env python3

# import os
# os.environ['PYTHONASYNCIODEBUG'] = '1'
# import logging
# logging.getLogger('asyncio').setLevel(logging.DEBUG)

from datetime import datetime
import traceback
import atexit
import argparse
import os
from os import path
import sys
import logging
from struct import pack
import random
from time import time, sleep, clock
from socket import socket
from configparser import ConfigParser
from shutil import which
from asyncio import sleep, Protocol, get_event_loop, Task
from pickle import dumps
import csv

from ..consts import BUILD_TIMESTAMP_VARNAME
from ..util import version, resolve, create_process, kill_all_processes, gcd
from ..util import verbose as util_verbose
from ..lib import AckTimeout, ClientProtocolMixin, SamplerSample
from ..varsfile import merge_vars_from_file_and_list
from ..dwarfutil import read_elf_variables


logger = logging.getLogger()


module_dir = os.path.dirname(os.path.realpath(__file__))
pc_dir = os.path.join(module_dir, '..', '..', '..', 'examples', 'pc_platform')
pc_executable = os.path.join(pc_dir, 'pc')


def start_fake_bench(port):
    return start_fake_sine(ticks_per_second=0, port=port)


def start_fake_sine(ticks_per_second, port, build_timestamp_value):
    # Run in a separate process so it doesn't hog the CPython lock
    # Use our executable to work with a development environment (python executable)
    # or pyinstaller (emotool.exe)
    if sys.argv[0].endswith(path.basename(get_python_executable())):
        cmdline = sys.argv[:2]
    elif path.isfile(sys.argv[0]) or path.isfile(sys.argv[0] + '.exe'):
        cmdline = [sys.argv[0]]
    elif which(sys.argv[0]):
        cmdline = [sys.argv[0]]
    # force usage of python if the first parameter is a python script; use extension as predicate
    if cmdline[0].endswith('.py'):
        cmdline = [get_python_executable()] + cmdline
    #print(f"{sys.argv!r} ; which said {which(sys.argv[0])}")
    return create_process(cmdline + ['--embedded', '--ticks-per-second', str(ticks_per_second), '--port', str(port),
                                     '--build-timestamp-value', str(build_timestamp_value)])


def start_pc(port, exe, debug):
    exe = os.path.realpath(exe)
    cmdline = [exe, str(port)]
    cmdline_str = ' '.join(cmdline)
    debug_cmdline = f'EMOLOG_PC_PORT={port} cgdb --args {cmdline_str}'
    os.environ['EMOLOG_PC_PORT'] = str(port)
    if debug:
        input(f"press enter once you ran pc with: {debug_cmdline}")
        return
    return create_process(cmdline)


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


def start_serial_process(serialurl, baudrate, hw_flow_control, port):
    """
    Block until serial2tcp is ready to accept a connection
    """
    serial2tcp_cmd = create_python_process_cmdline('serial2tcp.py')
    if hw_flow_control is True:
        serial2tcp_cmd += ['-r']
    serial2tcp_cmd += ' -b {} -p {} -P {}'.format(baudrate, serialurl, port).split()

    serial_subprocess = create_process(serial2tcp_cmd)
    return serial_subprocess


def get_python_executable():
    if 'win' in sys.platform:
        return 'python'
    return 'python3'


def create_python_process_cmdline(script):
    script_path = os.path.join(module_dir, script)
    return [get_python_executable(), script_path]


def create_python_process_cmdline_command(command):
    return [get_python_executable(), '-c', command]


class EmoToolClient(ClientProtocolMixin):

    def __init__(self, ticks_per_second, verbose, dump, debug, csv_writer_factory=None):
        if debug:
            print("timeout set to one hour for debugging (gdb)")
            ClientProtocolMixin.ACK_TIMEOUT_SECONDS = 3600.0
        super().__init__(verbose=verbose, dump=dump,
            ticks_per_second=ticks_per_second,
            csv_writer_factory=csv_writer_factory)

    @property
    def running(self):
        return self.cylib.running()

    @property
    def ticks_lost(self):
        return self.cylib.csv_handler.ticks_lost

    @property
    def samples_received(self):
        return self.cylib.csv_handler.samples_received

    @property
    def csv_filename(self):
        return self.cylib.csv_handler.csv_filename

    def reset(self, *args, **kw):
        self.last_samples_received = None  # don't trigger the check_progress() watchdog on the next sample
        self.cylib.csv_handler.reset(*args, **kw)

    def register_listener(self, *args, **kw):
        self.cylib.csv_handler.register_listener(*args, **kw)

    def data_received(self, data):
        self.cylib.data_received(data)


async def start_transport(client, args):
    loop = get_event_loop()
    port = random.randint(10000, 50000)
    if args.fake is not None:
        if args.fake == 'gen':
            start_fake_sine(ticks_per_second=args.ticks_per_second, port=port, build_timestamp_value=args.fake_gen_build_timestamp_value)
        elif args.fake == 'bench':
            start_fake_bench(port)
        elif args.fake == 'pc' or os.path.exists(args.fake):
            exe = pc_executable if args.fake == 'pc' else args.fake
            start_pc(port=port, exe=exe, debug=args.debug)
        else:
            print(f"error: unfinished support for fake {args.fake}")
            raise SystemExit
    else:
        start_serial_process(serialurl=args.serial, baudrate=args.baud, hw_flow_control=args.hw_flow_control, port=port)
    attempt = 0
    while attempt < 10:
        attempt += 1
        await sleep(0.1)
        s = socket()
        try:
            s.connect(('127.0.0.1', port))
        except:
            pass
        else:
            break
    client_transport, client2 = await loop.create_connection(lambda: client, sock=s)
    assert client2 is client


args = None


def cancel_outstanding_tasks():
    for task in Task.all_tasks():
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


async def cleanup(args, client):
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
    kill_all_processes()



def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description='Emolog protocol capture tool. Implements emolog client side, captures a given set of variables to a csv file')
    parser.add_argument('--fake', # TODO: can I have a hook for choices? i.e. choices=ChoicesOrExecutable['gen', 'pc', 'bench'],
                        help='debug only - fake a client - either generated or pc controller')
    now_timestamp = int(datetime.utcnow().timestamp() * 1000)
    parser.add_argument('--fake-elf-build-timestamp-value', type=int, default=now_timestamp, help='debug only - fake build timestamp value (address is fixed)')
    parser.add_argument('--fake-gen-build-timestamp-value', type=int, default=now_timestamp, help='debug only - fake build timestamp value (address is fixed)')
    parser.add_argument('--serial', default='auto', help='serial URL or device name') # see http://pythonhosted.org/pyserial/pyserial_api.html#serial.serial_for_url
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

    parser.add_argument('--csv-factory', help='advanced: module[.module]*.function to use as factory for csv file writing', default=None)

    parser.add_argument('--verbose', default=True, action='store_false', dest='silent',
                        help='turn on verbose logging; affects performance under windows')
    parser.add_argument('--verbose-kill', default=False, action='store_true')
    parser.add_argument('--log', default=None, help='log messages and other debug/info logs to this file')
    parser.add_argument('--runtime', type=float, default=3.0, help='quit after given seconds. use 0 for endless run.')
    parser.add_argument('--no-cleanup', default=False, action='store_true', help='do not stop sampler on exit')
    parser.add_argument('--dump')
    parser.add_argument('--ticks-per-second', default=1000000 / 50, type=float,
                        help='number of ticks per second. used in conjunction with runtime')
    parser.add_argument('--debug', default=False, action='store_true', help='produce more verbose debugging output')

    # Server - used for GUI access
    parser.add_argument('--listen', default=None, type=int, help='enable listening TCP port for samples') # later: add a command interface, making this suitable for interactive GUI
    parser.add_argument('--gui', default=False, action='store_true', help='launch graphing gui in addition to saving')

    # Embedded
    parser.add_argument('--embedded', default=False, action='store_true', help='debugging: be a fake embedded target')

    parser.add_argument('--check-timestamp', action='store_true', default=False, help='wip off by default for now')

    ret, unparsed = parser.parse_known_args(args=args)

    if ret.fake is None:
        if not ret.elf and not ret.embedded:
            # elf required unless fake_sine in effect
            parser.print_usage()
            print(f"{sys.argv[0]}: error: the following missing argument is required: --elf")
            raise SystemExit
    else:
        if ret.fake == 'gen':
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
        else:
            if ret.elf is None:
                if ret.fake == 'pc':
                    if not os.path.exists(pc_executable):
                        print(f"missing pc ELF file: {pc_executable}")
                        raise SystemExit
                    ret.elf = pc_executable
                else:
                    ret.elf = ret.fake
            if ret.varfile is None:
                ret.varfile = os.path.join(module_dir, '..', '..', 'vars.csv')
                ret.snapshotfile = os.path.join(module_dir, '..', '..', 'snapshot_vars.csv')
    return ret


def bandwidth_calc(args, variables):
    """
    :param variables: list of dictionaries
    :return: average baud rate (considering 8 data bits, 1 start & stop bits)
    """
    packets_per_second = args.ticks_per_second # simplification: assume a packet every tick (upper bound)
    header_average = packets_per_second * SamplerSample.empty_size()
    payload_average = sum(args.ticks_per_second / v['period_ticks'] * v['size'] for v in variables)
    return (header_average + payload_average) * 10


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


async def run_client(args, client, variables, allow_kb_stop):
    if not await initialize_board(client=client, variables=variables):
        logger.error("Failed to initialize board, exiting.")
        raise SystemExit
    sys.stdout.flush()
    logger.info('initialized board')

    dt = 0.1 if args.runtime is not None else 1.0
    if allow_kb_stop and try_getch_message:
        print(try_getch_message)
    client.start_logging_time = time()
    while client.running:
        if allow_kb_stop and try_getch():
            break
        await sleep(dt)
    await client.send_sampler_stop()


async def record_snapshot(args, client, csv_filename, varsfile, extra_vars=None):
    if extra_vars is None:
        extra_vars = []
    defs = merge_vars_from_file_and_list(filename=varsfile, def_lines=extra_vars)
    names, variables = read_elf_variables(elf=args.elf, defs=defs, fake_build_timestamp=args.fake_elf_build_timestamp_value)
    elf_by_name = {x['name']: x for x in variables}
    client.reset(csv_filename=csv_filename, names=names, min_ticks=1, max_samples=1)
    await run_client(args, client, variables, allow_kb_stop=False)
    read_values = {}
    try:
        with open(csv_filename) as fd:
            lines = list(csv.reader(fd))
    except IOError as io:
        logger.warning("snapshot failed, no file created")
        lines = []
    if len(lines) < 2:
        logger.warning("snapshot failed, no data saved")
    else:
        read_values = dict(zip(lines[0], lines[1]))
    return elf_by_name, read_values


CONFIG_FILE_NAME = 'local_machine_config.ini'


class SamplePassOn(Protocol):
    def __init__(self, client):
        self.client = client

    def connection_made(self, transport):
        self.transport = transport
        self.client.register_listener(self.write_messages)

    def write_messages(self, messages):
        pickled_messages = dumps(messages)
        self.transport.write(pack('<i', len(pickled_messages)))
        self.transport.write(pickled_messages)


async def start_tcp_listener(client, port):
    loop = get_event_loop()
    await loop.create_server(lambda: SamplePassOn(client), host='localhost', port=port)
    print(f"waiting on {port}")


async def amain_startup(args):
    if not os.path.exists(CONFIG_FILE_NAME):
        print("Configuration file {} not found. "
              "This file is required for specifying local machine configuration such as the output folder.\n"
              "Please start from the example {}.example.\n"
              "Exiting.".format(CONFIG_FILE_NAME, CONFIG_FILE_NAME))
        raise SystemExit

    setup_logging(args.log, args.silent)

    # TODO - fold this into window, make it the general IO object, so it decided to spew to stdout or to the GUI
    banner("Emotool {}".format(version()))

    client = EmoToolClient(ticks_per_second=args.ticks_per_second,
        verbose=not args.silent, dump=args.dump, debug=args.debug,
        csv_writer_factory=resolve(args.csv_factory))
    await start_transport(client=client, args=args)
    return client


def check_timestamp(params, elf_variables):
    if BUILD_TIMESTAMP_VARNAME not in params:
        logger.error(f'timestamp not received from target')
        raise SystemExit
    read_value = int(params[BUILD_TIMESTAMP_VARNAME])
    if BUILD_TIMESTAMP_VARNAME not in elf_variables:
        logger.error(f'Timestamp variable not in ELF file. Did you add a pre-build step to generate it?')
        raise SystemExit
    elf_var = elf_variables[BUILD_TIMESTAMP_VARNAME]
    elf_value = elf_var['init_value']
    if elf_value is None or elf_var['address'] == 0:
        logger.error(f'Bad timestamp variable in ELF: init value = {elf_value}, address = {elf_var["address"]}')
        raise SystemExit
    elf_value = int(elf_variables[BUILD_TIMESTAMP_VARNAME]['init_value'])
    if read_value != elf_value:
        if read_value < elf_value:
            logger.error('target build timestamp is older than ELF')
        else:
            logger.error('target build timestamp is newer than ELF')
        raise SystemExit


async def amain(client, args):
    defs = merge_vars_from_file_and_list(def_lines=args.var, filename=args.varfile)
    names, variables = read_elf_variables(elf=args.elf, defs=defs)

    config = ConfigParser()
    config.read(CONFIG_FILE_NAME)

    output_folder = config['folders']['output_folder']
    if args.out:
        if args.out[-4:] != '.csv':
            args.out = args.out + '.csv'
        csv_filename = os.path.join(output_folder, args.out)
    else:   # either --out or --out_prefix must be specified
        csv_filename = next_available(output_folder, args.out_prefix)

    take_snapshot = args.check_timestamp or args.snapshotfile
    if take_snapshot:
        print("Taking snapshot of parameters")
        snapshot_output_filename = csv_filename[:-4] + '_params.csv'
        (snapshot_elf_variables, params) = await record_snapshot(
            args=args, client=client,
            csv_filename=snapshot_output_filename,
            varsfile=args.snapshotfile,
            # TODO: why do we use 20000 in snapshot_vars.csv? ask Guy
            extra_vars = [f'{BUILD_TIMESTAMP_VARNAME},20000,1'] if args.check_timestamp else [])
        print("parameters saved to: {}".format(snapshot_output_filename))

        if args.check_timestamp:
            check_timestamp(params, snapshot_elf_variables)

    print("")
    print("output file: {}".format(csv_filename))
    bandwidth_bps = bandwidth_calc(args=args, variables=variables)
    print("upper bound on bandwidth: {} Mbps out of {} ({:.3f}%)".format(
        bandwidth_bps / 1e6,
        args.baud / 1e6,
        100 * bandwidth_bps / args.baud))
    max_samples = args.ticks_per_second * args.runtime if args.runtime else 0 # TODO - off by a factor of at least min_ticks_between_samples
    if max_samples > 0:
        print("running for {} seconds = {} samples".format(args.runtime, int(max_samples)))
    min_ticks = gcd(*(var['period_ticks'] for var in variables))

    client.reset(csv_filename=csv_filename, names=names, min_ticks=min_ticks, max_samples=max_samples)
    if args.listen:
        await start_tcp_listener(client, args.listen)

    start_time = time()
    start_clock = clock()
    await run_client(args=args, client=client, variables=variables, allow_kb_stop=True)

    logger.debug("stopped at time={} samples={}".format(time(), client.samples_received))
    setup_time = client.start_logging_time - start_time
    total_time = time() - start_time
    total_clock = clock() - start_clock
    print(f"samples received: {client.samples_received}\nticks lost: {client.ticks_lost}\ntime run {total_time:#3.6} cpu %{int(total_clock * 100 /total_time)} (setup time {setup_time:#3.6})")
    return client


def start_callback(args, loop):
    loop.set_debug(args.debug)

    try:
        client = loop.run_until_complete(amain_startup(args))
    except:
        traceback.print_exc()
        raise SystemExit
    try:
        client = loop.run_until_complete(amain(client=client, args=args))
    except KeyboardInterrupt:
        print("exiting on user ctrl-c")
    except Exception as e:
        logger.error("got exception {!r}".format(e))
        raise
    loop.run_until_complete(cleanup(args=args, client=client))
    return client


def main(cmdline=None):
    atexit.register(kill_all_processes)
    parse_args_args = [] if cmdline is None else [cmdline]
    args = parse_args(*parse_args_args)
    util_verbose.kill = args.verbose_kill
    if args.embedded:
        from .embedded import main as embmain
        embmain()
    else:
        loop = get_event_loop()
        def exception_handler(loop, context):
            print(f"Async Exception caught: {context}")
            raise SystemExit
        loop.set_exception_handler(exception_handler)
        client = start_callback(args, loop)
        if client.csv_filename is None or not os.path.exists(client.csv_filename):
            print("no csv file created.")


if __name__ == '__main__':
    main()
