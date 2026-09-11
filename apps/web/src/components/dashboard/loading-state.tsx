import { LoaderCircle } from "lucide-react";

export function LoadingState({
  label = "Loading workspace",
}: {
  label?: string;
}) {
  return (
    <div className="grid min-h-60 place-items-center rounded-2xl border border-line bg-surface text-center">
      <div>
        <LoaderCircle
          className="mx-auto animate-spin text-accent-ink"
          size={26}
        />
        <p className="mt-4 text-sm font-bold text-ink-secondary">{label}</p>
      </div>
    </div>
  );
}
