#include "zmk_usb_bridge_gui/usb_channel.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/usb/usb_device.h>

#define GUI_CDC_NODE DT_NODELABEL(gui_cdc_acm_uart)
#define LOG_CDC_NODE DT_NODELABEL(log_cdc_acm_uart)

static const struct device *const gui_dev = DEVICE_DT_GET(GUI_CDC_NODE);
static const struct device *const log_dev = DEVICE_DT_GET(LOG_CDC_NODE);

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

static void write_line(const struct device *dev, const char *line)
{
    if (dev == NULL || line == NULL || !channel_ready(dev)) {
        return;
    }

    for (const char *cursor = line; *cursor != '\0'; ++cursor) {
        uart_poll_out(dev, (unsigned char)*cursor);
    }

    uart_poll_out(dev, '\n');
}

int zmk_usb_bridge_gui_usb_channel_init(void)
{
    if (!device_is_ready(gui_dev) || !device_is_ready(log_dev)) {
        return -1;
    }

    return usb_enable(NULL);
}

bool zmk_usb_bridge_gui_usb_channel_gui_ready(void)
{
    return channel_ready(gui_dev);
}

void zmk_usb_bridge_gui_usb_channel_write_gui_line(const char *line)
{
    write_line(gui_dev, line);
}

void zmk_usb_bridge_gui_usb_channel_write_log_line(const char *line)
{
    write_line(log_dev, line);
}

int zmk_usb_bridge_gui_usb_channel_poll_gui_byte(unsigned char *byte)
{
    if (byte == NULL || !channel_ready(gui_dev)) {
        return -1;
    }

    return uart_poll_in(gui_dev, byte);
}
