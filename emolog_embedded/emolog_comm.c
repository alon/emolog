
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

#include "../../pump_drive_tiva/Hardware.h"

#define RX_BUF_SIZE			1024
#define TX_BUF_SIZE			5586 // 19 * 294 - did problems at some point (long repeating sequences of -293,A>0,B>0,C>0 tick jumps)


static volatile bool message_available = false;

static unsigned char rx_buf[RX_BUF_SIZE];
static volatile uint32_t rx_buf_pos = 0;


/**
 *  Circular Transmit buffer
 */


// This is no longer an encapsulated circular buffer, it is used by emolog_comm as well. Should
// be moved there and re-static-ed later.
static unsigned char tx_buf[TX_BUF_SIZE];

volatile uint32_t tx_buf_read_pos = 0;	// points at the first (the oldest) byte in the buffer
volatile uint32_t tx_buf_write_pos = 0;	// points where a new byte should go
static bool is_empty = true;


int tx_buf_bytes_free(void)
{
	if (is_empty) return (TX_BUF_SIZE);

	return (TX_BUF_SIZE - (tx_buf_write_pos - tx_buf_read_pos)) % TX_BUF_SIZE;
}


bool tx_buf_put_bytes(const uint8_t *src, size_t len)
{
	if (tx_buf_bytes_free() < len)
	{
		debug("tx_buf_put_bytes: tx buffer full: %d < %d\n", tx_buf_bytes_free(), len);
		return false;
	}

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


int tx_buf_len(void)
{
	if (is_empty) return 0;
	return (tx_buf_write_pos - tx_buf_read_pos) % TX_BUF_SIZE;
}


/**
 * Communication
 */

bool comm_queue_message(const uint8_t *src, size_t len)
{
	bool ret;

	IntDisable(INT_UART0);
	ret = tx_buf_put_bytes(src, len);
	if (ret)
	{
		handle_uart_tx();
	}
	IntEnable(INT_UART0);
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

    set_yellow_led(ON);
    status = UARTIntStatus(UART0_BASE, true);
    UARTIntClear(UART0_BASE, status);     		// Clear all asserted interrupts for the UART

    IntDisable(INT_UART0);
    if (status & UART_INT_TX){
    	handle_uart_tx();
    }

    if (status & (UART_INT_RX | UART_INT_RT )){
    	handle_uart_rx();
    }
    IntEnable(INT_UART0);
    set_yellow_led(OFF);
}


// called from the UART interrupt handler when the RX FIFO is over the specified level or when the receive timeout has triggered
void handle_uart_rx(void)
{
    int32_t new_char;
    int16_t needed;
    uint16_t n;

    if (message_available) {
    	debug("EMOLOG_EMBEDDED: Unexpected bytes from PC before having processed last message\n");
   	    return; // not our turn
    }

    // Loop while there are characters in the receive FIFO.
    while(UARTCharsAvail(UART0_BASE))
    {
        new_char = UARTCharGetNonBlocking(UART0_BASE);
        if (rx_buf_pos >= sizeof(rx_buf)) {
            debug("EMOLOG_EMBEDDED: RX Buffer Overflow! rx_buf_pos = %u, rx_buf = %u\n", rx_buf_pos, rx_buf);
            continue; // buffer overflow
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
	unsigned char *read = tx_buf + tx_buf_read_pos;
	unsigned written = 0;

	if (len == 0)
	{
		return;
	}

	while (len-- > 0 && !(HWREG(UART0_BASE + UART_O_FR) & UART_FR_TXFF) )
	{
		HWREG(UART0_BASE + UART_O_DR) = *read;
		read++;
		if (read >= tx_buf + TX_BUF_SIZE) read = tx_buf;
		written++;
	}
	tx_buf_read_pos = (tx_buf_read_pos + written) % TX_BUF_SIZE;
	if (tx_buf_read_pos == tx_buf_write_pos) {
		is_empty = true;
		tx_buf_read_pos = tx_buf_write_pos = 0;
	}
}
