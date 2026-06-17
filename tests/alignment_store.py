"""
alignment_store.py
==================
Beamline alignment session recorder with best-comparison, JSONL persistence,
and optional SQLite storage.

Usage inside a Bluesky plan
---------------------------
    from alignment_store import AlignmentStore, record_alignment

    store = AlignmentStore("alignment_log.jsonl")   # one shared instance per session

    def crl_setup():
        res = yield from dscan(crl.y, -0.2, 0.2, 20, tm1, 1, det_ch=[4])
        fmax = res[0].max
        xmax = fmax[0]
        yield from bps.mv(crl.y, xmax)
        yield from record_alignment(
            store,
            scan_id     = res[0].uid,          # or an integer scan id
            instrument  = "crl",
            step        = "y_scan",
            detector    = "tm1",
            motor       = "crl.y",
            max_intensity = fmax[1],
            x_at_max    = xmax,
            note        = "morning alignment",
        )
"""

from __future__ import annotations

import json
import sqlite3
import datetime
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Optional, Any

import bluesky.plan_stubs as bps   # only needed for record_alignment()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AlignmentRecord:
    """One scan result captured during a beamline alignment step."""
    timestamp:     str
    scan_id:       Any           # int or UID string
    instrument:    str
    step:          str
    detector:      str
    motor:         str
    max_intensity: float
    x_at_max:      Optional[float] = None
    fwhm:          Optional[float] = None
    cen:           Optional[float] = None
    com:           Optional[float] = None
    note:          Optional[str]   = None

    # ---- beamline state (used for comparability) ---------------------------
    crl_state:     Optional[str]   = None   # e.g. "in" / "out" / lens-count str
    hrm_state:     Optional[str]   = None   # e.g. "in" / "out"
    ring_current:  Optional[float] = None   # mA, raw value from machine PV

    # ---- comparison fields (filled in by AlignmentStore, not by the user) ----
    prev_max_intensity: Optional[float] = field(default=None, repr=False)
    delta_intensity:    Optional[float] = field(default=None, repr=False)
    delta_pct:          Optional[float] = field(default=None, repr=False)
    is_new_best:        bool            = field(default=False, repr=False)
    comparison_status:  str             = field(default="ok", repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AlignmentRecord":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)

    # ---- computed properties (not stored, not serialised) ------------------

    @property
    def ring_current_mode(self) -> str:
        """Bucket raw ring current into a nominal operating mode string."""
        if self.ring_current is None:
            return "unknown"
        return "400mA" if self.ring_current < 450.0 else "500mA"

    @property
    def comparable_key(self) -> tuple:
        """
        Five-element key used to partition the best-record table.
        Two records are comparable only when all five elements match.
        """
        return (
            self.instrument,
            self.step,
            self.crl_state,
            self.hrm_state,
            self.ring_current_mode,
        )

    def comparison_summary(self) -> str:
        """Human-readable summary for logging / printout."""
        cond = (
            f"CRL={self.crl_state}  HRM={self.hrm_state}  "
            f"ring={self.ring_current_mode}"
        )
        lines = [
            f"[{self.instrument}/{self.step}]  "
            f"max_intensity = {self.max_intensity:.4g}  "
            f"({cond})",
        ]
        if self.comparison_status == "ok":
            arrow = "▲" if self.delta_intensity >= 0 else "▼"
            lines.append(
                f"  {arrow} vs previous best: {self.prev_max_intensity:.4g}  "
                f"Δ = {self.delta_intensity:+.4g}  ({self.delta_pct:+.2f}%)"
            )
            if self.is_new_best:
                lines.append("  ★ NEW BEST")
        elif self.comparison_status == "first_record":
            lines.append(
                "  (first record for this instrument/step/conditions)"
            )
        else:  # "no_comparable_record"
            lines.append(
                "  (no comparable record — conditions differ from all prior records; "
                "see WARNING above)"
            )
        if self.fwhm is not None:
            lines.append(
                f"  fwhm={self.fwhm:.4g}  cen={self.cen:.4g}  com={self.com:.4g}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence + comparison
# ---------------------------------------------------------------------------

class AlignmentStore:
    """
    Stores alignment records to a JSONL file and optionally to SQLite.

    Parameters
    ----------
    jsonl_path : str | Path
        Path to the JSONL file.  Created on first write.
    sqlite_path : str | Path | None
        If given, every record is *also* written to this SQLite database.
    """

    TABLE = "alignment_records"

    def __init__(
        self,
        jsonl_path:   str | Path = "alignment_log.jsonl",
        sqlite_path:  Optional[str | Path] = None,
    ):
        self.jsonl_path  = Path(jsonl_path)
        self.sqlite_path = Path(sqlite_path) if sqlite_path else None
        self._best: dict[tuple, AlignmentRecord] = {}   # key: comparable_key (5-tuple)

        # Rebuild in-memory best table from existing JSONL (if any)
        self._load_history()

        if self.sqlite_path:
            self._init_sqlite()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, record: AlignmentRecord) -> AlignmentRecord:
        """
        Persist a record and fill in best-comparison fields in-place.

        Returns the (mutated) record so callers can print / inspect it.
        """
        self._fill_comparison(record)
        self._write_jsonl(record)
        if self.sqlite_path:
            self._write_sqlite(record)
        self._update_best(record)
        return record

    def get_best(
        self,
        instrument:   str,
        step:         str,
        crl_state:    Optional[str]   = None,
        hrm_state:    Optional[str]   = None,
        ring_current: Optional[float] = None,
    ) -> Optional[AlignmentRecord]:
        """
        Return the best record for the exact comparable key
        (instrument, step, crl_state, hrm_state, ring_current_mode).

        Returns None if no record exists for that exact combination.
        Pass the *raw* ring_current value (mA); bucketing is applied internally.
        """
        mode = "unknown" if ring_current is None else (
            "400mA" if ring_current < 450.0 else "500mA"
        )
        key = (instrument, step, crl_state, hrm_state, mode)
        return self._best.get(key)

    def get_best_any_condition(
        self,
        instrument: str,
        step:       str,
    ) -> list[AlignmentRecord]:
        """
        Return one best record per distinct condition set for (instrument, step).

        FOR DIAGNOSTICS AND REPORTING ONLY.
        The returned records may have different CRL states, HRM states, or
        ring-current modes and must NOT be used for intensity comparison.
        """
        return [
            r for key, r in self._best.items()
            if key[0] == instrument and key[1] == step
        ]

    def history(
        self,
        instrument: Optional[str] = None,
        step:       Optional[str] = None,
    ) -> list[AlignmentRecord]:
        """
        Return all records from JSONL, optionally filtered.

        This re-reads the file each time so it always reflects the latest
        on-disk state (safe for long multi-session workflows).
        """
        records = self._read_all_jsonl()
        if instrument:
            records = [r for r in records if r.instrument == instrument]
        if step:
            records = [r for r in records if r.step == step]
        return records

    def report(
        self,
        instrument: Optional[str] = None,
        step:       Optional[str] = None,
    ) -> str:
        """Multi-line text report of all matching records."""
        records = self.history(instrument, step)
        if not records:
            return "No records found."
        lines = [
            f"{'timestamp':<26} {'instrument':<12} {'step':<20} "
            f"{'max_intensity':>14} {'fwhm':>10} {'cen':>10} {'Δ%':>8}",
            "-" * 100,
        ]
        for r in records:
            lines.append(
                f"{r.timestamp:<26} {r.instrument:<12} {r.step:<20} "
                f"{r.max_intensity:>14.4g} "
                f"{(r.fwhm or 0.0):>10.4g} "
                f"{(r.cen  or 0.0):>10.4g} "
                f"{(r.delta_pct or 0.0):>+8.2f}"
                + (" ★" if r.is_new_best else "")
            )
        return "\n".join(lines)

    def to_sqlite(self, sqlite_path: Optional[str | Path] = None) -> Path:
        """
        Convert / sync the entire JSONL history to SQLite.

        If *sqlite_path* is not given, uses the path set at construction;
        raises ValueError if neither is set.

        Returns the path to the database.
        """
        target = Path(sqlite_path) if sqlite_path else self.sqlite_path
        if target is None:
            raise ValueError(
                "No sqlite_path provided.  Pass one explicitly or set it "
                "when constructing AlignmentStore."
            )
        conn = sqlite3.connect(target)
        self._ensure_table(conn)
        records = self._read_all_jsonl()
        cursor = conn.cursor()
        for r in records:
            self._upsert_record(cursor, r)
        conn.commit()
        conn.close()
        return target

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fill_comparison(self, record: AlignmentRecord) -> None:
        """
        Populate best-comparison fields on *record* in-place.

        Comparisons are made only against records with an identical comparable_key
        (instrument, step, crl_state, hrm_state, ring_current_mode).

        If no exact-key match exists, comparison fields are left at their
        defaults and comparison_status is set to indicate why:
          - "first_record"          : no prior record for (instrument, step) at all
          - "no_comparable_record"  : prior records exist but conditions differ
        In the latter case a WARNING is printed for each differing condition set.
        """
        key  = record.comparable_key
        best = self._best.get(key)

        if best is not None:
            # --- exact-key match: do the comparison -------------------------
            record.prev_max_intensity = best.max_intensity
            record.delta_intensity    = record.max_intensity - best.max_intensity
            record.delta_pct = (
                100.0 * record.delta_intensity / best.max_intensity
                if best.max_intensity != 0 else 0.0
            )
            record.is_new_best       = record.max_intensity > best.max_intensity
            record.comparison_status = "ok"
            return

        # --- no exact-key match: scan for same (instrument, step) with different conditions
        record.is_new_best = True   # first (or only) record for this condition set

        others = [
            r for k, r in self._best.items()
            if k[0] == record.instrument and k[1] == record.step
        ]

        if not others:
            record.comparison_status = "first_record"
            return

        # Prior records exist but conditions differ — emit warnings
        record.comparison_status = "no_comparable_record"
        for prior in others:
            diffs = []
            if prior.crl_state != record.crl_state:
                diffs.append(
                    f'CRL state "{prior.crl_state}" → "{record.crl_state}"'
                )
            if prior.hrm_state != record.hrm_state:
                diffs.append(
                    f'HRM state "{prior.hrm_state}" → "{record.hrm_state}"'
                )
            if prior.ring_current_mode != record.ring_current_mode:
                diffs.append(
                    f'ring-current mode "{prior.ring_current_mode}" → '
                    f'"{record.ring_current_mode}"'
                )
            diff_str = ", ".join(diffs) if diffs else "unknown difference"
            print(
                f"WARNING [{record.instrument}/{record.step}]: "
                f"no comparable record for current conditions\n"
                f"  ({diff_str})\n"
                f"  Last seen under those conditions: {prior.timestamp}"
            )

    def _update_best(self, record: AlignmentRecord) -> None:
        key = record.comparable_key
        if record.is_new_best or key not in self._best:
            self._best[key] = record

    def _write_jsonl(self, record: AlignmentRecord) -> None:
        with self.jsonl_path.open("a") as fh:
            fh.write(json.dumps(record.to_dict()) + "\n")

    def _read_all_jsonl(self) -> list[AlignmentRecord]:
        if not self.jsonl_path.exists():
            return []
        records = []
        with self.jsonl_path.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(AlignmentRecord.from_dict(json.loads(line)))
                    except Exception:
                        pass   # skip malformed lines
        return records

    def _load_history(self) -> None:
        """Rebuild self._best from existing JSONL so comparisons survive restarts."""
        for r in self._read_all_jsonl():
            key  = r.comparable_key
            prev = self._best.get(key)
            if prev is None or r.max_intensity > prev.max_intensity:
                self._best[key] = r

    # ---- SQLite helpers ------------------------------------------------

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        self._ensure_table(conn)
        conn.close()

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection) -> None:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {AlignmentStore.TABLE} (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp          TEXT,
                scan_id            TEXT,
                instrument         TEXT,
                step               TEXT,
                detector           TEXT,
                motor              TEXT,
                max_intensity      REAL,
                x_at_max           REAL,
                fwhm               REAL,
                cen                REAL,
                com                REAL,
                note               TEXT,
                crl_state          TEXT,
                hrm_state          TEXT,
                ring_current       REAL,
                ring_current_mode  TEXT,
                prev_max_intensity REAL,
                delta_intensity    REAL,
                delta_pct          REAL,
                is_new_best        INTEGER,
                comparison_status  TEXT,
                UNIQUE(timestamp, scan_id, instrument, step, crl_state, hrm_state)
            )
        """)
        conn.commit()

    @staticmethod
    def _upsert_record(cursor: sqlite3.Cursor, r: AlignmentRecord) -> None:
        d = r.to_dict()
        d["scan_id"]          = str(d["scan_id"])
        d["is_new_best"]      = int(d["is_new_best"])
        # ring_current_mode is a computed property, not in asdict() — add it explicitly
        d["ring_current_mode"] = r.ring_current_mode
        cols         = ", ".join(d.keys())
        placeholders = ", ".join("?" for _ in d)
        cursor.execute(
            f"INSERT OR IGNORE INTO {AlignmentStore.TABLE} ({cols}) VALUES ({placeholders})",
            list(d.values()),
        )

    def _write_sqlite(self, record: AlignmentRecord) -> None:
        conn   = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        self._upsert_record(cursor, record)
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Bluesky plan helper
# ---------------------------------------------------------------------------

def record_alignment(
    store:         AlignmentStore,
    scan_id:       Any,
    instrument:    str,
    step:          str,
    detector:      str,
    motor:         str,
    max_intensity: float,
    x_at_max:      Optional[float] = None,
    fwhm:          Optional[float] = None,
    cen:           Optional[float] = None,
    com:           Optional[float] = None,
    note:          Optional[str]   = None,
    crl_state:     Optional[str]   = None,
    hrm_state:     Optional[str]   = None,
    ring_current:  Optional[float] = None,
):
    """
    Bluesky plan stub — yields nothing but wraps store.add() so it can be
    called with ``yield from`` inside a plan for consistency.

    Parameters
    ----------
    crl_state : str, optional
        CRL configuration string, e.g. ``"in"``, ``"out"``, or a lens-count
        string such as ``"4lenses"``.  Used for comparability keying.
    hrm_state : str, optional
        High-resolution monochromator state, e.g. ``"in"`` / ``"out"``.
        Used for comparability keying.
    ring_current : float, optional
        Raw storage-ring current in mA (read from machine PV).  Bucketed
        into ``"400mA"`` / ``"500mA"`` / ``"unknown"`` for comparability keying.

    Example
    -------
        yield from record_alignment(
            store,
            scan_id       = res[0].uid,
            instrument    = "crl",
            step          = "y_scan",
            detector      = "tm1",
            motor         = "crl.y",
            max_intensity = fmax[1],
            x_at_max      = xmax,
            crl_state     = "in",
            hrm_state     = "out",
            ring_current  = 499.3,
            note          = "morning alignment",
        )
    """
    record = AlignmentRecord(
        timestamp     = datetime.datetime.now().isoformat(timespec="seconds"),
        scan_id       = scan_id,
        instrument    = instrument,
        step          = step,
        detector      = detector,
        motor         = motor,
        max_intensity = max_intensity,
        x_at_max      = x_at_max,
        fwhm          = fwhm,
        cen           = cen,
        com           = com,
        note          = note,
        crl_state     = crl_state,
        hrm_state     = hrm_state,
        ring_current  = ring_current,
    )
    record = store.add(record)
    print(record.comparison_summary())
    yield from bps.null()   # makes this a proper generator / plan
