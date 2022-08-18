from struct import unpack



class NamedDecoderException(Exception):
    pass


cdef class Decoder:
    cdef public bytes unpack_str
    cdef public bytes name
    def __init__(self, name, unpack_str):
        self.unpack_str = unpack_str
        self.name = name

    def to_csv_val(self, v):
        return v

cdef class ArrayDecoder(Decoder):
    cdef unsigned length

    def __init__(self, name, elem_unpack_str, length):
        super().__init__(name=name, unpack_str=(b'%d%b' % (length, elem_unpack_str)))
        self.length = length

    def decode(self, array):
        data = unpack(b'<' + self.unpack_str, array)
        if isinstance(data[0], bytes):  # a C char string
            return (b''.join(data)).decode()
        res = ['{ ']
        for i, elem in enumerate(data):
            if isinstance(elem, float):
                elem_str = "{:.3f}".format(elem)
            else:
                elem_str = "{}".format(elem)
            res.append(elem_str)
            res.append(', ')
        res = res[:-1]  # throw away last comma
        res.append(' }')
        return ''.join(res)


cdef class NamedDecoder(Decoder):

    cdef public dict val_to_name
    cdef public long long max_unsigned_val

    def __init__(self, name, max_unsigned_val, unpack_str, val_to_name):
        super().__init__(unpack_str=unpack_str, name=name)
        self.val_to_name = {(v % max_unsigned_val): k for v, k in val_to_name.items()}
        self.max_unsigned_val = max_unsigned_val

    def to_csv_val(self, v):
        v_mod = v % self.max_unsigned_val
        try:
            return self.val_to_name[v_mod]
        except:
            raise NamedDecoderException('{name} missing value {v} ({v_mod})'.format(name=self.name, v=v, v_mod=v_mod))


def unpack_str_from_size(size):
    if size == 8:
        s = b'q'
    elif size == 4:
        s = b'l'
    elif size == 2:
        s = b'h'
    elif size == 1:
        s = b'b'
    else:
        raise Exception("unhandled size in unpack_str_from_size: {size}".format(size=size))
    return s
