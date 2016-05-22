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

#include "comm.h"

