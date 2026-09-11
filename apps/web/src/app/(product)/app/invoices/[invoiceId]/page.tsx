import { InvoiceWorkspace } from "@/components/invoice-workspace";

export default async function InvoicePage({
  params,
}: {
  params: Promise<{ invoiceId: string }>;
}) {
  const { invoiceId } = await params;
  return <InvoiceWorkspace key={invoiceId} initialInvoiceId={invoiceId} />;
}
