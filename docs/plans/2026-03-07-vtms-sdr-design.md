# vtms-sdr Implementation Design

**Goal:** Python CLI tool that uses an RTL-SDR dongle to record audio from a given frequency (FM/AM/SSB) and scan for active or clear channels.

**Architecture:** Modular design with separate components for SDR hardware access, signal demodulation, audio recording, and frequency scanning. All coordinated through a Click-based CLI.

**Tech Stack:** Python 3.10+, pyrtlsdr, numpy, scipy, click, soundfile, pydub

---

## CLI Interface

```bash
# Record audio
vtms-sdr record -f 146.52M -m fm -o recording.wav
vtms-sdr record -f 462.5625M -m fm --format mp3 -d 60
vtms-sdr record -f 7.2M -m ssb --squelch -100

# Scan for active frequencies
vtms-sdr scan active --start 144M --end 148M --step 25k
vtms-sdr scan active --start 440M --end 450M --step 12.5k --threshold -30 -o scan.csv

# Find clear/unused frequencies
vtms-sdr scan clear --start 144M --end 148M --step 25k -d 300
```

## Project Structure

```
src/vtms_sdr/
├── cli.py        # Click CLI commands and entry point
├── sdr.py        # RTL-SDR device wrapper (context manager, IQ streaming)
├── demod.py      # FM/AM/SSB demodulators (factory pattern)
├── recorder.py   # WAV/MP3 audio writer with squelch gating
├── scanner.py    # Active + clear frequency scanning
└── utils.py      # Frequency parsing, dB conversion, helpers
```

## Data Flow

### Recording
```
RTL-SDR → IQ samples (2.4 Msps) → Demodulator → Audio (48 kHz) → Squelch gate → WAV/MP3
```

### Scanning
```
RTL-SDR → tune each freq → FFT power measurement → compare to threshold → report
```

## Key Design Decisions

- Single frequency at a time (multi-frequency deferred)
- Context-manager based SDR device access
- Factory pattern for demodulators (`Demodulator.create("fm")`)
- Scanner uses FFT power measurement (no demodulation needed)
- Clear scan: monitors range over time, reports frequencies that stayed quiet
- Graceful SIGINT handling preserves partial recordings
- MP3 via temp WAV conversion (avoids memory issues with long recordings)

## Dependencies

| Package | Purpose |
|---------|---------|
| pyrtlsdr | RTL-SDR dongle access |
| numpy | Array ops, FFT |
| scipy | DSP filters, decimation |
| click | CLI framework |
| soundfile | WAV file writing |
| pydub | MP3 encoding (wraps ffmpeg) |

System: `librtlsdr`, `ffmpeg` (MP3 only)
