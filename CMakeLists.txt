cmake_minimum_required(VERSION 3.20.0)

set(ZMK_USB_BRIDGE_GUI_DEFAULT_USER_CONF
    ${CMAKE_CURRENT_SOURCE_DIR}/config/user.conf)

if(DEFINED EXTRA_CONF_FILE)
    set(EXTRA_CONF_FILE
        "${ZMK_USB_BRIDGE_GUI_DEFAULT_USER_CONF};${EXTRA_CONF_FILE}")
else()
    set(EXTRA_CONF_FILE ${ZMK_USB_BRIDGE_GUI_DEFAULT_USER_CONF})
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(zmk_usb_bridge_gui)

target_include_directories(app PRIVATE main/include)

target_sources(app PRIVATE
    main/app_main.c
    main/src/ble_scan.c
    main/src/protocol.c
    main/src/runtime_state.c
    main/src/startup.c
    main/src/usb_channel.c
)
