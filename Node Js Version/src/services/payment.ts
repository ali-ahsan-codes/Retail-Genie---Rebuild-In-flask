/**
 * Represents the result of a payment transaction.
 */
export interface PaymentResult {
  /**
   * Indicates whether the payment was successful.
   */
  success: boolean;
  /**
   * A message providing details about the payment result.
   */
  message: string;
  /**
   * The transaction ID.
   */
  transactionId: string;
}

/**
 * Represents the payment methods.
 */
export type PaymentMethod = 'card' | 'cash' | 'bankTransfer';

/**
 * Represents a payment.
 */
export interface Payment {
  /**
   * The payment method.
   */
  method: PaymentMethod;
  /**
   * The payment amount.
   */
  amount: number;
}

/**
 * Asynchronously processes a payment.
 *
 * @param payments The payments information.
 * @param orderId The id of the order being paid.
 * @returns A promise that resolves to a PaymentResult object.
 */
export async function processPayment(payments: Payment[], orderId: string): Promise<PaymentResult> {
  // TODO: Implement this by calling an API.

  return {
    success: true,
    message: 'Payment successful',
    transactionId: '123456',
  };
}
