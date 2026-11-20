/*
 * Unit tests (component level, ISTQB) for flush_ctrl.c.
 * Tiny self-made framework so the project builds with only gcc + make.
 * Each test names its test technique and requirement in the comment.
 */
#include <stdio.h>
#include <string.h>
#include "flush_ctrl.h"

static int g_fail, g_run;
#define CHECK(cond) do { if (!(cond)) { \
    printf("    FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); g_fail++; return; } } while (0)
#define RUN(fn) do { int f0 = g_fail; g_run++; fn(); \
    printf("%s %s\n", (g_fail == f0) ? "PASS" : "FAIL", #fn); } while (0)

#define OK_mV 6000u

/* helper: run the controller from t0 to t1 in 10 ms ticks, collect events */
static uint8_t run(fc_t *fc, uint32_t *t, uint32_t dur, int pres, uint16_t mV)
{
    uint8_t all = 0;
    for (uint32_t i = 0; i < dur; i += 10u) {
        *t += 10u;
        all |= fc_step(fc, *t, pres != 0, mV);
    }
    return all;
}

static void setup(fc_t *fc, uint32_t t0)
{
    fc_config_t c;
    fc_default_config(&c);
    (void)fc_init(fc, &c, t0);
}

/* ---------- configuration: boundary value analysis (REQ-03, REQ-04) ---------- */
static void tc_u01_config_flush_duration_bva(void)
{
    fc_t fc; fc_config_t c; fc_default_config(&c);
    c.flush_duration_ms = 0;                   CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
    c.flush_duration_ms = 1;                   CHECK(fc_init(&fc, &c, 0) == FC_OK);
    c.flush_duration_ms = FC_MAX_FLUSH_MS;     CHECK(fc_init(&fc, &c, 0) == FC_OK);
    c.flush_duration_ms = FC_MAX_FLUSH_MS + 1; CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
}

static void tc_u02_config_hygiene_interval_bva(void)
{
    fc_t fc; fc_config_t c; fc_default_config(&c);
    c.hygiene_interval_ms = FC_MIN_HYGIENE_MS - 1; CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
    c.hygiene_interval_ms = FC_MIN_HYGIENE_MS;     CHECK(fc_init(&fc, &c, 0) == FC_OK);
    c.hygiene_interval_ms = FC_MAX_HYGIENE_MS;     CHECK(fc_init(&fc, &c, 0) == FC_OK);
    c.hygiene_interval_ms = FC_MAX_HYGIENE_MS + 1; CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
}

static void tc_u03_config_invalid_combinations(void)   /* decision table */
{
    fc_t fc; fc_config_t c;
    fc_default_config(&c); c.batt_cutoff_mV = c.batt_warn_mV;  CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
    fc_default_config(&c); c.sensor_stuck_ms = c.min_presence_ms; CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
    fc_default_config(&c); c.min_presence_ms = 0;              CHECK(fc_init(&fc, &c, 0) == FC_ERR_CONFIG);
    CHECK(fc_init(NULL, &c, 0) == FC_ERR_CONFIG);
    CHECK(fc_init(&fc, NULL, 0) == FC_ERR_CONFIG);
}

/* ---------- presence: BVA on min_presence 3000 ms (REQ-01, REQ-02) ---------- */
static void tc_u04_presence_below_min_no_flush(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 2990, 1, OK_mV);                  /* 2.99 s: below boundary */
    uint8_t ev = run(&fc, &t, 10000, 0, OK_mV);
    CHECK(!(ev & FC_EVT_FLUSH_START));
    CHECK(fc.flush_count == 0);
}

static void tc_u05_presence_at_min_flushes(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 3000, 1, OK_mV);                  /* exactly 3.00 s */
    uint8_t ev = run(&fc, &t, 10000, 0, OK_mV);
    CHECK(ev & FC_EVT_FLUSH_START);
    CHECK(fc.flush_count == 1);
    CHECK(fc.reason == FC_REASON_USER);
}

