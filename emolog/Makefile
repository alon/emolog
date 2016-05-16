CFLAGS=-I. -DDEBUG -ggdb -Wall

all: libemolog.so example_user

libemolog.so: emolog.h emolog.c
	gcc $(CFLAGS) -shared -fPIC -o libemolog.so emolog.c

example_user: example_user.c libemolog.so
	gcc $(CFLAGS) -o example_user -L. -lemolog example_user.c

.PHONY: clean run

clean:
	rm libemolog.so example_user

run: example_user
	LD_LIBRARY_PATH=. ./example_user

debug: example_user
	LD_LIBRARY_PATH=. cgdb ./example_user
