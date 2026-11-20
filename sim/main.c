/*
 * Simulated target ("virtual DUT") for system tests.
 *
 * Talks a line-based protocol on stdin/stdout, like a UART test interface on
 * a real board. The Python harness (tests/system) drives it; on real hardware
 * the same harness would talk to the board via a serial port (HIL).
 *
 * Commands:
 *   PRES 0|1           set presence sensor input
 *   BATT <mV>          set battery voltage
 *   ADV <ms>           advance simulated time (controller runs every 10 ms)
 *   TIME <ms>          re-init controller with clock at <ms> (overflow tests)
 *   CFG <key> <value>  change one config value, then re-init (keys below)
 *   STAT               print status line
 *   RESET              default config, clock 0
 * Output lines:
 *   EVT t=<ms> <NAME> [reason=..]
 *   STAT state=.. valve=.. flushes=.. hygiene=.. err=0x.. t=..
 *   OK / ERR <text>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "flush_ctrl.h"

#define TICK_MS 10u

static fc_t        fc;
static fc_config_t cfg;
static uint32_t    now_ms;
static int         presence;
static unsigned    batt_mV = 6000u;

static void print_events(uint8_t ev)
{
    if (ev & FC_EVT_FLUSH_START)
        printf("EVT t=%u FLUSH_START reason=%s\n", now_ms, fc_reason_name(fc.reason));
    if (ev & FC_EVT_FLUSH_END)
        printf("EVT t=%u FLUSH_END reason=%s\n", now_ms, fc_reason_name(fc.reason));
    if (ev & FC_EVT_FLUSH_ABORT) printf("EVT t=%u FLUSH_ABORT\n", now_ms);
    if (ev & FC_EVT_FAULT_SET)   printf("EVT t=%u FAULT_SET\n", now_ms);
    if (ev & FC_EVT_FAULT_CLEAR) printf("EVT t=%u FAULT_CLEAR\n", now_ms);
    if (ev & FC_EVT_BATT_WARN)   printf("EVT t=%u BATT_WARN\n", now_ms);
}

static int reinit(void)
{
    presence = 0;
    return fc_init(&fc, &cfg, now_ms) == FC_OK;
}

static int set_cfg(const char *key, unsigned long v)
{
    fc_config_t old = cfg;
    if      (!strcmp(key, "min_presence"))  cfg.min_presence_ms = (uint32_t)v;
    else if (!strcmp(key, "delay"))         cfg.flush_delay_ms = (uint32_t)v;
    else if (!strcmp(key, "duration"))      cfg.flush_duration_ms = (uint32_t)v;
    else if (!strcmp(key, "hygiene"))       cfg.hygiene_interval_ms = (uint32_t)v;
    else if (!strcmp(key, "stuck"))         cfg.sensor_stuck_ms = (uint32_t)v;
    else if (!strcmp(key, "batt_warn"))     cfg.batt_warn_mV = (uint16_t)v;
    else if (!strcmp(key, "batt_cutoff"))   cfg.batt_cutoff_mV = (uint16_t)v;
    else return 0;
    if (!reinit()) { cfg = old; reinit(); return 0; }
    return 1;
}

int main(void)
{
    char line[128];
    setvbuf(stdout, NULL, _IOLBF, 0);
    fc_default_config(&cfg);
    reinit();
    printf("READY hfc-sim\n");

    while (fgets(line, sizeof line, stdin)) {
        char cmd[16] = {0}, key[32] = {0};
        unsigned long a = 0, b = 0;
        int n = sscanf(line, "%15s %31s %lu", cmd, key, &b);
        if (n <= 0) continue;
        a = strtoul(key, NULL, 10);

        if (!strcmp(cmd, "PRES") && n >= 2)      { presence = (a != 0); puts("OK"); }
        else if (!strcmp(cmd, "BATT") && n >= 2) { batt_mV = (unsigned)a; puts("OK"); }
        else if (!strcmp(cmd, "ADV") && n >= 2) {
            for (unsigned long t = 0; t < a; t += TICK_MS) {
                now_ms += TICK_MS;   /* wraps naturally at 2^32 */
                print_events(fc_step(&fc, now_ms, presence != 0, (uint16_t)batt_mV));
            }
            puts("OK");
        }
        else if (!strcmp(cmd, "TIME") && n >= 2) { now_ms = (uint32_t)a; reinit(); puts("OK"); }
        else if (!strcmp(cmd, "CFG") && n >= 3) {
            puts(set_cfg(key, b) ? "OK" : "ERR config rejected");
        }
        else if (!strcmp(cmd, "STAT")) {
            printf("STAT state=%s valve=%d flushes=%u hygiene=%u err=0x%02X t=%u\n",
                   fc_state_name(fc.state), fc.valve_open ? 1 : 0,
                   fc.flush_count, fc.hygiene_count, fc.errors, now_ms);
        }
        else if (!strcmp(cmd, "RESET")) {
            fc_default_config(&cfg); now_ms = 0; batt_mV = 6000u; reinit(); puts("OK");
        }
        else if (!strcmp(cmd, "QUIT")) { break; }
        else { puts("ERR unknown command"); }
    }
    return 0;
}