/* ---------- state transition: valve timing (REQ-01, REQ-03) ---------- */
static void tc_u06_flush_delay_and_duration(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 5000, 1, OK_mV);
    run(&fc, &t, 990, 0, OK_mV);
    CHECK(!fc.valve_open);                         /* still in 1 s delay  */
    run(&fc, &t, 20, 0, OK_mV);
    CHECK(fc.valve_open);                          /* delay over          */
    run(&fc, &t, 3970, 0, OK_mV);
    CHECK(fc.valve_open);                          /* < 4 s open          */
    run(&fc, &t, 30, 0, OK_mV);
    CHECK(!fc.valve_open);                         /* closed at 4 s       */
}

static void tc_u07_user_returns_during_delay(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 4000, 1, OK_mV);
    run(&fc, &t, 500, 0, OK_mV);                   /* leaves briefly       */
    run(&fc, &t, 500, 1, OK_mV);                   /* comes back           */
    CHECK(fc.state == FC_OCCUPIED);
    CHECK(fc.flush_count == 0);
}

/* ---------- hygiene flush (REQ-04, REQ-05) ---------- */
static void tc_u08_hygiene_flush_after_72h(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 72u * 3600u * 1000u - 10u, 0, OK_mV);
    CHECK(fc.hygiene_count == 0 && !fc.valve_open);
    run(&fc, &t, 10, 0, OK_mV);
    CHECK(fc.valve_open && fc.reason == FC_REASON_HYGIENE);
    run(&fc, &t, 5000, 0, OK_mV);
    CHECK(fc.hygiene_count == 1);
}

static void tc_u09_hygiene_deferred_while_present(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 72u * 3600u * 1000u - 2000u, 0, OK_mV);
    run(&fc, &t, 5000, 1, OK_mV);                  /* due time passes while present */
    CHECK(fc.hygiene_count == 0 && !fc.valve_open);
    run(&fc, &t, 10000, 0, OK_mV);                 /* user flush resets the timer */
    CHECK(fc.flush_count == 1 && fc.reason == FC_REASON_USER);
}

/* ---------- sensor fault (REQ-06) ---------- */
static void tc_u10_sensor_stuck_sets_fault_and_recovers(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    /* presence starts at the first tick (t=10), so the boundary is t=600010 */
    uint8_t ev = run(&fc, &t, 10u * 60u * 1000u, 1, OK_mV);
    CHECK(!(ev & FC_EVT_FAULT_SET));               /* 9:59.99 -> no fault */
    ev = run(&fc, &t, 10, 1, OK_mV);
    CHECK(ev & FC_EVT_FAULT_SET);                  /* 10:00.00 -> fault   */
    CHECK(fc.state == FC_FAULT && (fc.errors & FC_ERR_SENSOR_STUCK));
    ev = run(&fc, &t, 10000, 0, OK_mV);
    CHECK(ev & FC_EVT_FAULT_CLEAR);
    CHECK(!(ev & FC_EVT_FLUSH_START));             /* no flush after fault */
}

static void tc_u11_hygiene_flush_runs_in_fault(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 72u * 3600u * 1000u + 5000u, 1, OK_mV);   /* stuck for 72 h */
    CHECK(fc.hygiene_count == 1);
    CHECK(fc.state == FC_FAULT);
}

/* ---------- battery: equivalence partitions + BVA (REQ-07) ---------- */
static void tc_u12_battery_partitions(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 10, 0, 4400);  CHECK(fc.errors == 0);                    /* ok   */
    run(&fc, &t, 10, 0, 4399);  CHECK(fc.errors == FC_ERR_BATT_LOW);      /* warn */
    run(&fc, &t, 10, 0, 4000);  CHECK(!(fc.errors & FC_ERR_BATT_CUTOFF));
    run(&fc, &t, 10, 0, 3999);  CHECK(fc.errors & FC_ERR_BATT_CUTOFF);    /* off  */
    run(&fc, &t, 10, 0, 4050);  CHECK(fc.errors & FC_ERR_BATT_CUTOFF);    /* hysteresis */
    run(&fc, &t, 10, 0, 4100);  CHECK(!(fc.errors & FC_ERR_BATT_CUTOFF));
}

