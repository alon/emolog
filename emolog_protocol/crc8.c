/*
 * crc8.c
 *
 *  Created on: 18 бреб„ 2016
 *      Author: Guy Ovadia
 */

#include <stdint.h>
#include <stdio.h>
#include <fcntl.h>

extern void
crc_init(void);

extern uint8_t
crc8(uint8_t const message[], int nBytes);

int main(int argc, char **argv)
{
    char buf[1024];
    int fd = open(argv[1], O_RDONLY);
    int n = read(fd, buf, 1024);
    crc_init();
    printf("%d", crc8(buf, n));
    return 0;
}
