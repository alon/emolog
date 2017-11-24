/* Emolog client example - Hardware abstraction for TI Tiva C series MCUs.
 *
 * This file can be used as-is on a TI Connected Launchpad (EK-TM4C1294XL)
 * but can be adapted to other Tiva platforms with minimal changes.
 * If using the Connected Launchpad, wire it as follows:
 * MCU pin PC4 (UART7 RX) to USB-UART adapter's TX
 * MCU pin PC5 (UART7 TX) to USB-UART adapter's RX
 * and of course Launchpad's ground to USB-UART adapter's ground.
 */


// General includes
#include <stdbool.h>
#include <stdint.h>

// TivaWare library includes
#include "inc/hw_ints.h"
#include "inc/hw_memmap.h"
#include "driverlib/pin_map.h"
#include "driverlib/sysctl.h"
#include "driverlib/interrupt.h"
#include "driverlib/gpio.h"
#include "driverlib/uart.h"
#include "utils/uartstdio.h"


#include "../examples_common/emolog_example_client.h" // include for example code that is common to all platforms
#include "emolog_embedded.h"       // for calling emolog_init()
#include "emolog_comm.h"
#include "emolog_sampler.h"
#include "emolog_protocol.h"


#define EMOLOG_BAUD_RATE_HZ         1000000
#define AUX_UART_BAUD_RATE_HZ       1000000


uint32_t sys_clk_hz;

// The error routine that is called by the TivaWare driver library if it encounters an error.
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif


// These delay functions are not very accurate as they rely on a busy loop that can be subject to wait states and stuff
 void delay_us(uint32_t us)
{
    SysCtlDelay(sys_clk_hz / 1000000 / 3 * us);
}


 void delay_ms(uint32_t ms)
{
    SysCtlDelay(sys_clk_hz / 1000 / 3 * ms);
}


 void init_clock(void)
{
    sys_clk_hz = SysCtlClockFreqSet((SYSCTL_XTAL_25MHZ | SYSCTL_OSC_MAIN | SYSCTL_USE_PLL | SYSCTL_CFG_VCO_480), 120000000);
}


void init_emolog_uart()
// Emolog is defined here to be on UART7. Modify if your connections are different.
{
    SysCtlPeripheralEnable(SYSCTL_PERIPH_UART7);
    SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOC);
    delay_us(10);

    GPIOPinConfigure(GPIO_PC4_U7RX);
    GPIOPinTypeUART(GPIO_PORTC_BASE, GPIO_PIN_4);
    GPIOPinConfigure(GPIO_PC5_U7TX);
    GPIOPinTypeUART(GPIO_PORTC_BASE, GPIO_PIN_5);

    UARTConfigSetExpClk(UART7_BASE, sys_clk_hz, EMOLOG_BAUD_RATE_HZ, (UART_CONFIG_WLEN_8 | UART_CONFIG_STOP_ONE | UART_CONFIG_PAR_NONE));
    UARTFIFOEnable(UART7_BASE);
    IntEnable(INT_UART7);
    UARTFIFOLevelSet(UART7_BASE, UART_FIFO_TX1_8, UART_FIFO_RX4_8);
    UARTTxIntModeSet(UART7_BASE, UART_TXINT_MODE_EOT);  // TX interrupt only on TX FIFO completely empty (rather than at specified level)

    // Note that the RX interrupt happens only at the FIFO level specified. Therefore, we also need to interrupt on the RX timeout
    // (happens after 32 bits time at the UART's baud rate), otherwise we won't trigger an interrupt on the last bytes.
    UARTIntEnable(UART7_BASE, UART_INT_RX | UART_INT_RT | UART_INT_TX);
}


void init_aux_uart()
// the aux UART is used for debug prints using UARTprintf().
// it's defined here to be on UART0, which on the Connected Launchpad board is wired
// to the debugger's auxiliary COM port. Just attach the Launchpad's USB and you'll have access to this serial port.
{
    SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOA);
    SysCtlPeripheralEnable(SYSCTL_PERIPH_UART0);
    delay_us(10);

    GPIOPinConfigure(GPIO_PA0_U0RX);
    GPIOPinTypeUART(GPIO_PORTA_BASE, GPIO_PIN_0);
    GPIOPinConfigure(GPIO_PA1_U0TX);
    GPIOPinTypeUART(GPIO_PORTA_BASE, GPIO_PIN_1);

    UARTStdioConfig(0, AUX_UART_BAUD_RATE_HZ, sys_clk_hz);     // Initialize the UART for console I/O.
}


void hw_init(void)
{
    init_clock();
    init_emolog_uart();
    init_aux_uart();
    IntMasterEnable();
}


int main(void)
{
    hw_init();     // platform specific HW initialization.
    emolog_example_main_loop(); // this never returns
}

