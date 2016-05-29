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


#include <emolog.h>

#include "comm.h"
#include "sampler.h"


/* Water Pump Protocol */


uint32_t g_ui32SysClock;


// The error routine that is called if the driver library encounters an error.
#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif


/* Main */

void setup_clock(void)
{
    g_ui32SysClock = MAP_SysCtlClockFreqSet((SYSCTL_XTAL_25MHZ |
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
    comm_setup();
    setup_led();
    ROM_IntMasterEnable();
}


// helpers

void queue_nack(uint8_t reply_to_seq, emo_error_t error)
{
    uint8_t buf_out[32];
    uint16_t encoded_len;

    encoded_len = emo_encode_nack(buf_out, reply_to_seq, error);
    assert(encoded_len <= sizeof(buf_out));
    comm_queue_message(buf_out, encoded_len);
}


void handle_message(emo_header *header)
{
    uint8_t buf_out[32];
    uint16_t encoded_len;

    switch (header->type) {
    case EMO_MESSAGE_TYPE_VERSION: {
        encoded_len = emo_encode_version(buf_out, header->seq);
        comm_queue_message(buf_out, encoded_len);
        break;
    }
    case EMO_MESSAGE_TYPE_PING: {
    	// TODO
    	break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE: {
    	emo_sampler_register_variable *m = (emo_sampler_register_variable *)header;
    	emo_sampler_register_variable_payload *p = &m->p;
    	sampler_register_variable(p->phase_ticks, p->period_ticks, p->address, p->size, header->seq);
    	break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_CLEAR: {
    	sampler_clear();
    	break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_START: {
    	sampler_start();
    	break;
    }
    case EMO_MESSAGE_TYPE_SAMPLER_STOP: {
    	sampler_stop();
    	break;
    }
    default: {
    	queue_nack(header->seq, EMO_ERROR_UNEXPECTED_MESSAGE);
    }
    }
}


void main(void)
{
    setup();

    while (1) {
    	emo_header *header;
        if ((header = comm_peek_message()) != NULL) {
            handle_message(header);
            comm_consume_message();
        }
        sampler_sample();
    }
}
