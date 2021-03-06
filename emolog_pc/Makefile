all: tests/example.out tests/example.g++.out

.PHONY: help
help:
	echo "TODO: help"

tests/example.out: tests/example.c
	arm-none-eabi-gcc -ggdb -static tests/example.c -o tests/example.out

tests/example.g++.out: tests/example.c
	arm-none-eabi-g++ -ggdb -static tests/example.c -o tests/example.g++.out

