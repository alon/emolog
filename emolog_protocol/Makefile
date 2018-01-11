# -DHOST_DEBUG
CFLAGS=-I. -ggdb -Wall -m64 -DEMOLOG_HOST

ifeq ($(OS),Windows_NT)
LIBPREFIX=
LIBSUFFIX=.dll
EXESUFFIX=.exe
else
LIBPREFIX=lib
LIBSUFFIX=.so
EXESUFFIX=
endif

LIBRARY=$(LIBPREFIX)emolog_protocol$(LIBSUFFIX)

all: $(LIBRARY)

$(LIBRARY): emolog_protocol.h emolog_protocol.cpp
	$(CC) $(CFLAGS) -shared -fPIC -o $(LIBRARY) emolog_protocol.cpp

.PHONY: clean run

clean:
	rm -f $(LIBRARY)
