# On 64 bit x86_64 this is required
ifeq ($(shell uname -m),armv7l)
	FORCE_32_BIT=
else
	FORCE_32_BIT=-m32
endif
CFLAGS=$(FORCE_32_BIT) -g -fPIC -I ../../emolog_protocol/source/ -I ../../emolog_embedded/source/ -I ../examples_common -DTICK_PERIOD_MS=0
CXXFLAGS=$(CFLAGS)
LDFLAGS=-lm

all: pc

OBJS=emolog_protocol.o emolog_comm_linux.o emolog_embedded.o emolog_sampler.o emolog_example_client.o emolog_example_hw_pc.o 

pc: $(OBJS)
	gcc $(CFLAGS) $(LDFLAGS) -o pc $(OBJS)

.PHONY: clean bla

clean:
	rm -f pc $(OBJS)
