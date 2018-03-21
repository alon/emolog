from io import StringIO

from emolog.varsfile import (
    read_vars_from_fd, VarsFileError, PROBLEM_NOT_ENOUGH,
    PROBLEM_NOT_A_DIGIT_FMT)


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

