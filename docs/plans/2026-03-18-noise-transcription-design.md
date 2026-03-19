# Improved Noise Handling for Transcription

**Date:** 2026-03-18
**Status:** Implemented

## Problem

Transcription quality degrades with wind noise and RF interference because:
- `noisereduce` was configured with `stationary=True`, which only handles constant
  background noise (hiss/hum) and is ineffective against bursty wind noise
- Whisper's default parameters are permissive enough to hallucinate on noisy input
- The bandpass filter's 300 Hz low cutoff allowed wind energy to bleed through

## Approach

Improve the default preprocessing and Whisper parameters without adding new
dependencies or CLI flags. Quality over speed.

## Changes

### 1. Preprocessing (`_preprocess_for_whisper`)

- **Bandpass cutoff:** 300 Hz → 400 Hz. Wind noise has significant energy in
  300–400 Hz while compressed radio speech fundamentals sit above ~400 Hz.
- **Noise reduction mode:** `stationary=True` → `stationary=False`. Adaptive
  spectral gating handles non-stationary noise (wind gusts, interference bursts).
- **Noise reduction strength:** `prop_decrease` 0.7 → 0.85. More aggressive
  reduction is safe for already-compressed radio audio.
- **Spectral gating tuning:** Added `time_constant_s=0.5` (tracks wind gusts),
  `freq_mask_smooth_hz=500` (prevents musical artifacts),
  `n_std_thresh_stationary=1.5` (explicit threshold).

### 2. Whisper parameters (`_run_whisper`)

- **`speech_pad_ms`:** 100 → 200. More padding around detected speech prevents
  word clipping in noisy audio where VAD boundaries are unreliable.
- **`condition_on_previous_text=False`:** Prevents hallucination cascading—if
  one segment hallucinates in noise, it won't contaminate subsequent segments.
- **`no_speech_threshold=0.45`:** Below default 0.6. Prevents Whisper from
  too-aggressively classifying noisy speech as silence.
- **`log_prob_threshold=-0.8`:** Rejects low-confidence segments earlier than
  the default -1.0.
- **`compression_ratio_threshold=2.0`:** Catches repetitive hallucinated output
  (e.g., "the the the") tighter than the default 2.4.

### 3. Segment confidence filter

Segments with `avg_logprob <= -1.0` are now filtered out in `_run_whisper`.
This drops output where Whisper was essentially guessing, which happens
frequently with wind noise. Uses `getattr` for backward compatibility with
segment objects that lack the attribute.

## Files Changed

- `src/vtms_sdr/transcriber.py` — preprocessing pipeline + Whisper params
- `tests/test_transcriber.py` — updated parameter assertions + new confidence filter tests
