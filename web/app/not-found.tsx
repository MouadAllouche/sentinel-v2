import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">The requested page does not exist.</p>
      <Link className="mt-4 inline-block text-blue-700 underline" href="/">
        Return to Overview
      </Link>
    </main>
  );
}
