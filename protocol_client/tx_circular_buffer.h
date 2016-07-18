/*
 * tx_circular_buffer.h
 *
 *  Created on: 18 αιεμ 2016
 *      Author: Guy Ovadia
 */

#ifndef TX_CIRCULAR_BUFFER_H_
#define TX_CIRCULAR_BUFFER_H_

#include <stdint.h>
#include <stdbool.h>

bool tx_buf_put(unsigned char byte);

// returns -1 is buffer is empty, or one byte if not
int tx_buf_get(void);

// returns space available in buffer, in bytes
int tx_buf_bytes_free(void);

bool tx_buf_is_empty(void);
bool tx_buf_is_full(void);

#endif /* TX_CIRCULAR_BUFFER_H_ */
