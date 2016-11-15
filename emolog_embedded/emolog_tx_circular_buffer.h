/*
 * emolog_tx_circular_buffer.h
 *
 *  Created on: 18 αιεμ 2016
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_TX_CIRCULAR_BUFFER_H_
#define EMOLOG_TX_CIRCULAR_BUFFER_H_

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#include "emolog_comm.h"

bool tx_buf_put_byte(unsigned char byte);
bool tx_buf_put_bytes(const uint8_t *src, size_t len);

// returns -1 is buffer is empty, or one byte if not
char tx_buf_get(void);
char tx_buf_get_unsafe(void);

// returns space available in buffer, in bytes
int tx_buf_bytes_free(void);

// returns size of data in buffer
int tx_buf_len(void);

bool tx_buf_is_empty(void);
bool tx_buf_is_full(void);

extern bool is_empty;
extern volatile int32_t tx_buf_read_pos;
extern volatile int32_t tx_buf_write_pos;
extern unsigned char tx_buf[TX_BUF_SIZE];

#endif /* EMOLOG_TX_CIRCULAR_BUFFER_H_ */
