/*
 * comm.h
 *
 *  Created on: 22 במאי 2016
 *      Author: Guy Ovadia
 */

#ifndef COMM_H_
#define COMM_H_

#include <stdio.h>
#include <stdint.h>

#include "emolog.h"


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
 * TODO: Can fail. What should the behavior be?
 */
void comm_queue_message(uint8_t *src, size_t len);


#endif /* COMM_H_ */
