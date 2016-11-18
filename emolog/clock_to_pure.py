import struct
import sys

infile = sys.argv[-2]
outfile = sys.argv[-1]

with open(infile, 'rb') as inf:
  with open(outfile, 'wb') as outf:
    while True:
      try:
        _, len = struct.unpack('<fI', inf.read(8))
      except:
        break
      outf.write(inf.read(len))
