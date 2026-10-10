import { unpaidInvoices } from "@/lib/invoices";
import { loadInvoices } from "@/lib/db";

export default async function InvoicesPage() {
  const invoices = unpaidInvoices(await loadInvoices());
  return <ul>{invoices.map((i) => <li key={i.id}>{i.dueOn}</li>)}</ul>;
}
