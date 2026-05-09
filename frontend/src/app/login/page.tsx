"use client";

import { Suspense } from "react";
import LoginContent from "./LoginContent";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            background: "var(--bg-primary)",
            color: "var(--text-muted)",
            fontSize: "13px",
          }}
        >
          Loading…
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
