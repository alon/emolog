/*
 * emolog_tx_circular_buffer.c
 *
 *  Created on: 18 ���� 2016
 *      Author: Guy Ovadia
 */

#include "emolog_tx_circular_buffer.h"

#include <stdint.h>
#include <stdbool.h>

#include "emolog_comm.h"


unsigned char tx_buf[TX_BUF_SIZE];

volatile int32_t tx_buf_read_pos = 0;	// points at the first (the oldest) byte in the buffer
volatile int32_t tx_buf_write_pos = 0;	// points where a new byte should go
static bool is_empty = true;


bool tx_buf_put(unsigned char byte)
{
	if (tx_buf_is_full()) return false;

	tx_buf[tx_buf_write_pos] = byte;
	tx_buf_write_pos = (tx_buf_write_pos + 1) % TX_BUF_SIZE;

	is_empty = false;
	return true;
}


int tx_buf_get(void)
{
	unsigned char res;

	if (tx_buf_is_empty()) return -1;

	res = tx_buf[tx_buf_read_pos];
	tx_buf_read_pos = (tx_buf_read_pos + 1) % TX_BUF_SIZE;

	if (tx_buf_read_pos == tx_buf_write_pos) is_empty = true;

	return res;
}


int tx_buf_bytes_free(void)
{
	if (is_empty) return (TX_BUF_SIZE);

	return ( (TX_BUF_SIZE - (tx_buf_write_pos - tx_buf_read_pos)) % TX_BUF_SIZE);
}


bool tx_buf_is_empty(void)
{
	return is_empty;
}


bool tx_buf_is_full(void)
{
	return ( (tx_buf_read_pos == tx_buf_write_pos) && (is_empty == false));
}

