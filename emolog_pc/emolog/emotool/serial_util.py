from serial.tools.list_ports import comports

SERIAL_AUTO_VENDOR_ID = 0x0403
SERIAL_AUTO_PRODUCT_ID = 0x6010

def find_serial():
    available = comports()
    if len(available) == 0:
        print("no com ports available - is board powered and connected?")
        raise SystemExit
    available = [ser for ser in available if ser.vid == SERIAL_AUTO_VENDOR_ID and ser.pid == SERIAL_AUTO_PRODUCT_ID]
    if len(available) == 0:
        print("no com port matching vendor/product ids available - is board powered and connected?")
        raise SystemExit
    if len(available) > 1:
        # pick the lowest interface in multiple interface devices
        if hasattr(available[0], 'device_path'):
            device = min([(x.device_path.split('/')[:-1], x) for x in available])[1]
        else:
            device = min([(x.device, x) for x in available])[1]
    else:
        device = available[0]
    comport = device.device
    print("automatic comport selection: {}".format(comport))
    return comport
