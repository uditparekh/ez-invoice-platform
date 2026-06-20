import type { Metadata } from "next";

import { InvoiceWorkspace } from "@/components/invoice-workspace";

export const metadata: Metadata = { title: "Invoice queue" };

export default function InvoicesPage() {
  return <InvoiceWorkspace />;
}
