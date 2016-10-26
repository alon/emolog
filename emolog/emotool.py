#!/bin/env python

import sys
import asyncio
import argparse

from dwarf import FileParser
import emolog

def getvars(filename, varparts):
    file_parser = FileParser(filename=filename)
    sampled_vars = [v for v in file_parser.visit_interesting_vars_tree_leafs() if v.name in varparts]
    print("Registering variables from {}".format(filename))
    for v in sampled_vars:
        print("   {}".format(v.get_full_name()))
    return sampled_vars


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default=None, help='serial port to use')
    parser.add_argument('--serial-hint', default='stellaris', help='usb description for serial port to filter on')
    parser.add_argument('--elf', default=None, required=True, help='elf executable running on embedded side')
    parser.add_argument('--var-parts', default='sawtooth,sine', help='all vars including one of the strings will be shown')
    parser.add_argument('--rate', type=int, default=1000, help='number of ticks to wait between samples')
    args = parser.parse_args()
    sampled_vars = getvars(args.elf, args.var_parts.split(','))
    var_dict = [dict(phase_ticks=0, period_ticks=args.rate, address=v.address, size=v.size) for v in sampled_vars]

    if sys.platform == 'win32':
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    async def emain():
        client = await emolog.get_serial_client(comport=args.serial, hint_description=args.serial_hint)
        client.send_version()
        client.send_sampler_stop()
        client.send_set_variables(var_dict)
        client.send_sampler_start()
        # TODO? ctrl-c
        while True:
            await asyncio.sleep(0.1)

    asyncio.get_event_loop().run_until_complete(emain())


if __name__ == '__main__':
    main()
