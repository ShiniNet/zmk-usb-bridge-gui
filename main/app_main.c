#include "zmk_usb_bridge_gui/startup.h"

#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(zubg_app, LOG_LEVEL_INF);

int main(void)
{
    LOG_INF("zmk-usb-bridge-gui firmware skeleton starting");
    zmk_usb_bridge_gui_startup_run();
    return 0;
}
