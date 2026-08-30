"use client";

// Đăng nhập Firebase Auth (email/password) — dev thiếu env thì báo để dùng backend AUTH_DISABLED.
// Sau khi login thành công → về màn hình chính (dữ liệu chỉ lấy được khi token hợp lệ).

import { useRouter } from "next/navigation";
import { useState } from "react";

import { isFirebaseConfigured, login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!isFirebaseConfigured()) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <div className="rounded-lg border border-line bg-paper p-6 text-sm">
          <p className="font-semibold text-ink">Chưa cấu hình Firebase Auth</p>
          <p className="mt-2 text-ink-2">
            Dev: backend local chạy AUTH_DISABLED=1 nên không cần token — vào{" "}
            <a className="text-accent underline" href="/">
              màn hình chính
            </a>{" "}
            trực tiếp.
            <br />
            Prod: set NEXT_PUBLIC_FIREBASE_API_KEY / AUTH_DOMAIN / PROJECT_ID.
          </p>
        </div>
      </main>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi đăng nhập");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-16">
      <h1 className="text-2xl font-bold text-ink">Đăng nhập</h1>
      <p className="mt-1 text-sm text-ink-2">Email + mật khẩu (Firebase Auth).</p>
      <form onSubmit={submit} className="mt-6 space-y-3">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="w-full rounded-md border border-line-2 bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent"
        />
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="mật khẩu"
          className="w-full rounded-md border border-line-2 bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
        >
          {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </button>
      </form>
    </main>
  );
}
