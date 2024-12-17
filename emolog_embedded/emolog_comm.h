/*
 * emolog_comm.h
 *
 *  Created on: 22 ���� 2016
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_COMM_H_
#define EMOLOG_COMM_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include "emolog_protocol.h"


void comm_init(void);

/**
 * @return:
 *  not NULL - message available
 *  NULL - no message available
 */
emo_header *comm_peek_message(void);


void comm_consume_message(void);


/**
 * queue message for sending.
 *
 *  @return:
 *   true - message queued
 *   false - message not queued, tx buffer full
 */
bool comm_queue_message(const uint8_t *src, size_t len);


/**
 * for communications protocols that are implemented with polling,
 * this is called once per tick from emolog_run_step()
 *
 * protocols that are purely interrupt-based and don't need anything done per-tick,
 * can leave this function empty.
 *
 */
void comm_run_step();


// check if there are new bytes in the DMA circular RX buffer
bool is_rx_buf_empty();

// pop a byte from the DMA circular RX buffer.
// It is the caller's responsibility to check if the buffer is empty before calling this function.
uint8_t pop_rx_buf();


#ifdef __cplusplus
}
#endif

#endif /* EMOLOG_COMM_H_ */
