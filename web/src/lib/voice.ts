/**
 * Thin wrapper around the browser's built-in Web Speech API (SpeechRecognition
 * for mic -> text, SpeechSynthesis for text -> voice) -- both ship free in
 * Chrome/Edge/Safari with no backend or API key, which is why this stays
 * entirely client-side rather than routing through a cloud STT/TTS service.
 * Firefox doesn't implement SpeechRecognition; isSpeechRecognitionSupported()
 * is how callers detect that and disable voice mode gracefully.
 *
 * Minimal local types for the handful of members actually used -- the Web
 * Speech API isn't part of TypeScript's standard DOM lib (non-standard/
 * vendor-prefixed), so there's no official @types coverage to import.
 */

interface SpeechRecognitionResult {
  0: { transcript: string };
  isFinal: boolean;
}

interface SpeechRecognitionEvent {
  results: ArrayLike<SpeechRecognitionResult>;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const isSpeechRecognitionSupported = (): boolean => getSpeechRecognitionCtor() !== null;
export const isSpeechSynthesisSupported = (): boolean => "speechSynthesis" in window;

/**
 * One listening turn: non-continuous (recognizer stops itself after a
 * pause), interim results enabled so the caller can show a live transcript
 * as the user talks, same as Wispr's live-preview-while-you-speak feel.
 * Returns null if this browser doesn't support it at all.
 */
export function startListening({
  onResult,
  onError,
  onEnd,
}: {
  onResult: (transcript: string, isFinal: boolean) => void;
  onError: (error: string) => void;
  onEnd: () => void;
}): SpeechRecognitionLike | null {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) return null;

  const recognizer = new Ctor();
  recognizer.continuous = false;
  recognizer.interimResults = true;
  recognizer.lang = "en-US";
  recognizer.onresult = (event) => {
    const result = event.results[event.results.length - 1];
    onResult(result[0].transcript, result.isFinal);
  };
  recognizer.onerror = (event) => onError(event.error);
  recognizer.onend = onEnd;
  recognizer.start();
  return recognizer;
}

/** Speaks text aloud; returns a function to cancel mid-utterance (e.g. the
 * user tapping the mic to interrupt and talk instead -- "barge-in"). */
export function speak(text: string, onEnd: () => void): () => void {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onend = onEnd;
  utterance.onerror = onEnd;
  window.speechSynthesis.cancel(); // clear anything still queued from before
  window.speechSynthesis.speak(utterance);
  return () => window.speechSynthesis.cancel();
}
