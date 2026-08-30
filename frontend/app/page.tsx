"use client";

// Màn hình duy nhất của portal (3 cột). Không còn tách "danh sách" và "dashboard"
// làm 2 route — mọi thứ nằm trên một màn, chọn note ở cột trái.

import { Workspace } from "./meetings/workspace";

export default function Home() {
  return <Workspace />;
}
