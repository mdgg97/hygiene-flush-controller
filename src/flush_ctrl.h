/*
 * flush_ctrl.h - Touchless WC flush controller with hygiene (stagnation) flush.
 *
 * Hardware-independent core: no registers, no HAL calls. The caller passes in
 * time, sensor and battery values; the controller returns the valve command
 * and events. This makes the logic testable on a PC (SIL) and on target (HIL).
 */
#ifndef FLUSH_CTRL_H
#define FLUSH_CTRL_H

#include <stdbool.h>
#include <stdint.h>

#define FC_MAX_FLUSH_MS      10000u   /* REQ-03: valve may never be open longer */
#define FC_MIN_HYGIENE_MS    (24u * 3600u * 1000u)   /* REQ-04 range: 24 h ... */
#define FC_MAX_HYGIENE_MS    (168u * 3600u * 1000u)  /* ... 168 h (7 days)     */

typedef struct {
    uint32_t min_presence_ms;     /* REQ-01/02: user must be present this long  */
    uint32_t flush_delay_ms;      /* REQ-01: wait after user leaves             */
    uint32_t flush_duration_ms;   /* REQ-03: valve open time                    */
    uint32_t hygiene_interval_ms; /* REQ-04: max time without a flush           */
    uint32_t sensor_stuck_ms;     /* REQ-06: continuous presence => sensor fault */
    uint16_t batt_warn_mV;        /* REQ-07: warning threshold                  */
    uint16_t batt_cutoff_mV;      /* REQ-07: valve disabled below this          */
} fc_config_t;

typedef enum {
    FC_IDLE = 0,
    FC_OCCUPIED,
    FC_WAIT_FLUSH,
    FC_FLUSHING,
    FC_FAULT
} fc_state_t;

typedef enum {
    FC_REASON_NONE = 0,
    FC_REASON_USER,
    FC_REASON_HYGIENE
} fc_reason_t;

/* Error flags (bitmask), REQ-06/07 */
#define FC_ERR_SENSOR_STUCK  0x01u
#define FC_ERR_BATT_LOW      0x02u
#define FC_ERR_BATT_CUTOFF   0x04u

/* Events returned by fc_step (bitmask), used for logging / telemetry REQ-08 */
#define FC_EVT_FLUSH_START   0x01u
#define FC_EVT_FLUSH_END     0x02u
#define FC_EVT_FAULT_SET     0x04u
#define FC_EVT_FAULT_CLEAR   0x08u
#define FC_EVT_BATT_WARN     0x10u
#define FC_EVT_FLUSH_ABORT   0x20u

typedef enum { FC_OK = 0, FC_ERR_CONFIG = -1 } fc_result_t;

typedef struct {
    fc_config_t cfg;
    fc_state_t  state;
    fc_reason_t reason;          /* reason of the current / last flush */
    bool        valve_open;
    uint8_t     errors;
    uint32_t    t_state_ms;      /* time the current state was entered */
    uint32_t    t_presence_ms;   /* time presence started              */
    uint32_t    t_last_flush_ms; /* time of the last completed flush   */
    bool        last_presence;
    uint32_t    flush_count;     /* REQ-08 */
    uint32_t    hygiene_count;   /* REQ-08 */
} fc_t;

void        fc_default_config(fc_config_t *cfg);
fc_result_t fc_init(fc_t *fc, const fc_config_t *cfg, uint32_t now_ms);
/* Call periodically (e.g. every 10 ms). Returns FC_EVT_* bitmask. */
uint8_t     fc_step(fc_t *fc, uint32_t now_ms, bool presence, uint16_t batt_mV);
const char *fc_state_name(fc_state_t s);
const char *fc_reason_name(fc_reason_t r);

#endif /* FLUSH_CTRL_H */
