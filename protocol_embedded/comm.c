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


#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>


#include "inc/hw_ints.h"
#include "inc/hw_memmap.h"
#include "inc/hw_types.h"
#include "driverlib/debug.h"
#include "driverlib/gpio.h"
#include "driverlib/interrupt.h"
#include "driverlib/pin_map.h"
#include "driverlib/rom.h"
#include "driverlib/rom_map.h"
#include "driverlib/sysctl.h"
#include "driverlib/uart.h"

#include "globals.h"
#include "comm.h"
#include "tx_circular_buffer.h"

static volatile bool message_available = false;

static unsigned char rx_buf[RX_BUF_SIZE];
static volatile uint32_t rx_buf_pos = 0;


bool comm_queue_message(uint8_t *src, size_t len)
{
	if (tx_buf_bytes_free() < len)
	{
		return false; // not enough space
	}

	bool ret;
	int i;
	for (i = 0; i < len; i++)
	{
		ret = tx_buf_put(src[i]);
		assert(ret);	// should never fail to put all bytes since free space was checked
	}
	handle_uart_tx();

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

    // initialize hardware
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOA);
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_UART0);
    SysCtlDelay(3);
    GPIOPinConfigure(GPIO_PA0_U0RX);
    GPIOPinConfigure(GPIO_PA1_U0TX);
    ROM_GPIOPinTypeUART(GPIO_PORTA_BASE, GPIO_PIN_0 | GPIO_PIN_1);
    ROM_UARTConfigSetExpClk(UART0_BASE, sys_clk_hz, 115200,
                            (UART_CONFIG_WLEN_8 | UART_CONFIG_STOP_ONE |
                             UART_CONFIG_PAR_NONE));

    ROM_UARTFIFOEnable(UART0_BASE);
    ROM_IntEnable(INT_UART0);
    ROM_UARTFIFOLevelSet(UART0_BASE, UART_FIFO_TX4_8, UART_FIFO_RX4_8);
    ROM_UARTTxIntModeSet(UART0_BASE, UART_TXINT_MODE_EOT);	// TX interrupt only on TX FIFO completely empty (rather than at specified level)

    // Note that the RX interrupt happens only at the FIFO level specified. Therefore, we also need to interrupt on the RX timeout
    // (happens after 32 bits's time at the UART's baud rate), otherwise we won't trigger an interrupt on the last bytes.
    ROM_UARTIntEnable(UART0_BASE, UART_INT_RX | UART_INT_RT | UART_INT_TX);
}


emo_header *comm_peek_message(void)
{
	if (message_available) {
		return (emo_header *)rx_buf;
	} else {
		return NULL;
	}
}


void uart_int_handler(void)
{
    uint32_t status;

    status = ROM_UARTIntStatus(UART0_BASE, true);
    ROM_UARTIntClear(UART0_BASE, status);     		// Clear all asserted interrupts for the UART

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
     while(ROM_UARTCharsAvail(UART0_BASE))
     {
         new_char = ROM_UARTCharGetNonBlocking(UART0_BASE);
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
	int ret;
	while (!tx_buf_is_empty() && UARTSpaceAvail(UART0_BASE))
	{
		ret = UARTCharPutNonBlocking(UART0_BASE, tx_buf_get());
		assert(ret);	// should always return true since we just checked there is space in the UART TX buffer
	}
}



