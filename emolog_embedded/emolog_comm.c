
/*
 * Design of communication
 * =======================
 *
 * A single buffer is used for all messages.
 * There are two types of messages:
 *  High priority
 *  Low priority
 *
 * Low priority messages of size N are accepted into the buffer only when it has at least HIGH_PRIORITY_BUFFER_BYTES + N bytes
 * available.
 *
 * High priority messages of size N are accepted if there are N bytes available.
 *
 * The API mirrors the protocol otherwise.
 */

#include "emolog_comm.h"

#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "inc/hw_ints.h"
#include "inc/hw_memmap.h"
#include "inc/hw_types.h"
#include "inc/hw_uart.h"
#include "driverlib/debug.h"
#include "driverlib/gpio.h"
#include "driverlib/interrupt.h"
#include "driverlib/pin_map.h"
#include "driverlib/rom.h"
#include "driverlib/rom_map.h"
#include "driverlib/sysctl.h"
#include "driverlib/uart.h"

#include "emolog_tx_circular_buffer.h"

static volatile bool message_available = false;

static unsigned char rx_buf[RX_BUF_SIZE];
static volatile uint32_t rx_buf_pos = 0;


bool comm_queue_message(const uint8_t *src, size_t len)
{
	bool ret;

	ret = tx_buf_put_bytes(src, len);
	if (ret)
	{
		handle_uart_tx();
	}
	return ret;
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
}


emo_header *comm_peek_message(void)
{
	if (message_available) {
		return (emo_header *)rx_buf;
	} else {
		return NULL;
	}
}


void uart0_interrupt(void)
{
    uint32_t status;

    status = UARTIntStatus(UART0_BASE, true);
    UARTIntClear(UART0_BASE, status);     		// Clear all asserted interrupts for the UART

    if (status & UART_INT_TX){
    	handle_uart_tx();
    }

    if (status & (UART_INT_RX | UART_INT_RT )){
    	handle_uart_rx();
    }
}


// called from the UART interrupt handler when the RX FIFO is over the specified level or when the receive timeout has triggered
void handle_uart_rx(void)
{
    int32_t new_char;
    int16_t needed;
    uint16_t n;

    // Loop while there are characters in the receive FIFO.
     while(UARTCharsAvail(UART0_BASE))
     {
         new_char = UARTCharGetNonBlocking(UART0_BASE);
         if (rx_buf_pos >= sizeof(rx_buf)) {
             continue; // buffer overflow
         }
         if (message_available) {
             continue; // not our turn
         }
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


// called either from the UART interrupt handler when all the bytes in the tx FIFO have been transmitted,
// or from comm_queue_message() to get the initial transmission going
void handle_uart_tx(void)
{
	unsigned len = tx_buf_len();
	while (len-- > 0 && !(HWREG(UART0_BASE + UART_O_FR) & UART_FR_TXFF) )
	{
		HWREG(UART0_BASE + UART_O_DR) = tx_buf_get_unsafe();
	}
}
