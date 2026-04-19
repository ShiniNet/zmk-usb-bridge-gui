#include "zmk_usb_bridge_gui/usb_channel.h"

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/usb/usb_device.h>

#define GUI_CDC_NODE DT_NODELABEL(gui_cdc_acm_uart)
#define LOG_CDC_NODE DT_NODELABEL(log_cdc_acm_uart)
#define GUI_TX_RING_SIZE 16384
#define LOG_TX_RING_SIZE 2048
#define TX_CHUNK_SIZE 64
#define GUI_WRITER_STACK_SIZE 2048
#define LOG_WRITER_STACK_SIZE 1024
#define GUI_WRITER_THREAD_PRIORITY 8
#define LOG_WRITER_THREAD_PRIORITY 12
#define LINE_BUFFER_SIZE CONFIG_ZMK_USB_BRIDGE_GUI_PROTOCOL_BUFFER_SIZE

static const struct device *const gui_dev = DEVICE_DT_GET(GUI_CDC_NODE);
static const struct device *const log_dev = DEVICE_DT_GET(LOG_CDC_NODE);

struct async_channel {
    const struct device *dev;
    struct ring_buf tx_ring;
    struct k_sem data_ready;
    struct k_mutex lock;
};

static uint8_t gui_tx_ring_storage[GUI_TX_RING_SIZE];
static uint8_t log_tx_ring_storage[LOG_TX_RING_SIZE];
static struct async_channel gui_channel = {.dev = gui_dev};
static struct async_channel log_channel = {.dev = log_dev};
static K_THREAD_STACK_DEFINE(gui_writer_stack, GUI_WRITER_STACK_SIZE);
static K_THREAD_STACK_DEFINE(log_writer_stack, LOG_WRITER_STACK_SIZE);
static struct k_thread gui_writer_thread;
static struct k_thread log_writer_thread;

static bool channel_ready(const struct device *dev)
{
    uint32_t dtr = 0U;

    if (!device_is_ready(dev)) {
        return false;
    }

    if (uart_line_ctrl_get(dev, UART_LINE_CTRL_DTR, &dtr) != 0) {
        return false;
    }

    return dtr != 0U;
}

static void async_channel_init(
    struct async_channel *channel,
    uint8_t *storage,
    size_t storage_size)
{
    ring_buf_init(&channel->tx_ring, storage_size, storage);
    k_sem_init(&channel->data_ready, 0, K_SEM_MAX_LIMIT);
    k_mutex_init(&channel->lock);
}

static void async_channel_writer(void *channel_ptr, void *unused_a, void *unused_b)
{
    struct async_channel *channel = channel_ptr;
    uint8_t chunk[TX_CHUNK_SIZE];

    ARG_UNUSED(unused_a);
    ARG_UNUSED(unused_b);

    while (true) {
        k_sem_take(&channel->data_ready, K_FOREVER);

        while (true) {
            uint32_t chunk_size;

            if (!channel_ready(channel->dev)) {
                k_msleep(10);
                continue;
            }

            k_mutex_lock(&channel->lock, K_FOREVER);
            chunk_size = ring_buf_get(&channel->tx_ring, chunk, sizeof(chunk));
            k_mutex_unlock(&channel->lock);

            if (chunk_size == 0U) {
                break;
            }

            for (uint32_t index = 0; index < chunk_size; ++index) {
                uart_poll_out(channel->dev, chunk[index]);
            }
        }
    }
}

static void start_async_channel_writer(
    struct async_channel *channel,
    struct k_thread *thread,
    k_thread_stack_t *stack,
    size_t stack_size,
    int priority)
{
    k_thread_create(
        thread,
        stack,
        stack_size,
        async_channel_writer,
        channel,
        NULL,
        NULL,
        priority,
        0,
        K_NO_WAIT);
}

static void write_line(struct async_channel *channel, const char *line)
{
    size_t line_length;
    size_t required;

    if (channel == NULL || line == NULL) {
        return;
    }

    line_length = strnlen(line, LINE_BUFFER_SIZE);
    if (line_length >= LINE_BUFFER_SIZE) {
        return;
    }

    required = line_length + 1U;

    k_mutex_lock(&channel->lock, K_FOREVER);
    if (ring_buf_space_get(&channel->tx_ring) < required) {
        k_mutex_unlock(&channel->lock);
        return;
    }

    (void)ring_buf_put(&channel->tx_ring, (const uint8_t *)line, line_length);
    (void)ring_buf_put(&channel->tx_ring, (const uint8_t *)"\n", 1U);
    k_mutex_unlock(&channel->lock);
    k_sem_give(&channel->data_ready);
}

int zmk_usb_bridge_gui_usb_channel_init(void)
{
    if (!device_is_ready(gui_dev) || !device_is_ready(log_dev)) {
        return -1;
    }

    async_channel_init(&gui_channel, gui_tx_ring_storage, sizeof(gui_tx_ring_storage));
    async_channel_init(&log_channel, log_tx_ring_storage, sizeof(log_tx_ring_storage));
    start_async_channel_writer(
        &gui_channel,
        &gui_writer_thread,
        gui_writer_stack,
        K_THREAD_STACK_SIZEOF(gui_writer_stack),
        GUI_WRITER_THREAD_PRIORITY);
    start_async_channel_writer(
        &log_channel,
        &log_writer_thread,
        log_writer_stack,
        K_THREAD_STACK_SIZEOF(log_writer_stack),
        LOG_WRITER_THREAD_PRIORITY);

    return usb_enable(NULL);
}

bool zmk_usb_bridge_gui_usb_channel_gui_ready(void)
{
    return channel_ready(gui_dev);
}

void zmk_usb_bridge_gui_usb_channel_write_gui_line(const char *line)
{
    write_line(&gui_channel, line);
}

void zmk_usb_bridge_gui_usb_channel_write_log_line(const char *line)
{
    write_line(&log_channel, line);
}

int zmk_usb_bridge_gui_usb_channel_poll_gui_byte(unsigned char *byte)
{
    if (byte == NULL || !channel_ready(gui_dev)) {
        return -1;
    }

    return uart_poll_in(gui_dev, byte);
}
