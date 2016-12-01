#!/bin/env python

# import os
# os.environ['PYTHONASYNCIODEBUG'] = '1'
# import logging
# logging.getLogger('asyncio').setLevel(logging.DEBUG)

from time import sleep, clock  # more accurate on windows, vs time.time on linux
import sys
import os
import csv
import struct
import asyncio
import argparse
import string
from socket import socketpair
import logging
import subprocess

from dwarf import FileParser
import emolog

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


async def start_fake_sine(port=None):
    loop = asyncio.get_event_loop()
    if port is None:
        rsock, wsock = socketpair()
        await loop.create_connection(emolog.FakeSineEmbedded, sock=rsock)
    else:
        wsock = None
        await loop.create_server(emolog.FakeSineEmbedded, '127.0.0.1', port)
    return wsock


class EmoToolClient(emolog.Client):
    def __init__(self, csv, fd, verbose, names, dump, min_ticks):
        super(EmoToolClient, self).__init__(verbose=verbose, dump=dump)
        self.csv = csv
        self.fd = fd
        self.csv.writerow(['sequence', 'ticks', 'timestamp'] + names)
        self.last_ticks = None
        self.min_ticks = min_ticks
        self.client = self # ugly reference for KeboardInterrupt handling

    def handle_sampler_sample(self, msg):
        # todo - decode variables (integer/float) in emolog VariableSampler
        self.csv.writerow([msg.seq, msg.ticks, clock() * 1000] + msg.variables)
        self.fd.flush()
        if self.last_ticks is not None and msg.ticks - self.last_ticks != self.min_ticks:
            print("{:8.5}: ticks jump {:6} -> {:6} [{:6}]".format(clock(), self.last_ticks, msg.ticks, msg.ticks - self.last_ticks))
        self.last_ticks = msg.ticks


def iterate(filename, initial, firstoption):
    if firstoption is not None:
        if firstoption[-4:] != '.csv':
            yield '{}.csv'.format(firstoption)
        else:
            yield firstoption
    if filename[-4:] == '.csv':
        filename = filename[:-4]
    while True:
        yield '{}_{:03}.csv'.format(filename, initial)
        initial += 1


def next_available(filename, numbered):
    filenames = iterate(filename, 1, filename if numbered is None else None)
    for filename in filenames:
        if not os.path.exists(filename):
            return filename


def decode_little_endian_float(s):
    return struct.unpack('<f', s)[0]


def str_size_to_decoder(s, size):
    if s.endswith('float'):
        if size == 4:
            return decode_little_endian_float
    else:  # might be broken since s which is dwarf.dwarf.VarDescriptor.get_type_name() doesn't necessarily end with 'int' / 'float'
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

    fileHandler = logging.FileHandler(filename=filename)
    fileHandler.setLevel(level=logging.DEBUG)
    fileFormatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fileHandler.setFormatter(fileFormatter)

    streamFormatter = logging.Formatter('%(message)s')
    streamHandler = logging.StreamHandler()
    streamHandler.setLevel(level=logging.INFO)
    streamHandler.setFormatter(streamFormatter)

    logger.addHandler(fileHandler)
    logger.addHandler(streamHandler)

    logger.debug('debug first')
    logger.info('info first')


