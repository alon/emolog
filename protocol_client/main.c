#include <stdio.h>

#include <cmwpp.h>


uint16_t g_foo;

int g_buz(void) {
	return g_foo + 10 * g_foo;
}


int main(void)
{
	unsigned char buf[1024];
	unsigned int encoded_len;
	int16_t needed;

	g_foo = 10;
    encoded_len = wpp_encode_version(buf);
    needed = wpp_decode(buf, encoded_len);
    return needed;
}
