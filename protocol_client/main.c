#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
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


#include <cmwpp.h>



/* Water Pump Protocol */

unsigned char buf[1024];

volatile bool message_available = false;
volatile uint32_t buf_pos = 0;


/* UART */

uint32_t g_ui32SysClock;

// The error routine that is called if the driver library encounters an error.
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif


void
UARTIntHandler(void)
{
    uint32_t ui32Status;
    int32_t new_char;
    int16_t needed;
    uint16_t n;

    //
    // Get the interrrupt status.
    //
    ui32Status = ROM_UARTIntStatus(UART0_BASE, true);

    //
    // Clear the asserted interrupts.
    //
    ROM_UARTIntClear(UART0_BASE, ui32Status);

    //
    // Loop while there are characters in the receive FIFO.
    //
    while(ROM_UARTCharsAvail(UART0_BASE))
    {
        //
        // Read the next character from the UART and write it back to the UART.
        //
        new_char = ROM_UARTCharGetNonBlocking(UART0_BASE);
        if (buf_pos >= sizeof(buf)) {
            continue; // buffer overflow
        }
        if (message_available) {
            continue; // not our turn
        }

        buf[buf_pos++] = new_char;
    }

    needed = -1;
    while (needed < 0) {
        needed = wpp_decode(buf, buf_pos);

        if (needed == 0) {
            message_available = true;
            break;
        } else if (needed < 0) {
            n = -needed;
            memcpy(buf, buf + n, buf_pos - n); // buf: [garbage "-needed" bytes] [more-new-bytes buf_pos + "needed"]
            // buf = 0; 0, 1, 2 - 1 = 1: copy from 1 1 byte to 0
            buf_pos -= n;
        }
    }
    assert(needed > 0); // missing bytes, will wait for next call to the interrupt
}


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
        ROM_UARTCharPutNonBlocking(UART0_BASE, *pui8Buffer++);
    }
}


/* Main */

void setup(void)
{
    // initialize globals
    message_available = false;

    // initialize hardware

    g_ui32SysClock = MAP_SysCtlClockFreqSet((SYSCTL_XTAL_25MHZ |
                                             SYSCTL_OSC_MAIN |
                                             SYSCTL_USE_PLL |
                                             SYSCTL_CFG_VCO_480), 120000000);
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_GPION);
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOA);
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_UART0);
    SysCtlDelay(3);
    GPIOPinConfigure(GPIO_PA0_U0RX);
    GPIOPinConfigure(GPIO_PA1_U0TX);
    ROM_GPIOPinTypeUART(GPIO_PORTA_BASE, GPIO_PIN_0 | GPIO_PIN_1);
    ROM_UARTConfigSetExpClk(UART0_BASE, g_ui32SysClock, 115200,
                            (UART_CONFIG_WLEN_8 | UART_CONFIG_STOP_ONE |
                             UART_CONFIG_PAR_NONE));

    /* GPIO initialization */
    ROM_GPIOPinTypeGPIOOutput(GPIO_PORTN_BASE, GPIO_PIN_0);
    ROM_UARTConfigSetExpClk(UART0_BASE, g_ui32SysClock, 115200,
                            (UART_CONFIG_WLEN_8 | UART_CONFIG_STOP_ONE |
                             UART_CONFIG_PAR_NONE));

    ROM_IntMasterEnable();
    ROM_IntEnable(INT_UART0);
    ROM_UARTIntEnable(UART0_BASE, UART_INT_RX | UART_INT_RT);
}


void handle_message(void)
{
    uint8_t buf_out[32];
    uint16_t encoded_len;

    wpp_header *header = (wpp_header *)buf;

    if (header->type == WPP_MESSAGE_TYPE_VERSION) {
        encoded_len = wpp_encode_version(buf_out);
        UARTSend(buf_out, encoded_len);
    }
}


void main(void)
{
    setup();

    while (1) {
        if (message_available) {
            handle_message();
        } else {
            SysCtlDelay(100);
        }
    }
}
