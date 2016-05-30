# -DHOST_DEBUG
CFLAGS=-I. -ggdb -Wall -m64

ifeq ($(OS),Windows_NT)
LIBPREFIX=
LIBSUFFIX=.dll
EXESUFFIX=.exe
else
LIBPREFIX=lib
LIBSUFFIX=.so
EXESUFFIX=
endif

LIBRARY=$(LIBPREFIX)emolog$(LIBSUFFIX)

all: $(LIBRARY) example_user$(EXESUFFIX)

$(LIBRARY): emolog.h emolog.c
	gcc $(CFLAGS) -shared -fPIC -o $(LIBRARY) emolog.c

example_user$(EXESUFFIX): example_user.c $(LIBRARY)
	gcc $(CFLAGS) -o example_user -L. -lemolog example_user.c

.PHONY: clean run

clean:
	rm -f $(LIBRARY) example_user$(EXESUFFIX)

run: example_user$(EXESUFFIX)
	LD_LIBRARY_PATH=. ./example_user

debug: example_user$(EXESUFFIX)
	LD_LIBRARY_PATH=. cgdb ./example_user