def start_subprocess(serial, baudrate, port):
    """
    Block until serial2tcp is ready to accept a connection
    """
    p = subprocess.Popen(['python', 'serial2tcp.py', '-r', '-b', str(baudrate),
                             '-p', str(serial), '-P', str(port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    line = None
    while line != 'Waiting for connection...':
        sleep(0.1)
        line = p.stdout.readline().strip()
        if b'CRITICAL' in line:
            print("oh noes! error talking to serial:\n{}".format(line))
            raise SystemExit
        if p.returncode is not None: # process exited, something is wrong
            print("process exited! returncode {}".format(t.returncode))
            raise SystemExit
        if line != b'':
            print("got {}".format(repr(line)))
    return p

async def start_transport(args, client, serial_process):
    loop = asyncio.get_event_loop()
    if not args.direct:
        serial_process[0] = start_subprocess(serial=args.serial, baudrate=args.baud, port=args.port)
        print("TODO - wait for socket availability")
        #await asyncio.sleep(0.5)
        client_transport, client2 = await loop.create_connection(lambda: client, '127.0.0.1', args.port)
        assert client2 is client
        return
    if args.fake_sine and not args.port:
        client_end = await start_fake_sine()
        client_transport, client = await loop.create_connection(lambda: client, sock=client_end)
    elif args.port:
        client_transport, client2 = await loop.create_connection(lambda: client, '127.0.0.1', args.port)
        assert client2 is client
    elif args.fake_sine:
        await start_fake_sine(args.port)


args = None
serial_process = [None]


async def cleanup(client):
    for task in asyncio.Task.all_tasks():
        logger.warn('canceling task {}'.format(task))
        task.cancel()
    if not hasattr(client, 'transport'):
        return
    client.transport.close()
    logger.warn('cancelling futures of client')
    # client.cancel_all_futures()
    if not args.no_cleanup:
        logger.debug("sending sampler stop")
        await client.send_sampler_stop()
    if serial_process[0] is not None:
        serial_process[0].terminate() # note: under windows kill & terminate are one and the same
    client.exit_gracefully()


async def amain():
    global args
    global serial_process
    parser = argparse.ArgumentParser(
        description='Emolog protocol capture tool. Implements emolog client side, captures a given set of variables to a csv file')
    parser.add_argument('--fake-sine', default=False, action='store_true',
                        help='debug only - use a fake sine producing client')
    parser.add_argument('--serial', default='auto', help='serial port to use')
    parser.add_argument('--elf', default=None, required=True, help='elf executable running on embedded side')
    parser.add_argument('--var', default=[], action='append',
                        help='add a single var, example "foo,float,1,0" = "varname,vartype,ticks,tickphase"')
    parser.add_argument('--varfile', help='file containing variable definitions, identical to multiple --var calls')
    parser.add_argument('--csv-filename', default=None, help='name of csv output file')
    parser.add_argument('--verbose', default=True, action='store_false', dest='silent', help='turn on verbose logging; affects performance under windows')
    parser.add_argument('--log', default='out.log', help='log messages and other debug/info logs here')
    parser.add_argument('--runtime', type=float, help='quit after given seconds')
    parser.add_argument('--baud', default=1000000, help='baudrate, using RS422 up to 12000000 theoretically', type=int)
    parser.add_argument('--no-cleanup', default=False, action='store_true', help='do not stop sampler on exit')
    parser.add_argument('--dump')
    parser.add_argument('--direct', default=False, action='store_true', help='DEBUG access serial port directly without subprocess')
    parser.add_argument('--port', type=int, default=38080, help='connect to local TCP port instead of serial port, will be default')
    args = parser.parse_args()

    setup_logging(args.log, args.silent)

    if args.varfile is not None:
        with open(args.varfile) as fd:
            args.var = args.var + fd.readlines()
    split_vars = [[x.strip() for x in v.split(',')] for v in args.var]
    for v, orig in zip(split_vars, args.var):
        if len(v) != 3 or not an_int(v[1]) or not an_int(v[2]):
            logger.error("problem with '--var' argument {!r}".format(orig))
            logger.error("--var parameter must be a 4 element comma separated list of: <name>,<period:int>,<phase:int>")
            raise SystemExit
    names = [name for name, ticks, phase in split_vars]
    name_to_ticks_and_phase = {name: (int(ticks), int(phase)) for name, ticks, phase in split_vars}
    dwarf_variables = dwarf_get_variables_by_name(args.elf, list(name_to_ticks_and_phase.keys()), verbose=not args.silent)
    if len(dwarf_variables) == 0:
        logger.error("no variables set for sampling")
        raise SystemExit
    variables = []
    for name in names:
        v = dwarf_variables[name]
        period_ticks, phase_ticks = name_to_ticks_and_phase[name]
        variables.append(dict(phase_ticks=phase_ticks, period_ticks=period_ticks,
                              address=v.address, size=v.size,
                              _type=str_size_to_decoder(v.get_type_str(), v.size)))

    csv_filename = (next_available('emo', numbered=True) if not args.csv_filename else
                    next_available(args.csv_filename, numbered=False))
    print("================")
    print("Emotool starting")
    print("================")
    print("")
    print("creating output {}".format(csv_filename))
    csv_fd = open(csv_filename, 'w+')
    csv_obj = csv.writer(csv_fd, lineterminator='\n')
    loop = asyncio.get_event_loop()

    async def quit_after_runtime():
        start = clock()
        dt = 0.1 if args.runtime is not None else 1.0
        if try_getch_message:
            print(try_getch_message)
        while True:
            if try_getch():
                break
            await asyncio.sleep(0.1)
            if args.runtime is not None and clock() - start > args.runtime:
                break
        await cleanup(client)

    quit_task = quit_after_runtime()
    min_ticks = min(var['period_ticks'] for var in variables) # this is wrong, use gcd
    client = EmoToolClient(csv=csv_obj, fd=csv_fd, verbose=not args.silent, names=names, dump=args.dump,
                           min_ticks = min_ticks)
    await start_transport(args=args, client=client, serial_process=serial_process)
    # TODO - if one of these is never acked we get a hung process, and ctrl-c will complain
    # that the above task quit_after_runtime was never awaited
    print("about to send version")
    await client.send_version()
    print("about to send sampler stop")
    await client.send_sampler_stop()
    print("about to send sampler set variables")
    await client.send_set_variables(variables)
    print("about to send sampler start")
    await client.send_sampler_start()
    print("client initiated, starting to log data at rate TBD")
    sys.stdout.flush()
    return client, quit_task


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


async def amain_with_loop():
    client, quit_task = await amain()
    await quit_task


def main():
    #if sys.platform == 'win32':
    #    asyncio.set_event_loop(asyncio.ProactorEventLoop())

    loop = asyncio.get_event_loop()
    loop.run_until_complete(amain_with_loop())
    try:
        loop.run_until_complete(amain_with_loop())
    except KeyboardInterrupt:
        print("exiting on user ctrl-c")
    except Exception as e:
        print("got exception {!r}".format(e))
    loop.run_until_complete(cleanup(getattr(EmoToolClient, 'client', None)))


if __name__ == '__main__':
    main()
