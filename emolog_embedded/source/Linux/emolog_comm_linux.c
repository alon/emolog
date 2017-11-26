// General includes
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

// Socket - TCP socket used, we run as a server
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdio.h>

#include "emolog_comm.h"



#define handle_error(msg) \
    do { perror(msg); exit(EXIT_FAILURE); } while (0)

static int cfd;

static uint8_t buf[128 * 1024];
static size_t buf_pos = 0;
static bool message_available = false;



static uint16_t get_connection_port(void)
{
    uint16_t ret = 10000;
    const char* port = getenv("EMOLOG_PC_PORT");
    if (port != NULL)
    {
        ret = atoi(port);
    }
    return ret;
}

static void init_wait_for_socket_connection()
{
    struct sockaddr_in my_addr, peer_addr;
    socklen_t peer_addr_size;
    int sfd;

    sfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sfd == 0)
        handle_error("linux: socket");

    memset(&my_addr, 0, sizeof(my_addr));
    my_addr.sin_family = AF_INET;
    my_addr.sin_port = htons(get_connection_port());
    if (bind(sfd, (struct sockaddr*)&my_addr, sizeof(my_addr)) == -1)
        handle_error("linux: bind");

    if (listen(sfd, 1) == -1)
        handle_error("linux: listen");

    peer_addr_size = sizeof(peer_addr);
    cfd = accept(sfd, (struct sockaddr *) &peer_addr, &peer_addr_size);
    if (cfd == -1)
        handle_error("linux: accept");
}


void comm_setup(void)
{
    init_wait_for_socket_connection();
}


static void consume_available_bytes(void)
{
    ssize_t ret = recv(cfd, buf, sizeof(buf) - buf_pos, MSG_DONTWAIT);
    if (ret == -1)
        return; // this is normal, but there are some cases in which we should quit?
    buf_pos += ret;
    int dec_ret = emo_decode(buf, buf_pos);
    message_available = (dec_ret == 0);
    if (dec_ret < 0) {
        memcpy(buf, buf - dec_ret, buf_pos + dec_ret);
    }
    //printf("pc: read bytes. pos = %d. have message %d\n", buf_pos, message_available);
}


emo_header *comm_peek_message(void)
{
    if (message_available) {
        return (emo_header *)buf;
    }
    consume_available_bytes();
    if (!message_available) {
        return NULL;
    }
    return (emo_header *)buf;
}


void comm_consume_message(void)
{
    if (!message_available)
    {
        return;
    }
    //printf("linux: consumed message\n");
    message_available = 0;
    buf_pos = 0;
}


bool comm_queue_message(const uint8_t *src, size_t len)
{
    //printf("linux: sending %d\n", len);
    if (-1 == send(cfd, src, len, 0))
        handle_error("linux: send");
    return true;
}
