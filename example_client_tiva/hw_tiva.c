#include "hw_tiva.h"

#include <stdbool.h>
#include <stdint.h>

#include "driverlib/sysctl.h"
#include "driverlib/interrupt.h"


/* Hardware abstraction for TI Tiva C series MCUs.
 * This file runs as-is on a TI Connected Launchpad (EK-TM4C1294XL)
 * but can be adapted to other Tiva platforms with minimal changes */


uint32_t sys_clk_hz;

// The error routine that is called by the TivaWare driver library if it encounters an error.
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif


void init_clock(void)
{
    sys_clk_hz = SysCtlClockFreqSet((SYSCTL_XTAL_25MHZ | SYSCTL_OSC_MAIN | SYSCTL_USE_PLL | SYSCTL_CFG_VCO_480), 120000000);
}


void hw_init(void)
{
    init_clock();
    IntMasterEnable();
}


void delay_ms(uint32_t ms)
{
    SysCtlDelay(sys_clk_hz / 1000 / 3 * ms);
}
