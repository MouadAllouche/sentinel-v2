import { Overview } from "@/components/overview/Overview";

export default function OverviewPage() {
  // Rendered on the server (the layout is dynamic); passing this value down as
  // a prop keeps SSR and the first client render identical, so no hydration
  // mismatch and no unstable query keys from a second clock read.
  const now = new Date().toISOString();
  return <Overview now={now} />;
}
