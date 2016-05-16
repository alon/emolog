/* vim: set tabstop=4 softtabstop=4 shiftwidth=4 expandtab : */

#include <stdio.h>

#include "emolog.h"

int serialize_version_test(void)
{
  unsigned char buf[1024];
  unsigned int encoded_len;
  int16_t needed;
  int i;

  wpp_version *version = (wpp_version *)buf;
  wpp_header *decoded = NULL;

  for (i = 0 ; i < 2 ; ++i) {
    encoded_len = wpp_encode_version(buf, -1);
    needed = wpp_decode(buf, encoded_len);
    if (needed != 0) {
        printf("return from wpp_decode is not 0: %d\n", needed);
        return 1;
    }
    decoded = (wpp_header *)buf;
    printf("start:   %c%c%c\n", decoded->start[0], decoded->start[1], decoded->start[2]);
    printf("type:    %d\n", decoded->type);
    printf("length:  %d\n", decoded->length);
    printf("seq:     %d\n", decoded->seq);
    printf("version: %d\n", version->p.protocol_version);
  }
  return 0;
}

int serialize_and_send_version_test(void)
{
    // TODO
    return 0;
}

int main(void)
{
    int err;

    if ((err = serialize_version_test()) != 0) {
        printf("failed serialize_version_test: %d\n", err);
        return err;
    }
    return serialize_and_send_version_test();
}
