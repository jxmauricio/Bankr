import { useEffect, useRef, useState } from "react";
import { isSpeechRecognitionSupported, isSpeechSynthesisSupported, speak, startListening } from "./voice";

export type VoiceState = "idle" | "listening" | "speaking";

/**
 * Hands-free voice conversation loop: tap the mic to start, talk, it
 * auto-sends on your final transcript, speaks the reply aloud, then starts
 * listening again for your next turn -- until you tap the mic again to stop
 * (or tap it mid-reply to interrupt/"barge in" and talk over it).
 *
 * A monotonic `turnId` guards every async callback (recognition result/end,
 * speech end) against acting after it's been superseded -- e.g. a barge-in
 * tap firing while the previous utterance's onend is still in flight.
 */
export function useVoiceMode({
  onFinalTranscript,
  onDraftChange,
  onError,
}: {
  onFinalTranscript: (text: string) => void;
  onDraftChange: (text: string) => void;
  onError: (message: string) => void;
}) {
  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");

  const voiceModeRef = useRef(voiceMode);
  const recognizerRef = useRef<ReturnType<typeof startListening>>(null);
  const cancelSpeechRef = useRef<(() => void) | null>(null);
  const turnRef = useRef(0);

  useEffect(() => {
    voiceModeRef.current = voiceMode;
  }, [voiceMode]);

  useEffect(() => {
    return () => {
      recognizerRef.current?.abort();
      window.speechSynthesis?.cancel();
    };
  }, []);

  function listen() {
    const turnId = ++turnRef.current;
    const recognizer = startListening({
      onResult: (transcript, isFinal) => {
        if (turnRef.current !== turnId) return;
        onDraftChange(transcript);
        if (isFinal) {
          recognizerRef.current = null;
          setVoiceState("idle");
          onDraftChange("");
          const text = transcript.trim();
          if (text) onFinalTranscript(text);
        }
      },
      onError: (err) => {
        if (turnRef.current !== turnId) return;
        recognizerRef.current = null;
        setVoiceState("idle");
        if (err !== "aborted" && err !== "no-speech") onError(`Voice input failed (${err}).`);
      },
      onEnd: () => {
        // Recognition stopped without a final result (e.g. silence timeout)
        // -- don't get stuck showing "listening" forever.
        if (turnRef.current !== turnId) return;
        setVoiceState((s) => (s === "listening" ? "idle" : s));
      },
    });
    if (!recognizer) {
      onError("Voice mode isn't supported in this browser (try Chrome or Edge).");
      setVoiceMode(false);
      return;
    }
    recognizerRef.current = recognizer;
    setVoiceState("listening");
  }

  function toggle() {
    if (voiceState === "speaking") {
      turnRef.current++; // invalidate the in-flight speech's onend
      cancelSpeechRef.current?.();
      cancelSpeechRef.current = null;
      listen();
      return;
    }
    if (voiceMode) {
      turnRef.current++;
      recognizerRef.current?.abort();
      recognizerRef.current = null;
      setVoiceMode(false);
      setVoiceState("idle");
      return;
    }
    if (!isSpeechRecognitionSupported()) {
      onError("Voice mode isn't supported in this browser (try Chrome or Edge).");
      return;
    }
    setVoiceMode(true);
    listen();
  }

  /** Call once a reply arrives -- speaks it if voice mode is on, then
   * resumes listening for the next turn once it's done. No-op otherwise. */
  function speakReply(text: string) {
    if (!voiceModeRef.current || !isSpeechSynthesisSupported()) return;
    const turnId = ++turnRef.current;
    setVoiceState("speaking");
    cancelSpeechRef.current = speak(text, () => {
      if (turnRef.current !== turnId) return; // superseded by a barge-in
      cancelSpeechRef.current = null;
      if (voiceModeRef.current) listen();
      else setVoiceState("idle");
    });
  }

  return { voiceMode, voiceState, toggle, speakReply };
}
