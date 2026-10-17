/**
 * Represents tax information.
 */
export interface Tax {
  /**
   * The tax name (e.g., GST, VAT).
   */
  name: string;
  /**
   * The tax rate as a decimal (e.g., 0.05 for 5%).
   */
  rate: number;
}

/**
 * Asynchronously retrieves the applicable taxes.
 *
 * @returns A promise that resolves to an array of Tax objects.
 */
export async function getApplicableTaxes(): Promise<Tax[]> {
  // TODO: Implement this by calling an API.

  return [
    {
      name: 'GST',
      rate: 0.05,
    },
  ];
}
