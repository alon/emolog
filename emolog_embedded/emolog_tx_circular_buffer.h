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

bool tx_buf_put_byte(unsigned char byte);
bool tx_buf_put_bytes(const uint8_t *src, size_t len);

// returns -1 is buffer is empty, or one byte if not
int tx_buf_get(void);

// returns space available in buffer, in bytes
int tx_buf_bytes_free(void);

// returns size of data in buffer
int tx_buf_len(void);

bool tx_buf_is_empty(void);
bool tx_buf_is_full(void);

#endif /* EMOLOG_TX_CIRCULAR_BUFFER_H_ */
