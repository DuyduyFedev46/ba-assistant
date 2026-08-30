import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BA Assistant — Trạng thái sống của buổi họp",
  description: "Hiểu-họp theo nhịp: quyết định, câu hỏi treo, hành động — cập nhật theo nhịp.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
