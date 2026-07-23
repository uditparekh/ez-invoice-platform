import { LoaderCircle } from "lucide-react";

export default function AppLoading() {
  return (
    <div className="grid min-h-screen place-items-center bg-canvas">
      <div className="flex flex-col items-center gap-3">
        <LoaderCircle size={24} className="animate-spin text-accent" />
        <p className="text-xs font-bold text-ink-muted">
          Opening your workspace
        </p>
      </div>
    </div>
  );
}
