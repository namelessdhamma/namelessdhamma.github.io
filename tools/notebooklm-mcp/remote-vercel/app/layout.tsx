import type { ReactNode } from "react";

export const metadata = {
  title: "ND NotebookLM Remote MCP",
  description: "Transport qualification endpoint for Nameless Dhamma.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
