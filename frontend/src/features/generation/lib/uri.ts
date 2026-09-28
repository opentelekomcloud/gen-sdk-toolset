/** The path parameters of an endpoint's URI, in order: `/v1/billing/invoices/{invoice_id}` takes `invoice_id`. */
export const pathParams = (uri: string): string[] => [...uri.matchAll(/\{([^}]+)\}/g)].map((m) => m[1]);
