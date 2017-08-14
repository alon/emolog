/*
 * emolog_comm_stm32f3.c
 *
 *  Created on: 11 Aug 2017
 *      Author: Guy Ovadia
 */

#include "emolog_comm.h"


#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>

#include "emolog_debug.h"

#include "stm32f302x8.h"


#define RX_BUF_SIZE         1024

static volatile bool message_available = false;

static unsigned char rx_buf[RX_BUF_SIZE];
static volatile uint32_t rx_buf_pos = 0;


bool comm_queue_message(const uint8_t *src, size_t len)
{
    // simple blocking implementation
    for (uint32_t i = 0; i < len; i++) {
      while (!(USART1->ISR & USART_ISR_TXE));  // wait for tx to clear
      USART1->TDR = src[i];
    }
    return true;
}


void comm_consume_message(void)
{
    rx_buf_pos = 0;
    message_available = false;
}


void comm_setup(void)
{
    // initialize globals
    message_available = false;
    USART1->CR1 |= USART_CR1_RXNEIE;
}


emo_header *comm_peek_message(void)
{
    if (message_available) {
        return (emo_header *)rx_buf;
    } else {
        return NULL;
    }
}


void USART1_IRQHandler(void)
{
    int32_t new_char;
    int16_t needed;
    uint16_t n;

    new_char = USART1->RDR;  // must read the byte in all cases, to clear the UART.
    if (USART1->ISR & USART_ISR_ORE){
        USART1->ICR |= USART_ICR_ORECF;
    }

    if (message_available) {
        debug_printf("EMOLOG_EMBEDDED: Unexpected bytes from PC before having processed last message\n");
        return; // not our turn
    }

    if (rx_buf_pos >= sizeof(rx_buf)) {
        debug_printf("EMOLOG_EMBEDDED: RX Buffer Overflow! rx_buf_pos = %lu\n", rx_buf_pos);
    } else {
        rx_buf[rx_buf_pos++] = new_char;
    }

    needed = -1;
    while (needed < 0) {
        needed = emo_decode(rx_buf, rx_buf_pos);

        if (needed == 0) {
            message_available = true;
            break;
        } else if (needed < 0) {
            n = -needed;
            memcpy(rx_buf, rx_buf + n, rx_buf_pos - n); // buf: [garbage "-needed" bytes] [more-new-bytes buf_pos + "needed"]
            // buf = 0; 0, 1, 2 - 1 = 1: copy from 1 1 byte to 0
            rx_buf_pos -= n;
        }
    }
    assert(needed >= 0); // missing bytes, will wait for next call to the interrupt
}

