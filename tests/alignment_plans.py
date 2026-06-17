"""
alignment_plans.py
==================
Example beamline alignment plans that use AlignmentStore.

These show the intended usage pattern:
  - one shared AlignmentStore for the whole session
  - each plan extracts statistics from the scan result, then calls record_alignment()
  - at the end of the session you can convert to SQLite and/or print a report
"""

import bluesky.plan_stubs as bps
from ophyd import Device   # replace with your actual imports

from alignment_store import AlignmentStore, record_alignment

# ---------------------------------------------------------------------------
# One shared store for the full alignment session.
# Set sqlite_path to None if you don't want SQLite side-by-side.
# ---------------------------------------------------------------------------
store = AlignmentStore(
    jsonl_path  = "alignment_log.jsonl",
    sqlite_path = "alignment_log.db",    # optional — comment out to skip
)


# ---------------------------------------------------------------------------
# Helper: extract stats from a Bluesky scan result
# ---------------------------------------------------------------------------
def _stats_from_result(res, detector: str):
    """
    Pull peak statistics out of a lmfit / peakstats result dict.
    Adjust key names to match whatever your plan returns.
    """
    stats  = res[0]                         # first (only) run
    max_intensity = stats.max[detector]
    x_at_max      = stats.max["motor"]      # adjust to your motor key
    fwhm          = getattr(stats, "fwhm",  None)
    cen           = getattr(stats, "cen",   None)
    com           = getattr(stats, "com",   None)
    return max_intensity, x_at_max, fwhm, cen, com


# ---------------------------------------------------------------------------
# Individual instrument plans
# ---------------------------------------------------------------------------

def crl_setup(note: str = "",
              crl_state: str | None = None,
              hrm_state: str | None = None,
              ring_current: float | None = None):
    """Scan CRL vertical position; move to peak; record."""
    res = yield from dscan(crl.y, -0.2, 0.2, 20, tm1, 1, det_ch=[4])

    fmax = res[0].max
    xmax = fmax[0]
    yield from bps.mv(crl.y, xmax)

    yield from record_alignment(
        store,
        scan_id       = res[0].uid,
        instrument    = "crl",
        step          = "y_scan",
        detector      = "tm1",
        motor         = "crl.y",
        max_intensity = fmax[1],
        x_at_max      = xmax,
        crl_state     = crl_state,
        hrm_state     = hrm_state,
        ring_current  = ring_current,
        note          = note,
    )


def dcm_p1_scan(note: str = "",
                crl_state: str | None = None,
                hrm_state: str | None = None,
                ring_current: float | None = None):
    """Scan DCM pitch-1; move to peak; record including peak shape."""
    res = yield from dscan(dcm.p1, -50, 50, 100, tm1, 0.5, det_ch=[1])

    fmax  = res[0].max
    xmax  = fmax[0]
    stats = res[0]                    # adjust to your plan's return type

    yield from bps.mv(dcm.p1, xmax)

    yield from record_alignment(
        store,
        scan_id       = res[0].uid,
        instrument    = "dcm",
        step          = "p1_scan",
        detector      = "tm1",
        motor         = "dcm.p1",
        max_intensity = fmax[1],
        x_at_max      = xmax,
        fwhm          = getattr(stats, "fwhm", None),
        cen           = getattr(stats, "cen",  None),
        com           = getattr(stats, "com",  None),
        crl_state     = crl_state,
        hrm_state     = hrm_state,
        ring_current  = ring_current,
        note          = note,
    )


def mirror_pitch_scan(note: str = "",
                      crl_state: str | None = None,
                      hrm_state: str | None = None,
                      ring_current: float | None = None):
    """Scan focusing mirror pitch; record."""
    res = yield from dscan(mirror.pitch, -0.5, 0.5, 50, tm1, 1)

    fmax = res[0].max
    xmax = fmax[0]
    yield from bps.mv(mirror.pitch, xmax)

    yield from record_alignment(
        store,
        scan_id       = res[0].uid,
        instrument    = "mirror",
        step          = "pitch_scan",
        detector      = "tm1",
        motor         = "mirror.pitch",
        max_intensity = fmax[1],
        x_at_max      = xmax,
        crl_state     = crl_state,
        hrm_state     = hrm_state,
        ring_current  = ring_current,
        note          = note,
    )


# ---------------------------------------------------------------------------
# Full alignment sequence
# ---------------------------------------------------------------------------

def full_alignment(note: str = "morning alignment",
                   crl_state: str | None = None,
                   hrm_state: str | None = None,
                   ring_current: float | None = None):
    """
    Run the complete alignment sequence in order.
    Each step prints a live comparison against the previous best.
    """
    yield from mirror_pitch_scan(note=note, crl_state=crl_state,
                                 hrm_state=hrm_state, ring_current=ring_current)
    yield from dcm_p1_scan(note=note, crl_state=crl_state,
                           hrm_state=hrm_state, ring_current=ring_current)
    yield from crl_setup(note=note, crl_state=crl_state,
                         hrm_state=hrm_state, ring_current=ring_current)

    # ---- End-of-session: print text report --------------------------------
    print("\n" + "=" * 100)
    print("ALIGNMENT SESSION REPORT")
    print("=" * 100)
    print(store.report())

    # ---- Optional: flush everything to SQLite ----------------------------
    db_path = store.to_sqlite()
    print(f"\nHistory written to {db_path}")


# ---------------------------------------------------------------------------
# Ad-hoc utilities (run outside a plan)
# ---------------------------------------------------------------------------

def print_best(instrument: str, step: str,
               crl_state: str | None = None,
               hrm_state: str | None = None,
               ring_current: float | None = None):
    """
    Print the best record for the exact (instrument, step, crl_state,
    hrm_state, ring_current_mode) combination.

    If no record exists for those exact conditions, reports that and
    lists the best records that do exist for this (instrument, step)
    under different conditions (diagnostics only — not for comparison).
    """
    rec = store.get_best(instrument, step,
                         crl_state=crl_state,
                         hrm_state=hrm_state,
                         ring_current=ring_current)
    if rec:
        print(rec.comparison_summary())
    else:
        print(
            f"No records for {instrument}/{step} "
            f"under the specified conditions "
            f"(CRL={crl_state}  HRM={hrm_state}  "
            f"ring_current={ring_current})."
        )
        others = store.get_best_any_condition(instrument, step)
        if others:
            print(
                "  Records exist under different conditions "
                "(FOR DIAGNOSTICS ONLY — conditions may differ):"
            )
            for r in others:
                print(
                    f"    CRL={r.crl_state}  HRM={r.hrm_state}  "
                    f"ring={r.ring_current_mode}  "
                    f"best={r.max_intensity:.4g}  @ {r.timestamp}"
                )


def print_history(instrument: str | None = None, step: str | None = None):
    """Tabular printout of all (or filtered) historical records."""
    print(store.report(instrument=instrument, step=step))