static void tc_u13_no_flush_below_cutoff(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 5000, 1, 3900);
    run(&fc, &t, 10000, 0, 3900);
    CHECK(fc.flush_count == 0 && !fc.valve_open && fc.state == FC_IDLE);
}

static void tc_u14_brownout_during_flush_closes_valve(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    run(&fc, &t, 5000, 1, OK_mV);
    run(&fc, &t, 1500, 0, OK_mV);
    CHECK(fc.valve_open);
    uint8_t ev = run(&fc, &t, 10, 0, 3500);
    CHECK(ev & FC_EVT_FLUSH_ABORT);
    CHECK(!fc.valve_open);
}

/* ---------- timer overflow (REQ-09) ---------- */
static void tc_u15_tick_wraparound(void)
{
    fc_t fc; uint32_t t = 0xFFFFFFFFu - 1500u; setup(&fc, t);   /* wraps in 1.5 s */
    run(&fc, &t, 1000, 1, OK_mV);                  /* only 1 s presence */
    run(&fc, &t, 10000, 0, OK_mV);
    CHECK(fc.flush_count == 0);                    /* must NOT flush */
    run(&fc, &t, 4000, 1, OK_mV);
    run(&fc, &t, 10000, 0, OK_mV);
    CHECK(fc.flush_count == 1);
}

/* ---------- diagnostics strings used in logs / telemetry (REQ-08) ---------- */
static void tc_u16_state_and_reason_names(void)
{
    CHECK(strcmp(fc_state_name(FC_IDLE), "IDLE") == 0);
    CHECK(strcmp(fc_state_name(FC_OCCUPIED), "OCCUPIED") == 0);
    CHECK(strcmp(fc_state_name(FC_WAIT_FLUSH), "WAIT_FLUSH") == 0);
    CHECK(strcmp(fc_state_name(FC_FLUSHING), "FLUSHING") == 0);
    CHECK(strcmp(fc_state_name(FC_FAULT), "FAULT") == 0);
    CHECK(strcmp(fc_state_name((fc_state_t)99), "?") == 0);
    CHECK(strcmp(fc_reason_name(FC_REASON_USER), "USER") == 0);
    CHECK(strcmp(fc_reason_name(FC_REASON_HYGIENE), "HYGIENE") == 0);
    CHECK(strcmp(fc_reason_name(FC_REASON_NONE), "NONE") == 0);
}

/* robustness: corrupted state variable (e.g. RAM bit flip) -> safe state */
static void tc_u17_corrupted_state_recovers(void)
{
    fc_t fc; uint32_t t = 0; setup(&fc, t);
    fc.state = (fc_state_t)42;
    fc.valve_open = true;                          /* worst case: valve open */
    run(&fc, &t, 10, 0, OK_mV);
    CHECK(fc.state == FC_IDLE && !fc.valve_open);
}

int main(void)
{
    puts("== unit tests: flush_ctrl ==");
    RUN(tc_u01_config_flush_duration_bva);
    RUN(tc_u02_config_hygiene_interval_bva);
    RUN(tc_u03_config_invalid_combinations);
    RUN(tc_u04_presence_below_min_no_flush);
    RUN(tc_u05_presence_at_min_flushes);
    RUN(tc_u06_flush_delay_and_duration);
    RUN(tc_u07_user_returns_during_delay);
    RUN(tc_u08_hygiene_flush_after_72h);
    RUN(tc_u09_hygiene_deferred_while_present);
    RUN(tc_u10_sensor_stuck_sets_fault_and_recovers);
    RUN(tc_u11_hygiene_flush_runs_in_fault);
    RUN(tc_u12_battery_partitions);
    RUN(tc_u13_no_flush_below_cutoff);
    RUN(tc_u14_brownout_during_flush_closes_valve);
    RUN(tc_u15_tick_wraparound);
    RUN(tc_u16_state_and_reason_names);
    RUN(tc_u17_corrupted_state_recovers);
    printf("== %d run, %d failed ==\n", g_run, g_fail);
    return g_fail ? 1 : 0;
}
