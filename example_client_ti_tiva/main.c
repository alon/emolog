#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <math.h>

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

#include <emolog.h>

#include <emolog_embedded.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846 // pedantic
#endif

/* Water Pump Protocol */


uint32_t sys_clk_hz;

uint32_t sawtooth = 0;
float sine = 0;

// The error routine that is called if the driver library encounters an error.
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif


/* Main */


void delay_ms(uint32_t ms)
{
	SysCtlDelay(sys_clk_hz / 1000 / 3 * ms);
}


void setup_clock(void)
{
    sys_clk_hz = MAP_SysCtlClockFreqSet((SYSCTL_XTAL_25MHZ |
                                             SYSCTL_OSC_MAIN |
                                             SYSCTL_USE_PLL |
                                             SYSCTL_CFG_VCO_480), 120000000);
}

void setup_led(void)
{
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_GPION);
    SysCtlDelay(3);
    ROM_GPIOPinTypeGPIOOutput(GPIO_PORTN_BASE, GPIO_PIN_0); // led
}


void setup(void)
{
    setup_clock();
    emolog_init();
    setup_led();
    ROM_IntMasterEnable();
}


emo_error_t handle_app_specific_message(emo_header* message)
{
	return EMO_ERROR_UNEXPECTED_MESSAGE;
}


void main(void)
{
    setup();
    uint32_t ticks = 0;

    while (1) {
        sawtooth = (sawtooth + 1) % 100;
        sine = 50.0 * sin(2 * M_PI * ((float)ticks / 100.0));

        emolog_run_step();
        ticks++;
        delay_ms(50);
    }
}
