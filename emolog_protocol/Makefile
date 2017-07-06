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

all: $(LIBRARY) example_user$(EXESUFFIX)

$(LIBRARY): source/emolog_protocol.h source/emolog_protocol.c
	$(CC) $(CFLAGS) -shared -fPIC -o $(LIBRARY) source/emolog_protocol.c

example_user$(EXESUFFIX): source/example_user.c $(LIBRARY)
	$(CC) $(CFLAGS) -o example_user -L. -lemolog_protocol source/example_user.c

.PHONY: clean run

clean:
	rm -f $(LIBRARY) example_user$(EXESUFFIX)

run: example_user$(EXESUFFIX)
	LD_LIBRARY_PATH=. ./example_user

debug: example_user$(EXESUFFIX)
	LD_LIBRARY_PATH=. cgdb ./example_user
