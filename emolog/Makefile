CFLAGS=-I. -DDEBUG -ggdb -Wall -m64

all: libemolog.so example_user

SYSTEM=$(shell uname -s)

ifeq ($(SYSTEM), MINGW32_NT-6.1)
LIBPREFIX=
LIBSUFFIX=.dll
EXESUFFIX=.exe
else
LIBPREFIX=lib
LIBSUFFIX=.so
EXESUFFIX=
endif

LIBRARY=$(LIBPREFIX)emolog$(LIBSUFFIX)

libemolog.so: emolog.h emolog.c
	gcc $(CFLAGS) -shared -fPIC -o $(LIBRARY) emolog.c

example_user: example_user.c libemolog.so
	gcc $(CFLAGS) -o example_user -L. -lemolog example_user.c

.PHONY: clean run

clean:
	rm $(LIBRARY) example_user$(EXESUFFIX)

run: example_user
	LD_LIBRARY_PATH=. ./example_user

debug: example_user
	LD_LIBRARY_PATH=. cgdb ./example_user
