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

#define RX_BUF_SIZE			1024
#define TX_BUF_SIZE			1024


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
bool comm_queue_message(uint8_t *src, size_t len);

// called from the UART interrupt handler when there are incoming bytes in the RX FIFO
void handle_uart_rx(void);

// called from the UART interrupt handler when all the bytes in the tx FIFO have been transmitted
void handle_uart_tx(void);

#endif /* COMM_H_ */
