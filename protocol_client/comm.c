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


static volatile bool message_available = false;


static unsigned char recv_buf[1024];


static volatile uint32_t recv_buf_pos = 0;


void
UARTSend(const uint8_t *pui8Buffer, uint32_t ui32Count)
{
    //
    // Loop while there are more characters to send.
    //
    while(ui32Count--)
    {
        //
        // Write the next character to the UART.
        //
        ROM_UARTCharPut(UART0_BASE, *pui8Buffer++); // TODO: DMA
    }
}


void comm_queue_message(uint8_t *src, size_t len)
{
	UARTSend(src, len);
}


void comm_consume_message(void)
{
    recv_buf_pos = 0;
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
    ROM_UARTConfigSetExpClk(UART0_BASE, g_ui32SysClock, 115200,
                            (UART_CONFIG_WLEN_8 | UART_CONFIG_STOP_ONE |
                             UART_CONFIG_PAR_NONE));

    ROM_IntEnable(INT_UART0);
    ROM_UARTIntEnable(UART0_BASE, UART_INT_RX | UART_INT_RT);
}


emo_header *comm_peek_message(void)
{
	if (message_available) {
		return (emo_header *)recv_buf;
	} else {
		return NULL;
	}
}


void
UARTIntHandler(void)
{
    uint32_t status;
    int32_t new_char;
    int16_t needed;
    uint16_t n;

    //
    // Get the interrrupt status.
    //
    status = ROM_UARTIntStatus(UART0_BASE, true);

    //
    // Clear the asserted interrupts.
    //
    ROM_UARTIntClear(UART0_BASE, status);

    //
    // Loop while there are characters in the receive FIFO.
    //
    while(ROM_UARTCharsAvail(UART0_BASE))
    {
        new_char = ROM_UARTCharGetNonBlocking(UART0_BASE);
        if (recv_buf_pos >= sizeof(recv_buf)) {
            continue; // buffer overflow
        }
        if (message_available) {
            continue; // not our turn
        }
        recv_buf[recv_buf_pos++] = new_char;
    }

    needed = -1;
    while (needed < 0) {
        needed = emo_decode(recv_buf, recv_buf_pos);

        if (needed == 0) {
            message_available = true;
            break;
        } else if (needed < 0) {
            n = -needed;
            memcpy(recv_buf, recv_buf + n, recv_buf_pos - n); // buf: [garbage "-needed" bytes] [more-new-bytes buf_pos + "needed"]
            // buf = 0; 0, 1, 2 - 1 = 1: copy from 1 1 byte to 0
            recv_buf_pos -= n;
        }
    }
    assert(needed >= 0); // missing bytes, will wait for next call to the interrupt
}
