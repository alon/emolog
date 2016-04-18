CFLAGS=-I. -DDEBUG -ggdb -Wall

all: libcmwpp.so example_user

libcmwpp.so: cmwpp.h cmwpp.c
	gcc $(CFLAGS) -shared -fPIC -o libcmwpp.so cmwpp.c

example_user: example_user.c libcmwpp.so
	gcc $(CFLAGS) -o example_user -L. -lcmwpp example_user.c

.PHONY: clean run

clean:
	rm libcmwpp.so example_user

run: example_user
	LD_LIBRARY_PATH=. ./example_user

debug: example_user
	LD_LIBRARY_PATH=. cgdb ./example_user
