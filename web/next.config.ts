import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pages from the old task-based navigation, folded into the new sections.
  // Temporary (307) so a browser never caches a mapping we may change again.
  async redirects() {
    return [
      { source: "/today", destination: "/", permanent: false },
      { source: "/build", destination: "/", permanent: false },
      { source: "/calendar", destination: "/matches/calendar", permanent: false },
      { source: "/calendar/:date", destination: "/matches/calendar/:date", permanent: false },
      { source: "/generate", destination: "/picks?tab=value", permanent: false },
      { source: "/pool", destination: "/picks?tab=pool", permanent: false },
      { source: "/results", destination: "/analytics", permanent: false },
    ];
  },
};

export default nextConfig;
