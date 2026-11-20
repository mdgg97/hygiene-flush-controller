/*
 * flush_ctrl.c - see flush_ctrl.h. Requirement IDs refer to docs/REQUIREMENTS.md.
 */
#include "flush_ctrl.h"
#include <stddef.h>

#define BATT_HYST_mV 100u   /* hysteresis so the flag does not toggle on noise */

/*
 * REQ-09: time arithmetic must survive the uint32 millisecond wrap (~49.7 days).
 * Correct form: unsigned subtraction. Building with -DFC_INJECT_BUG_OVERFLOW
 * switches to a typical wrong form, so the test suite can show it catches it.
 */
static bool elapsed(uint32_t now, uint32_t since, uint32_t dur)
{
#ifdef FC_INJECT_BUG_OVERFLOW
    return now >= since + dur;              /* BUG: since + dur can wrap */
#else
    return (uint32_t)(now - since) >= dur;
#endif
}

void fc_default_config(fc_config_t *cfg)
{
    cfg->min_presence_ms     = 3000u;                    /* 3 s     */
    cfg->flush_delay_ms      = 1000u;                    /* 1 s     */
    cfg->flush_duration_ms   = 4000u;                    /* 4 s     */
    cfg->hygiene_interval_ms = 72u * 3600u * 1000u;      /* 72 h    */
    cfg->sensor_stuck_ms     = 10u * 60u * 1000u;        /* 10 min  */
    cfg->batt_warn_mV        = 4400u;                    /* 4xAA    */
    cfg->batt_cutoff_mV      = 4000u;
}

static bool config_valid(const fc_config_t *c)
{
    if (c->min_presence_ms == 0u) return false;
    if (c->flush_duration_ms == 0u || c->flush_duration_ms > FC_MAX_FLUSH_MS) return false;
    if (c->hygiene_interval_ms < FC_MIN_HYGIENE_MS ||
        c->hygiene_interval_ms > FC_MAX_HYGIENE_MS) return false;
    if (c->sensor_stuck_ms <= c->min_presence_ms) return false;
    if (c->batt_cutoff_mV >= c->batt_warn_mV) return false;
    return true;
}

fc_result_t fc_init(fc_t *fc, const fc_config_t *cfg, uint32_t now_ms)
{
    if (fc == NULL || cfg == NULL || !config_valid(cfg)) {
        return FC_ERR_CONFIG;
    }
    fc->cfg             = *cfg;
    fc->state           = FC_IDLE;
    fc->reason          = FC_REASON_NONE;
    fc->valve_open      = false;
    fc->errors          = 0u;
    fc->t_state_ms      = now_ms;
    fc->t_presence_ms   = now_ms;
    fc->t_last_flush_ms = now_ms;   /* hygiene timer starts at power-up */
    fc->last_presence   = false;
    fc->flush_count     = 0u;
    fc->hygiene_count   = 0u;
    return FC_OK;
}

static void enter(fc_t *fc, fc_state_t s, uint32_t now)
{
    fc->state = s;
    fc->t_state_ms = now;
}

/* Returns true if the flush really started (battery may forbid it). */
static bool start_flush(fc_t *fc, uint32_t now, fc_reason_t reason, uint8_t *ev)
{
    if (fc->errors & FC_ERR_BATT_CUTOFF) {
        return false;                                   /* REQ-07 */
    }
    fc->valve_open = true;
    fc->reason = reason;
    *ev |= FC_EVT_FLUSH_START;
    enter(fc, FC_FLUSHING, now);
    return true;
}

static void update_battery(fc_t *fc, uint32_t now, uint16_t mV, uint8_t *ev)
{
    if (mV < fc->cfg.batt_warn_mV) {
        if (!(fc->errors & FC_ERR_BATT_LOW)) {
            fc->errors |= FC_ERR_BATT_LOW;
            *ev |= FC_EVT_BATT_WARN;
        }
    } else if (mV >= fc->cfg.batt_warn_mV + BATT_HYST_mV) {
        fc->errors &= (uint8_t)~FC_ERR_BATT_LOW;
    }

    if (mV < fc->cfg.batt_cutoff_mV) {
        fc->errors |= FC_ERR_BATT_CUTOFF;
        if (fc->valve_open) {                           /* REQ-07: close safely */
            fc->valve_open = false;
            *ev |= FC_EVT_FLUSH_ABORT;
            enter(fc, (fc->errors & FC_ERR_SENSOR_STUCK) ? FC_FAULT : FC_IDLE, now);
        }
    } else if (mV >= fc->cfg.batt_cutoff_mV + BATT_HYST_mV) {
        fc->errors &= (uint8_t)~FC_ERR_BATT_CUTOFF;
    }
}

