import os
import sys
from time import sleep
sys.path.append(os.path.join(os.path.dirname(sys.modules[__name__].__file__), '..'))


from emolog.cython_util import coalesce_meth
from emolog.util import resolve


def test_coalesce():
    class T:
        g = []
        @coalesce_meth(100)
        def f(self, args):
            self.g.extend(args)
    # TODO - make test fake time
    t = T()
    t.f([1])
    assert t.g == [1]
    t.f([2])
    assert t.g == [1]
    sleep(0.02)
    assert t.g == [1]
    t.f([3])
    assert t.g == [1, 2, 3]


def test_resolve():
    plat = resolve('sys.platform')
    assert plat is sys.platform
    bla = resolve('nothing.here')
    assert bla is None


if __name__ == '__main__':
    test_coalesce()
