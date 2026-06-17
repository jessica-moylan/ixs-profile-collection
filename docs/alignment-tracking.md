# Purpose

Track beamline alignment quality over time.

# Data Stored

- timestamp
- scan_id
- instrument
- max intensity
- peak center
- FWHM
- ring current
- CRL state
- HRM state

# Comparison Rules

Records are comparable only if:

- same instrument
- same CRL state
- same HRM state
- same nominal ring-current mode

Nominal modes:
- 400 mA
- 500 mA

# Validation

Peak validation may include:

- FWHM threshold
- center/com consistency
- crossings == 2

Statistics may be absent for some plans.

# Warnings

Warn if:
- no comparable historical data
- different CRL state
- different HRM state
- different ring-current mode
