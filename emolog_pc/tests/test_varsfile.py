from io import StringIO
from tempfile import TemporaryDirectory
from os import path

from emolog.varsfile import (
    read_vars_from_fd, VarsFileError, PROBLEM_NOT_ENOUGH,
    PROBLEM_NOT_A_DIGIT_FMT, merge_vars_from_file_and_list)


def test_read_vars_from_fd():
    for inp, error, expected_result in [
        ("""a,1,2
 """    ,
        False,
        ['a,1,2\n']
        ),
        ("""a,b
"""     ,
        True,
        VarsFileError(linenumber=0, linecontents='a,b\n', problem=PROBLEM_NOT_ENOUGH)
        ),
        ("""a,2,c
"""     ,
        True,
        VarsFileError(linenumber=0, linecontents='a,2,c\n', problem=PROBLEM_NOT_A_DIGIT_FMT.format('c'))
        ),
        ]:
        fd = StringIO(inp)
        if error:
            res = None
            try:
                read_vars_from_fd(fd, check_errors=True)
            except Exception as e:
                res = e
        else:
            res = read_vars_from_fd(fd, check_errors=True)
        assert(repr(res) == repr(expected_result))


def test_merge_vars_from_file_and_list():
    with TemporaryDirectory() as temp_dir:
        filename = path.join(temp_dir, 'vars.csv')
        with open(filename, 'w+') as fd:
            fd.write('\n'.join(['a,1,2', 'b,2,3']) + '\n')
        result = merge_vars_from_file_and_list(filename=filename, def_lines=[])
        assert(result == [('a', 1, 2), ('b', 2, 3)])
        result2 = merge_vars_from_file_and_list(filename=filename, def_lines=['c,4,5'])
        assert(result2 == [('c', 4, 5), ('a', 1, 2), ('b', 2, 3)])
        result3 = merge_vars_from_file_and_list(filename=None, def_lines=['c,4,5'])
        assert(result3 == [('c', 4, 5)])

