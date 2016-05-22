def read_map_file(file_name):
    """

    """
    map_file = open(file_name).readlines()
    [i] = [i for i, x in enumerate(map_file) if "GLOBAL SYMBOLS: SORTED BY Symbol Address" in x]
    i += 4
    map_dict = {}
    for line in map_file[i:-3]:
        addr, symbol = line.split()
        map_dict[int(addr, 16)] = symbol
    return map_dict


if __name__ == '__main__':
    var_map = read_map_file("D:\\Projects\\Comet ME Pump Drive\\firmware\\pump_drive_tiva\\Debug\\pump_drive_tiva.map")
    ram_only = {addr: symbol for addr, symbol in var_map.items() if addr >= 0x20000000 and addr < 0xffffffff and symbol[0] != '_'}
