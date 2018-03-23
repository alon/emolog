import logging

logger = logging.getLogger('varsfile')

class VarsFileError(Exception):
    def __init__(self, linenumber, linecontents, problem):
        self.linenumber = linenumber
        self.linecontents = linecontents
        self.problem = problem

    def __str__(self):
        return f'{self.linenumber}: {self.problem}\n==> {self.linecontents}'

    def __repr__(self):
        return f'VarsFileError({self.linenumber}, "{self.linecontents}", "{self.problem}")'


def read_vars_file(filename, check_errors):
    with open(filename) as fd:
        return read_vars_from_fd(fd, check_errors)


def read_vars_from_fd(fd, check_errors):
    ret = [l for l in fd.readlines() if l.strip()[:1] != '#' and len(l.strip()) > 0]
    if check_errors:
        for i, line in enumerate(ret):
            parse_vars_definition(line=line, linenumber=i)
    return ret


PROBLEM_NOT_ENOUGH = 'Variable must contain 3 elements separated by commas'
PROBLEM_NOT_A_DIGIT_FMT = 'Element {!r} is not a number'


def parse_vars_definition(line, linenumber):
    v_str = [x.strip() for x in line.split(',')]
    if len(v_str) != 3:
        raise VarsFileError(linenumber=linenumber, linecontents=line,
            problem=PROBLEM_NOT_ENOUGH)
    for elem in [1, 2]:
        if not v_str[elem].isdigit():
            raise VarsFileError(linenumber=linenumber, linecontents=line,
                problem=PROBLEM_NOT_A_DIGIT_FMT.format(v_str[elem]))
    return (v_str[0], int(v_str[1]), int(v_str[2]))


def merge_vars_from_file_and_list(filename=None, def_lines=None, check_errors=False):
    if def_lines is None:
        def_lines = []
    num_not_from_file = len(def_lines)
    if filename is not None:
        def_lines.extend(read_vars_file(filename, check_errors=check_errors))
    # TODO - move this check to command line parsing, too low level here
    if len(def_lines) == 0:
        logger.error('no variable definitions supplied. use --var or --varsfile')
        raise SystemExit
    try:
        # Note hack: using negative numbers for command line arguments.
        # rust: would have used an enum :)
        defs = [parse_vars_definition(line=v, linenumber=i - num_not_from_file)
                    for i, v in enumerate(def_lines)]
    except VarsFileError as e:
        logger.error(str(e))
        raise SystemExit
    return defs


def main():
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', type=argparse.FileType('r'), help='file to check', required=True)
    args = parser.parse_args()
    try:
        res = read_vars_from_fd(args.file, check_errors=True)
    except VarsFileError as e:
        print(str(e))
        sys.exit(-1)
    else:
        print("ok")
