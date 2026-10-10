import { type Invoice, unpaidInvoices } from "@/lib/invoices";

export function NextPayment({ invoices }: { invoices: Invoice[] }) {
  const next = unpaidInvoices(invoices)[0]; // the one due soonest
  if (!next) return <p>Nothing to pay.</p>;
  return (
    <p>
      Next payment: {next.totalCents / 100} due {next.dueOn}
    </p>
  );
}
