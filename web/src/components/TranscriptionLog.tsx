import { useEffect, useRef } from "react";
import type { TranscriptionLine } from "../types/sdr";

interface TranscriptionLogProps {
  /** Transcription lines to display */
  lines: TranscriptionLine[];
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/**
 * Scrolling log of transcription lines with timestamps.
 *
 * Auto-scrolls to bottom when new entries arrive.
 * Uses `role="log"` for accessibility.
 */
export function TranscriptionLog({ lines }: TranscriptionLogProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines.length]);

  return (
    <div
      className="transcription-log"
      role="log"
      aria-label="Radio transcriptions"
      ref={containerRef}
    >
      {lines.length === 0 ? (
        <div className="transcription-log__empty">No transcriptions yet</div>
      ) : (
        lines.map((line, i) => (
          <div className="transcription-log__entry" key={`${line.timestamp}-${i}`}>
            <span className="transcription-log__time">{formatTime(line.timestamp)}</span>
            <span className="transcription-log__text">{line.text}</span>
          </div>
        ))
      )}
    </div>
  );
}
