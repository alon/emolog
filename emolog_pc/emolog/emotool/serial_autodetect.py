"""
COM port auto-detection for emolog.

When --serial is 'auto', resolve to a concrete device name (e.g. 'COM4') by
enumerating USB-serial adapters and matching against a serial_autodetect.ini
file.

INI lookup order:
  1. Path passed explicitly via --serial-autodetect.
  2. ./serial_autodetect.ini in the current working directory.
  3. Built-in default shipped with emolog.

Each [section] describes one acceptable adapter. Sections are priority-ordered:
if matches come from different sections, the first section's match wins.
Multiple matches within a single section is an error.

Match keys (all optional; blank means "any"):
    vid             hex (0x0403) or decimal
    pid             hex (0x6014) or decimal
    description     regex applied to ListPortInfo.description
    serial_number   regex applied to ListPortInfo.serial_number
"""

import os
import re
import sys
from configparser import ConfigParser

from serial.tools import list_ports


DEFAULT_INI_NAME = 'serial_autodetect.ini'

_KNOWN_KEYS = {'vid', 'pid', 'description', 'serial_number'}


class AutodetectError(Exception):
    pass


class Candidate:
    def __init__(self, name):
        self.name = name
        self.vid = None
        self.pid = None
        self.description = None     # compiled regex or None
        self.serial_number = None   # compiled regex or None

    def matches(self, port):
        if self.vid is not None and port.vid != self.vid:
            return False
        if self.pid is not None and port.pid != self.pid:
            return False
        if self.description is not None:
            if port.description is None or not self.description.search(port.description):
                return False
        if self.serial_number is not None:
            if port.serial_number is None or not self.serial_number.search(port.serial_number):
                return False
        # An entry with no fields set would match every port - reject it as a
        # config error rather than silently grabbing arbitrary hardware.
        if (self.vid is None and self.pid is None
                and self.description is None and self.serial_number is None):
            return False
        return True


def _parse_int(value):
    value = value.strip()
    if value.lower().startswith('0x'):
        return int(value, 16)
    return int(value, 0)


def _default_ini_path():
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        return os.path.join(base, 'emolog', 'emotool', DEFAULT_INI_NAME)
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), DEFAULT_INI_NAME)


def _resolve_ini_path(explicit):
    """Returns (path, source_label). Raises AutodetectError if not found."""
    if explicit:
        if not os.path.isfile(explicit):
            raise AutodetectError(
                "--serial-autodetect file not found: {p}".format(p=explicit))
        return explicit, 'specified via --serial-autodetect'
    cwd_path = os.path.join(os.getcwd(), DEFAULT_INI_NAME)
    if os.path.isfile(cwd_path):
        return cwd_path, 'CWD'
    default = _default_ini_path()
    if not os.path.isfile(default):
        raise AutodetectError(
            "built-in default {n} not found at {p}".format(n=DEFAULT_INI_NAME, p=default))
    return default, 'built-in default'


def load_candidates(path):
    cp = ConfigParser()
    with open(path, 'r', encoding='utf-8') as f:
        cp.read_file(f)
    out = []
    for section in cp.sections():
        c = Candidate(name=section)
        for key, val in cp.items(section):
            val = val.strip()
            if val == '':
                continue
            if key == 'vid':
                c.vid = _parse_int(val)
            elif key == 'pid':
                c.pid = _parse_int(val)
            elif key == 'description':
                c.description = re.compile(val)
            elif key == 'serial_number':
                c.serial_number = re.compile(val)
            elif key not in _KNOWN_KEYS:
                print("warning: unknown key '{k}' in section [{s}] of {p}; ignoring".format(
                    k=key, s=section, p=path))
        out.append(c)
    return out


def _format_port(p):
    vid = '{:04X}'.format(p.vid) if p.vid is not None else '----'
    pid = '{:04X}'.format(p.pid) if p.pid is not None else '----'
    sn = p.serial_number if p.serial_number else '-'
    desc = p.description if p.description else '-'
    return '{dev}  VID={vid} PID={pid}  SN={sn}  "{desc}"'.format(
        dev=p.device, vid=vid, pid=pid, sn=sn, desc=desc)


def resolve_serial(args_serial, autodetect_path=None):
    """
    If args_serial is 'auto', enumerate available ports and match against the
    auto-detect INI. Returns the resolved device name (e.g. 'COM4'). Otherwise
    returns args_serial unchanged.

    Raises AutodetectError on zero matches or ambiguous matches within a single
    section.
    """
    if args_serial != 'auto':
        return args_serial

    ini_path, ini_source = _resolve_ini_path(autodetect_path)
    candidates = load_candidates(ini_path)
    all_ports = list(list_ports.comports())

    # Priority-by-section: walk sections in order. First section with any
    # match wins. Within that section, more than one match is an error.
    for cand in candidates:
        matches = [p for p in all_ports if cand.matches(p)]
        if not matches:
            continue
        if len(matches) > 1:
            lines = [
                "--serial auto matched multiple ports for section [{n}]:".format(n=cand.name),
            ]
            lines += ['  ' + _format_port(p) for p in matches]
            lines.append(
                "Specify --serial COMx, or add a serial_number filter to [{n}] in {p}".format(
                    n=cand.name, p=ini_path))
            raise AutodetectError('\n'.join(lines))
        port = matches[0]
        vid = port.vid if port.vid is not None else 0
        pid = port.pid if port.pid is not None else 0
        print(
            "auto-detected {dev} (section [{name}], VID={vid:04X} PID={pid:04X}, SN={sn}) "
            "[from {src}: {path}]".format(
                dev=port.device, name=cand.name, vid=vid, pid=pid,
                sn=port.serial_number or '-', src=ini_source, path=ini_path))
        return port.device

    lines = [
        "--serial auto found no matching ports (using {src}: {path})".format(
            src=ini_source, path=ini_path),
    ]
    if all_ports:
        lines.append("Detected ports:")
        lines += ['  ' + _format_port(p) for p in all_ports]
    else:
        lines.append("No serial ports detected.")
    lines.append("Specify --serial COMx, or add a section to {p}".format(p=ini_path))
    raise AutodetectError('\n'.join(lines))