uint8_t fc_step(fc_t *fc, uint32_t now, bool presence, uint16_t batt_mV)
{
    uint8_t ev = 0u;
    const bool hygiene_due = elapsed(now, fc->t_last_flush_ms, fc->cfg.hygiene_interval_ms);

    update_battery(fc, now, batt_mV, &ev);

    if (presence && !fc->last_presence) {
        fc->t_presence_ms = now;
    }
    fc->last_presence = presence;

    switch (fc->state) {
    case FC_IDLE:
        if (presence) {
            enter(fc, FC_OCCUPIED, now);
        } else if (hygiene_due) {                       /* REQ-04, REQ-05 */
            (void)start_flush(fc, now, FC_REASON_HYGIENE, &ev);
        }
        break;

    case FC_OCCUPIED:
        if (presence) {
            if (elapsed(now, fc->t_presence_ms, fc->cfg.sensor_stuck_ms)) {   /* REQ-06 */
                fc->errors |= FC_ERR_SENSOR_STUCK;
                ev |= FC_EVT_FAULT_SET;
                enter(fc, FC_FAULT, now);
            }
        } else if (elapsed(now, fc->t_state_ms, fc->cfg.min_presence_ms)) {    /* REQ-01 */
            enter(fc, FC_WAIT_FLUSH, now);
        } else {
            enter(fc, FC_IDLE, now);                    /* REQ-02: passer-by */
        }
        break;

    case FC_WAIT_FLUSH:
        if (presence) {
            enter(fc, FC_OCCUPIED, now);                /* user came back */
        } else if (elapsed(now, fc->t_state_ms, fc->cfg.flush_delay_ms)) {
            if (!start_flush(fc, now, FC_REASON_USER, &ev)) {
                enter(fc, FC_IDLE, now);                /* REQ-07: no flush */
            }
        }
        break;

    case FC_FLUSHING:                                   /* presence ignored */
        if (elapsed(now, fc->t_state_ms, fc->cfg.flush_duration_ms)) {        /* REQ-03 */
            fc->valve_open = false;
            fc->t_last_flush_ms = now;
            fc->flush_count++;
            if (fc->reason == FC_REASON_HYGIENE) {
                fc->hygiene_count++;
            }
            ev |= FC_EVT_FLUSH_END;
            enter(fc, (fc->errors & FC_ERR_SENSOR_STUCK) ? FC_FAULT : FC_IDLE, now);
        }
        break;

    case FC_FAULT:
        if (!presence) {                                /* sensor recovered */
            fc->errors &= (uint8_t)~FC_ERR_SENSOR_STUCK;
            ev |= FC_EVT_FAULT_CLEAR;
            enter(fc, FC_IDLE, now);
        } else if (hygiene_due) {                       /* REQ-06: hygiene wins */
            (void)start_flush(fc, now, FC_REASON_HYGIENE, &ev);
        }
        break;

    default:                                            /* corrupted state */
        fc->valve_open = false;                         /* fail safe: close */
        enter(fc, FC_IDLE, now);
        break;
    }
    return ev;
}

const char *fc_state_name(fc_state_t s)
{
    switch (s) {
    case FC_IDLE:       return "IDLE";
    case FC_OCCUPIED:   return "OCCUPIED";
    case FC_WAIT_FLUSH: return "WAIT_FLUSH";
    case FC_FLUSHING:   return "FLUSHING";
    case FC_FAULT:      return "FAULT";
    default:            return "?";
    }
}

const char *fc_reason_name(fc_reason_t r)
{
    switch (r) {
    case FC_REASON_USER:    return "USER";
    case FC_REASON_HYGIENE: return "HYGIENE";
    default:                return "NONE";
    }
}
