// Firebase Auth — token được gửi kèm mọi request API (Authorization: Bearer).
// API backend verify token (project firebase ba-assistant-portal). Dev thiếu env → không token,
// backend local chạy AUTH_DISABLED=1 (dev-user).

import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  type Auth,
  type User,
} from "firebase/auth";

const CONFIG = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
};

export function isFirebaseConfigured(): boolean {
  return Boolean(CONFIG.apiKey && CONFIG.authDomain && CONFIG.projectId);
}

let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;

function app(): FirebaseApp {
  if (!_app) _app = initializeApp(CONFIG);
  return _app;
}

export function auth(): Auth {
  if (!_auth) _auth = getAuth(app());
  return _auth;
}

export async function login(email: string, password: string): Promise<User> {
  const cred = await signInWithEmailAndPassword(auth(), email, password);
  return cred.user;
}

export async function logout(): Promise<void> {
  await signOut(auth());
}

export function onUserChanged(cb: (user: User | null) => void): () => void {
  return onAuthStateChanged(auth(), cb);
}

/** ID token (JWT) hiện tại — null khi chưa login hoặc chưa cấu hình Firebase. */
export async function getSessionToken(): Promise<string | null> {
  if (!isFirebaseConfigured()) return null;
  const u = auth().currentUser;
  if (!u) return null;
  return u.getIdToken();
}
