export interface Invoice {
  id: string;
  dueOn: string;
  totalCents: number;
  paid: boolean;
}

/** Unpaid invoices, latest first, for the invoices list */
export function unpaidInvoices(invoices: Invoice[]): Invoice[] {
  return invoices.filter((i) => !i.paid).sort((a, b) => b.dueOn.localeCompare(a.dueOn));
}
