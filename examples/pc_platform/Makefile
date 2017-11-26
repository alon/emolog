CFLAGS=-g -m32 -fPIC -I ../../emolog_protocol/source/ -I ../../emolog_embedded/source/ -I ../examples_common
CXXFLAGS=$(CFLAGS)
LDFLAGS=-lm

all: pc

OBJS=emolog_protocol.o emolog_comm_linux.o emolog_embedded.o emolog_sampler.o emolog_example_client.o emolog_example_hw_pc.o 

pc: $(OBJS)
	gcc $(CFLAGS) $(LDFLAGS) -o pc $(OBJS)

.PHONY: clean

clean:
	rm -f pc $(OBJS)
