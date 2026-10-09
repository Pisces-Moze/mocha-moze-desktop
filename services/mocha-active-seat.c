/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdio.h>
#include <systemd/sd-login.h>
int main(void) {
    puts(sd_uid_is_on_seat(1000, 1, "seat0") > 0 ? "active" : "inactive");
    return 0;
}
