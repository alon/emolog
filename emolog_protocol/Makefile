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

$(LIBRARY): emolog_protocol.h emolog_protocol.c
	$(CC) $(CFLAGS) -shared -fPIC -o $(LIBRARY) emolog_protocol.c

example_user$(EXESUFFIX): example_user.c $(LIBRARY)
	$(CC) $(CFLAGS) -o example_user -L. -lemolog_protocol example_user.c

.PHONY: clean run

clean:
	rm -f $(LIBRARY) example_user$(EXESUFFIX)

run: example_user$(EXESUFFIX)
	LD_LIBRARY_PATH=. ./example_user

debug: example_user$(EXESUFFIX)
	LD_LIBRARY_PATH=. cgdb ./example_user
