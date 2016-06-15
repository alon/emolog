from unittest import TestCase

from dwarf import FileParser


class TestDwarf(TestCase):

    def test_sanity(self):
        parser = FileParser("sanity.out")
        data = sorted([(ivar.get_type_str(), ivar) for ivar in parser.interesting_vars])
        for (ivar_str, ivar), (expected_type, expected_name) in zip(data, [
                                        ('Foo', 'foo'),
                                        ('MyEnum', 'enum_instance'),
                                        ('volatile int', 'global_var')
                                  ]):
            self.assertEqual(ivar_str, expected_type)
            self.assertEqual(ivar.name, expected_name)