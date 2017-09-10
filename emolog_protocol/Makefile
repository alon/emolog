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

$(LIBRARY): source/emolog_protocol.h source/emolog_protocol.c
	$(CC) $(CFLAGS) -shared -fPIC -o $(LIBRARY) source/emolog_protocol.c

.PHONY: clean run

clean:
	rm -f $(LIBRARY)
