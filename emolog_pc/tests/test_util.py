import os
import sys
from time import sleep
sys.path.append(os.path.join(os.path.dirname(sys.modules[__name__].__file__), '..'))


from emolog.cylib import coalesce_meth


def test_coalesce():
    class T:
        g = []
        @coalesce_meth(100)
        def f(self, args):
            self.g.extend(args)
    # TODO - make test fake time
    t = T()
    t.f(1)
    assert t.g == [1]
    t.f(2)
    assert t.g == [1]
    sleep(0.02)
    assert t.g == [1]
    t.f(3)
    assert t.g == [1, 2, 3]


if __name__ == '__main__':
    test_coalesce()
