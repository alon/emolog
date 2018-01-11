/*
 * emolog_comm.h
 *
 *  Created on: 22 במאי 2016
 *      Author: Guy Ovadia
 */

#ifndef EMOLOG_COMM_H_
#define EMOLOG_COMM_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdint.h>

#include "emolog_protocol.h"


void comm_setup(void);

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


#ifdef __cplusplus
}
#endif

#endif /* EMOLOG_COMM_H_ */
