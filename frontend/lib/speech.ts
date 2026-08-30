// Nhận dạng giọng nói bằng Web Speech API (có sẵn trong trình duyệt, không cần
// API key, không cần backend). FE chỉ biến tiếng thành CHỮ rồi POST /ingest —
// mọi việc cắt nhịp/đọc hiểu vẫn ở engine (luật L2: FE mỏng tuyệt đối).
//
// Giới hạn cần biết:
//  · Chrome/Edge/Safari có; Firefox không → tự fallback về ô gõ tay.
//  · Chỉ chạy trên https hoặc localhost.
//  · KHÔNG tách được người nói (diarization) — speaker do người dùng tự đặt.
//  · Chrome gửi âm thanh lên máy chủ Google để nhận dạng.

import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechAlternative {
  transcript: string;
}
interface SpeechResult {
  readonly length: number;
  readonly isFinal: boolean;
  [index: number]: SpeechAlternative;
}
interface SpeechResultList {
  readonly length: number;
  [index: number]: SpeechResult;
}
interface SpeechEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechResultList;
}
interface SpeechErrorEvent extends Event {
  readonly error: string;
}
interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechEvent) => void) | null;
  onerror: ((e: SpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognition;

function getCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Trình duyệt chặn mic — bấm biểu tượng ổ khoá trên thanh địa chỉ để cho phép.",
  "service-not-allowed": "Trình duyệt chặn dịch vụ nhận dạng giọng nói.",
  "audio-capture": "Không tìm thấy micro.",
  network: "Mất mạng — nhận dạng giọng nói cần internet.",
};

/**
 * Mic → chữ. Mỗi câu hoàn chỉnh (isFinal) gọi onFinal một lần = một lượt nói,
 * đúng hạt "chunk" mà POST /ingest mong đợi.
 */
export function useSpeech({ lang = "vi-VN", onFinal }: { lang?: string; onFinal: (text: string) => void }) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [supported, setSupported] = useState(false);

  const recRef = useRef<SpeechRecognition | null>(null);
  const wantRef = useRef(false); // người dùng CÓ muốn nghe không (khác với đang nghe)
  const finalRef = useRef(onFinal);
  finalRef.current = onFinal;

  useEffect(() => setSupported(getCtor() !== null), []);

  const stop = useCallback(() => {
    wantRef.current = false;
    setListening(false);
    setInterim("");
    recRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    const Ctor = getCtor();
    if (!Ctor) {
      setError("Trình duyệt này không hỗ trợ nhận dạng giọng nói — dùng ô gõ tay bên dưới.");
      return;
    }
    setError(null);
    wantRef.current = true;

    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;

    rec.onresult = (e) => {
      let pending = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const text = r[0]?.transcript ?? "";
        if (r.isFinal) {
          const clean = text.trim();
          if (clean) finalRef.current(clean);
        } else {
          pending += text;
        }
      }
      setInterim(pending);
    };

    rec.onerror = (e) => {
      // "no-speech"/"aborted" là chuyện thường khi im lặng — onend sẽ tự bật lại.
      if (e.error === "no-speech" || e.error === "aborted") return;
      setError(ERRORS[e.error] ?? `Lỗi nhận dạng: ${e.error}`);
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        wantRef.current = false;
        setListening(false);
      }
    };

    // Chrome tự ngắt sau một quãng im lặng — còn muốn nghe thì bật lại.
    rec.onend = () => {
      setInterim("");
      if (wantRef.current) {
        try {
          rec.start();
        } catch {
          setListening(false);
        }
      } else {
        setListening(false);
      }
    };

    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      setError("Không khởi động được mic.");
      wantRef.current = false;
      setListening(false);
    }
  }, [lang]);

  useEffect(() => {
    return () => {
      wantRef.current = false;
      recRef.current?.abort();
    };
  }, []);

  return { supported, listening, interim, error, start, stop };
}
