"""CLI entry point for vtms-sdr using Click."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import click

from . import __version__
from .utils import (
    format_frequency,
    iq_power_db,
    parse_frequency,
    validate_frequency,
    VALID_MODULATIONS,
)

__all__ = [
    "main",
]


def _parse_freq_param(ctx, param, value: str) -> int:
    """Click callback to parse a frequency parameter with range validation."""
    try:
        freq = parse_frequency(value)
        validate_frequency(freq)
        return freq
    except ValueError as e:
        raise click.BadParameter(str(e))


def _parse_freq_value(ctx, param, value: str) -> int:
    """Click callback to parse a frequency value without range validation.

    Used for step sizes, bandwidths, etc. that aren't actual tuning frequencies.
    """
    try:
        return parse_frequency(value)
    except ValueError as e:
        raise click.BadParameter(str(e))


@click.group()
@click.version_option(__version__, prog_name="vtms-sdr")
@click.option(
    "-v", "--verbose", count=True, help="Increase verbosity (-v info, -vv debug)."
)
@click.pass_context
def main(ctx, verbose):
    """vtms-sdr: RTL-SDR audio recorder and frequency scanner.

    Record audio from VHF/UHF frequencies using an RTL-SDR dongle,
    or scan for active/clear channels.
    """
    ctx.ensure_object(dict)
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(name)s: %(message)s", stream=sys.stderr)


@main.command()
@click.option(
    "-f",
    "--freq",
    default=None,
    help="Frequency to record (e.g. 146.52M, 7200k, 462.5625M).",
)
@click.option(
    "-m",
    "--mod",
    type=click.Choice(VALID_MODULATIONS, case_sensitive=False),
    default=None,
    help="Modulation type (default: fm).",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Output filename. Auto-generated if not specified.",
)
@click.option(
    "--format",
    "audio_format",
    type=click.Choice(["wav"]),
    default="wav",
    show_default=True,
    help="Audio output format.",
)
@click.option(
    "-d",
    "--duration",
    type=float,
    default=None,
    help="Recording duration in seconds (default: until Ctrl+C).",
)
@click.option(
    "-g",
    "--gain",
    default=None,
    help="SDR gain in dB, or 'auto' (default: auto).",
)
@click.option(
    "--squelch",
    type=float,
    default=None,
    help="Squelch threshold in dB. Use -100 to disable (default: -40).",
)
@click.option(
    "--device",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR device index.",
)
@click.option(
    "--transcribe",
    is_flag=True,
    default=False,
    help="Enable live transcription of radio comms (requires faster-whisper).",
)
@click.option(
    "--model",
    "whisper_model",
    type=click.Choice(["auto", "tiny", "base", "small", "medium", "large"]),
    default="auto",
    show_default=True,
    help="Whisper model size. 'auto' picks based on hardware.",
)
@click.option(
    "--transcript",
    "transcript_path",
    type=click.Path(),
    default=None,
    help="Path for transcript log file (default: auto-generated).",
)
@click.option(
    "--label",
    type=str,
    default=None,
    help="Channel label for transcript output (e.g. 'PIT-CREW').",
)
@click.option(
    "--preset",
    "preset_name",
    type=str,
    default=None,
    help="Use a named preset profile from a YAML file.",
)
@click.option(
    "--preset-file",
    type=click.Path(exists=True),
    default=None,
    help="Path to preset YAML file (default: presets.yaml in CWD).",
)
@click.option(
    "--ppm",
    type=int,
    default=None,
    help="RTL-SDR frequency correction in PPM. Measure with 'rtl_test -p'.",
)
@click.option(
    "--monitor",
    is_flag=True,
    default=False,
    help="Enable live audio monitoring through speakers/headphones.",
)
@click.option(
    "--volume",
    type=float,
    default=0.5,
    show_default=True,
    help="Initial monitor volume (0.0 to 1.0). Requires --monitor.",
)
@click.option(
    "--language",
    type=str,
    default="en",
    show_default=True,
    help="Language code for transcription (e.g. 'en', 'es', 'de'). Requires --transcribe.",
)
@click.option(
    "--prompt",
    type=str,
    default=None,
    help="Custom initial prompt for Whisper (overrides default motorsport prompt). Requires --transcribe.",
)
@click.option(
    "--dcs",
    "dcs_code",
    type=int,
    default=None,
    help="DCS code for squelch gating (e.g. 23, 71, 155). Only opens squelch when this code matches.",
)
@click.option(
    "--mqtt-broker",
    type=str,
    default=None,
    help="MQTT broker hostname/IP. Enables publishing SDR state to MQTT.",
)
@click.option(
    "--mqtt-prefix",
    type=str,
    default="lemons/",
    show_default=True,
    help="MQTT topic prefix for SDR state/control messages.",
)
@click.option(
    "--audio-ws-port",
    type=int,
    default=None,
    help="WebSocket port for live audio streaming (e.g. 9003).",
)
def record(
    freq,
    mod,
    output,
    audio_format,
    duration,
    gain,
    squelch,
    device,
    transcribe,
    whisper_model,
    transcript_path,
    label,
    preset_name,
    preset_file,
    ppm,
    monitor,
    volume,
    language,
    prompt,
    dcs_code,
    mqtt_broker,
    mqtt_prefix,
    audio_ws_port,
):
    """Record audio from a frequency.

    Tunes the RTL-SDR to the specified frequency, demodulates the signal,
    and saves the audio to a WAV file.

    Examples:

        vtms-sdr record -f 146.52M -m fm

        vtms-sdr record -f 462.5625M -m fm -o gmrs.wav -d 60

        vtms-sdr record -f 7.2M -m ssb

        vtms-sdr record --preset nascar --preset-file presets.yaml
    """
    from .session import RecordConfig, RecordingSession

    # --- Resolve preset if provided ---
    if preset_name:
        from .presets import load_presets, get_preset, find_preset_file

        if preset_file:
            preset_path = Path(preset_file)
        else:
            preset_path = find_preset_file()
            if preset_path is None:
                click.echo(
                    "Error: No preset file found. "
                    "Use --preset-file or create presets.yaml.",
                    err=True,
                )
                sys.exit(1)

        try:
            presets = load_presets(preset_path)
            preset = get_preset(presets, preset_name)
        except (FileNotFoundError, ValueError, KeyError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Apply preset values where CLI didn't provide explicit overrides
        if freq is None:
            freq = preset.get("freq")
        if mod is None:
            mod = preset.get("mod")
        if gain is None and "gain" in preset:
            gain = str(preset["gain"])
        if squelch is None and "squelch" in preset:
            squelch = float(preset["squelch"])
        if label is None:
            label = preset.get("label")
        if ppm is None and "ppm" in preset:
            ppm = int(preset["ppm"])
        if dcs_code is None and "dcs_code" in preset:
            dcs_code = int(preset["dcs_code"])

    # Apply defaults for values still unset
    if mod is None:
        mod = "fm"
    if gain is None:
        gain = "auto"
    if squelch is None:
        squelch = -30.0
    if ppm is None:
        ppm = 0

    # Validate DCS code if provided
    if dcs_code is not None:
        from .dcs import DCS_CODES

        if dcs_code not in DCS_CODES:
            click.echo(f"Error: Invalid DCS code {dcs_code}.", err=True)
            sys.exit(1)

    # Freq is required (either from CLI or preset)
    if freq is None:
        click.echo("Error: Must provide -f/--freq or --preset.", err=True)
        sys.exit(1)

    # Parse the frequency string
    try:
        freq = parse_frequency(freq) if isinstance(freq, str) else freq
        validate_frequency(freq)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Generate output filename if not specified
    if output is None:
        recordings_dir = Path("recordings")
        recordings_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        freq_str = format_frequency(freq).replace(" ", "").replace(".", "_")
        output = str(
            recordings_dir / f"recording_{freq_str}_{mod}_{timestamp}.{audio_format}"
        )

    # Ensure correct extension
    output_path = Path(output)
    if audio_format == "wav" and output_path.suffix != ".wav":
        output_path = output_path.with_suffix(".wav")

    # Parse gain
    gain_val: str | float
    if gain == "auto":
        gain_val = "auto"
    else:
        try:
            gain_val = float(gain)
        except ValueError:
            raise click.BadParameter(f"Invalid gain '{gain}'. Use a number or 'auto'.")

    # Set up transcriber if requested
    transcriber_instance = None
    if transcribe:
        try:
            from .transcriber import Transcriber
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        if transcript_path is None:
            recordings_dir = Path("recordings")
            recordings_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fstr = format_frequency(freq).replace(" ", "").replace(".", "_")
            transcript_path = str(
                recordings_dir / f"transcript_{fstr}_{mod}_{timestamp}.log"
            )

        try:
            transcriber_instance = Transcriber(
                model_size=whisper_model,
                language=language,
                log_path=transcript_path,
                label=label,
                prompt=prompt,
            )
        except RuntimeError as e:
            click.echo(f"Transcription error: {e}", err=True)
            sys.exit(1)

    # Set up audio monitor if requested
    audio_monitor_instance = None
    if monitor:
        from .monitor import AudioMonitor

        audio_monitor_instance = AudioMonitor(volume=volume)

    # Print configuration
    click.echo(f"Frequency:  {format_frequency(freq)}", err=True)
    click.echo(f"Modulation: {mod.upper()}", err=True)
    click.echo(f"Gain:       {gain_val}", err=True)
    click.echo(f"Squelch:    {squelch:.0f} dB", err=True)
    if ppm:
        click.echo(f"PPM:        {ppm}", err=True)
    if dcs_code:
        click.echo(f"DCS Code:   {dcs_code}", err=True)
    click.echo(f"Output:     {output_path}", err=True)
    click.echo(f"Format:     {audio_format.upper()}", err=True)
    if transcriber_instance:
        click.echo(
            f"Transcribe: {transcriber_instance.model_size} model | "
            f"Log: {transcript_path}",
            err=True,
        )
        if label:
            click.echo(f"Label:      {label}", err=True)
    if duration:
        click.echo(f"Duration:   {duration:.0f}s", err=True)
    else:
        click.echo("Duration:   Until Ctrl+C", err=True)
    click.echo("", err=True)

    try:
        # Set up StateManager and optional MQTT bridge
        state_manager = None
        mqtt_bridge = None
        if mqtt_broker is not None:
            from .mqtt_bridge import MqttBridge
            from .state import StateManager

            state_manager = StateManager()
            mqtt_bridge = MqttBridge(
                state_manager, broker=mqtt_broker, prefix=mqtt_prefix
            )
            mqtt_bridge.start()

        # Set up optional audio WebSocket server
        audio_ws_server = None
        if audio_ws_port is not None:
            from .audio_ws import AudioWSServer

            audio_ws_server = AudioWSServer(port=audio_ws_port)
            audio_ws_server.start()

        config = RecordConfig(
            freq=freq,
            mod=mod,
            output_path=output_path,
            audio_format=audio_format,
            duration=duration,
            gain=gain_val,
            squelch_db=squelch,
            device=device,
            ppm=ppm,
            transcriber=transcriber_instance,
            monitor=audio_monitor_instance,
            volume=volume,
            label=label,
            dcs_code=dcs_code,
            state_manager=state_manager,
            audio_ws=audio_ws_server,
        )
        stats = RecordingSession(config).run()

        # Print final stats
        click.echo("", err=True)
        click.echo("Recording complete:", err=True)
        click.echo(f"  File:     {stats['file']}", err=True)
        click.echo(f"  Duration: {stats['audio_duration_sec']:.1f}s", err=True)
        click.echo(f"  Size:     {stats['file_size_bytes'] / 1024:.1f} KB", err=True)
        if transcriber_instance:
            click.echo(
                f"  Transcriptions: {transcriber_instance.transcription_count}",
                err=True,
            )

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)
    finally:
        if audio_ws_server is not None:
            audio_ws_server.stop()
        if mqtt_bridge is not None:
            mqtt_bridge.stop()


@main.group()
def scan():
    """Scan for active or clear frequencies."""


@scan.command("active")
@click.option(
    "--start",
    required=True,
    callback=_parse_freq_param,
    help="Start frequency (e.g. 144M).",
)
@click.option(
    "--end",
    required=True,
    callback=_parse_freq_param,
    help="End frequency (e.g. 148M).",
)
@click.option(
    "--step",
    required=True,
    callback=_parse_freq_value,
    help="Step size (e.g. 25k, 12.5k).",
)
@click.option(
    "--threshold",
    type=float,
    default=-30.0,
    show_default=True,
    help="Signal detection threshold in dB.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Save results to CSV file.",
)
@click.option(
    "--device",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR device index.",
)
@click.option(
    "-g",
    "--gain",
    default="auto",
    help="SDR gain in dB, or 'auto' (default: auto).",
)
@click.option(
    "--ppm",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR frequency correction in PPM.",
)
def scan_active(start, end, step, threshold, output, device, gain, ppm):
    """Scan for active frequencies in a range.

    Performs a single sweep through the frequency range and reports
    frequencies with signal power above the threshold.

    Examples:

        vtms-sdr scan active --start 144M --end 148M --step 25k

        vtms-sdr scan active --start 440M --end 450M --step 12.5k -o scan.csv
    """
    from .sdr import SDRDevice
    from .scanner import FrequencyScanner, format_scan_report, format_scan_csv

    gain_val: str | float = gain if gain == "auto" else float(gain)

    try:
        with SDRDevice(device_index=device) as sdr:
            sdr.configure(center_freq=start, gain=gain_val, ppm=ppm)

            scanner = FrequencyScanner(
                sdr, threshold_db=threshold, gain=gain_val, ppm=ppm
            )
            report = scanner.scan_active(start, end, step)

        # Print results
        click.echo(format_scan_report(report))

        # Optionally save CSV
        if output:
            csv_data = format_scan_csv(report)
            Path(output).write_text(csv_data)
            click.echo(f"\nResults saved to {output}", err=True)

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--model",
    "whisper_model",
    type=click.Choice(["auto", "tiny", "base", "small", "medium", "large"]),
    default="auto",
    show_default=True,
    help="Whisper model size. 'auto' picks based on hardware.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Path for transcript log file.",
)
@click.option(
    "--label",
    type=str,
    default=None,
    help="Channel label for transcript output (e.g. 'PIT-CREW').",
)
@click.option(
    "--language",
    type=str,
    default="en",
    show_default=True,
    help="Language code for transcription (e.g. 'en', 'es', 'de').",
)
@click.option(
    "--prompt",
    type=str,
    default=None,
    help="Custom initial prompt for Whisper (overrides default motorsport prompt).",
)
def transcribe(file, whisper_model, output, label, language, prompt):
    """Transcribe a pre-recorded audio file.

    Runs Whisper speech recognition on a WAV file and prints the
    transcription. Optionally saves a transcript log file.

    Examples:

        vtms-sdr transcribe recording.wav

        vtms-sdr transcribe recording.wav --model base -o transcript.log

        vtms-sdr transcribe recording.wav --label PIT-CREW -o transcript.log
    """
    try:
        from .transcriber import transcribe_file
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        text = transcribe_file(
            audio_path=file,
            model_size=whisper_model,
            language=language,
            log_path=output,
            label=label,
            prompt=prompt,
        )
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(text)

    if output:
        click.echo(f"Transcript saved to {output}", err=True)


@scan.command("clear")
@click.option(
    "--start",
    required=True,
    callback=_parse_freq_param,
    help="Start frequency (e.g. 144M).",
)
@click.option(
    "--end",
    required=True,
    callback=_parse_freq_param,
    help="End frequency (e.g. 148M).",
)
@click.option(
    "--step",
    required=True,
    callback=_parse_freq_value,
    help="Step size (e.g. 25k, 12.5k).",
)
@click.option(
    "-d",
    "--duration",
    type=float,
    default=300.0,
    show_default=True,
    help="Monitoring duration in seconds.",
)
@click.option(
    "--threshold",
    type=float,
    default=-30.0,
    show_default=True,
    help="Signal detection threshold in dB.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Save results to CSV file.",
)
@click.option(
    "--device",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR device index.",
)
@click.option(
    "-g",
    "--gain",
    default="auto",
    help="SDR gain in dB, or 'auto' (default: auto).",
)
@click.option(
    "--ppm",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR frequency correction in PPM.",
)
def scan_clear(start, end, step, duration, threshold, output, device, gain, ppm):
    """Find clear (unused) frequencies in a range.

    Monitors the frequency range for the specified duration and reports
    frequencies that stayed below the threshold the entire time. Useful
    for finding a good frequency to use.

    Examples:

        vtms-sdr scan clear --start 144M --end 148M --step 25k -d 300

        vtms-sdr scan clear --start 462M --end 467M --step 12.5k -d 600
    """
    from .sdr import SDRDevice
    from .scanner import FrequencyScanner, format_scan_report, format_scan_csv

    gain_val: str | float = gain if gain == "auto" else float(gain)

    try:
        with SDRDevice(device_index=device) as sdr:
            sdr.configure(center_freq=start, gain=gain_val, ppm=ppm)

            scanner = FrequencyScanner(
                sdr, threshold_db=threshold, gain=gain_val, ppm=ppm
            )
            report = scanner.scan_clear(start, end, step, duration_sec=duration)

        # Print results
        click.echo(format_scan_report(report))

        # Optionally save CSV
        if output:
            csv_data = format_scan_csv(report)
            Path(output).write_text(csv_data)
            click.echo(f"\nResults saved to {output}", err=True)

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@scan.command("recommend")
@click.option(
    "--start",
    required=True,
    callback=_parse_freq_param,
    help="Start frequency (e.g. 400MHz).",
)
@click.option(
    "--end",
    required=True,
    callback=_parse_freq_param,
    help="End frequency (e.g. 470MHz).",
)
@click.option(
    "--step",
    required=True,
    callback=_parse_freq_value,
    help="Step size (e.g. 25kHz).",
)
@click.option(
    "-d",
    "--duration",
    type=float,
    default=300.0,
    show_default=True,
    help="Monitoring duration in seconds.",
)
@click.option(
    "--threshold",
    type=float,
    default=-30.0,
    show_default=True,
    help="Signal detection threshold in dB.",
)
@click.option(
    "--top",
    "top_n",
    default=0,
    type=int,
    help="Show only the top N channels (default: all).",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Save full results to CSV file.",
)
@click.option(
    "--device",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR device index.",
)
@click.option(
    "-g",
    "--gain",
    default="auto",
    help="SDR gain in dB, or 'auto' (default: auto).",
)
@click.option(
    "--ppm",
    type=int,
    default=0,
    show_default=True,
    help="RTL-SDR frequency correction in PPM.",
)
def scan_recommend(
    start, end, step, duration, threshold, top_n, output, device, gain, ppm
):
    """Recommend clear channels for team radio use.

    Scans the frequency range over multiple passes, ranks every channel
    by how quiet and consistently clear it is, and outputs a sorted
    recommendation table.

    Examples:

        vtms-sdr scan recommend --start 446MHz --end 446.2MHz --step 25kHz

        vtms-sdr scan recommend --start 400MHz --end 470MHz --step 25kHz -d 600

        vtms-sdr scan recommend --start 462MHz --end 467MHz --step 12.5kHz --top 10
    """
    from .sdr import SDRDevice
    from .scanner import (
        FrequencyScanner,
        format_recommend_report,
        format_scan_csv,
    )

    gain_val: str | float = gain if gain == "auto" else float(gain)

    try:
        with SDRDevice(device_index=device) as sdr:
            sdr.configure(center_freq=start, gain=gain_val, ppm=ppm)

            scanner = FrequencyScanner(
                sdr, threshold_db=threshold, gain=gain_val, ppm=ppm
            )
            report = scanner.scan_recommend(start, end, step, duration_sec=duration)

        # Print ranked results
        click.echo(format_recommend_report(report, top_n=top_n))

        # Optionally save CSV
        if output:
            csv_data = format_scan_csv(report)
            Path(output).write_text(csv_data)
            click.echo(f"\nResults saved to {output}", err=True)

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
