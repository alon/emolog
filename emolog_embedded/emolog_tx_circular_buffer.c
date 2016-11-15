/*
 * emolog_tx_circular_buffer.c
 *
 *  Created on: 18 αιεμ 2016
 *      Author: Guy Ovadia
 */

#include "emolog_tx_circular_buffer.h"

#include <stdint.h>
#include <stdbool.h>

#include "emolog_comm.h"


// This is no longer an encapsulated circular buffer, it is used by emolog_comm as well. Should
// be moved there and re-static-ed later.
unsigned char tx_buf[TX_BUF_SIZE];

volatile int32_t tx_buf_read_pos = 0;	// points at the first (the oldest) byte in the buffer
volatile int32_t tx_buf_write_pos = 0;	// points where a new byte should go
bool is_empty = true;


bool tx_buf_put_bytes(const uint8_t *src, size_t len)
{
	if (tx_buf_bytes_free() < len) return false;

	int32_t space_until_wrap_around = TX_BUF_SIZE - tx_buf_write_pos;
	if (space_until_wrap_around >= len) // can put everything without wrap-around
	{
		memcpy(tx_buf + tx_buf_write_pos, src, len);
	}
	else
	{
		memcpy(tx_buf + tx_buf_write_pos, src, space_until_wrap_around);
		memcpy(tx_buf, src + space_until_wrap_around, len - space_until_wrap_around);
	}
	tx_buf_write_pos = (tx_buf_write_pos + len) % TX_BUF_SIZE;
	is_empty = false;
	return true;
}


bool tx_buf_put_byte(unsigned char byte)
{
	if (tx_buf_is_full()) return false;

	tx_buf[tx_buf_write_pos] = byte;
	tx_buf_write_pos = (tx_buf_write_pos + 1) % TX_BUF_SIZE;

	is_empty = false;
	return true;
}


char tx_buf_get(void)
{
	if (tx_buf_is_empty()) return (char)-1;

	return tx_buf_get_unsafe();
}


char tx_buf_get_unsafe(void)
{
	unsigned char res;

	res = tx_buf[tx_buf_read_pos];
	tx_buf_read_pos = (tx_buf_read_pos + 1) % TX_BUF_SIZE;

	if (tx_buf_read_pos == tx_buf_write_pos) is_empty = true;

	return res;
}


int tx_buf_bytes_free(void)
{
	if (is_empty) return (TX_BUF_SIZE);

	return (TX_BUF_SIZE - (tx_buf_write_pos - tx_buf_read_pos)) % TX_BUF_SIZE;
}


int tx_buf_len(void)
{
	if (is_empty) return 0;
	return (tx_buf_write_pos - tx_buf_read_pos) % TX_BUF_SIZE;
}


bool tx_buf_is_empty(void)
{
	return is_empty;
}


bool tx_buf_is_full(void)
{
	return (tx_buf_read_pos == tx_buf_write_pos) && (is_empty == false);
}
