from unittest import TestCase

from dwarf import FileParser


class TestDwarf(TestCase):

    def test_sanity(self):
        parser = FileParser("sanity.out")
        data = sorted([(ivar.get_type_str(), ivar) for ivar in parser.interesting_vars])
        for (ivar_type, ivar), (expected_type, expected_name, expected_size) in zip(data, [
                                        ('Foo', 'foo', 16),
                                        ('MyEnum', 'enum_instance', 1),
                                        ('volatile int', 'global_var', 4)
                                  ]):
            self.assertEqual(ivar_type, expected_type)
            self.assertEqual(ivar.name, expected_name)
            self.assertEqual(ivar.size, expected_size)

    def test_class(self):
        parser = FileParser("sanity.out")
        foo = [v for v in parser.interesting_vars if v.name == 'foo'][0]
        self.assertEqual(foo.get_type_str(), 'Foo')
        # look for children
        self.assertEqual(len(foo.children), 3)
        sorted_children = list(sorted(foo.children, key=lambda c: c.name))
        self.assertEqual([c.name for c in sorted_children], ['foo1', 'foo2', 'p'])
        for v, offset in zip(sorted_children, [0, 4, 8]):
            self.assertEqual(v.address - foo.address, offset)
        p = [c for c in sorted_children if c.name == 'p'][0]
        sorted_p_children = list(sorted(p.children, key=lambda c: c.name))
        for v, offset in zip(sorted_p_children, [0, 4]):
            self.assertEqual(v.address - p.address, offset)