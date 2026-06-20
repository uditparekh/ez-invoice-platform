import { AppShell } from "@/components/app-shell";
import { AuthProvider } from "@/components/auth-provider";

export default function ProductLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
