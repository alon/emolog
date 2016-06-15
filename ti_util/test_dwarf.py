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