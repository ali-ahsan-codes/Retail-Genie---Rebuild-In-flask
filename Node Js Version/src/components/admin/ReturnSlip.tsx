import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { format } from 'date-fns';
import { Order, ReturnDetails, OrderItem, Product, CustomItem } from '@/types';

interface ReturnSlipProps {
  order: Order;
  returnDetails: ReturnDetails;
}

const ReturnSlip: React.FC<ReturnSlipProps> = ({ order, returnDetails }) => {
  const getOrderItemDetails = (item: OrderItem) => {
    if (item.itemType === 'product' && item.product) {
      return (item.product as Product).name;
    } else if (item.itemType === 'custom' && item.customItem) {
      return (item.customItem as CustomItem).name;
    }
    return 'Unknown Item';
  };

  const calculateTotalReturnedValue = (returnDetails: ReturnDetails) => {
    return returnDetails.returnedItems.reduce((total, returnedItem) => {
      const originalItem = order.orderItems.find(
        (item) => item.id === returnedItem.orderItemId
      );
      if (originalItem) {
        return total + originalItem.price * returnedItem.returnedQuantity;
      }
      return total;
    }, 0);
  };

  const totalReturnedValue = calculateTotalReturnedValue(returnDetails);
  const netRefundPayment = returnDetails.refundAmount - returnDetails.exchangeDifference;

  return (
    <Card className="w-full max-w-2xl mx-auto print:shadow-none">
      <CardHeader>
        <CardTitle>Return Slip</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <p className="text-sm font-medium text-gray-500">Order ID:</p>
            <p className="text-lg font-semibold">{order.id}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Return ID:</p>
            <p className="text-lg font-semibold">{returnDetails.id}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Customer Name:</p>
            <p>{order.customerName}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Return Date:</p>
            <p>{format(new Date(returnDetails.returnDate), 'PPP')}</p>
          </div>
        </div>

        <h3 className="text-lg font-semibold mb-4">Returned Items</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead>Original Qty</TableHead>
              <TableHead>Returned Qty</TableHead>
              <TableHead>Price</TableHead>
              <TableHead className="text-right">Subtotal</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {returnDetails.returnedItems.map((returnedItem) => {
              const originalItem = order.orderItems.find(
                (item) => item.id === returnedItem.orderItemId
              );
              if (!originalItem) return null;

              return (
                <TableRow key={returnedItem.id}>
                  <TableCell className="font-medium">
                    {getOrderItemDetails(originalItem)}
                  </TableCell>
                  <TableCell>{originalItem.quantity}</TableCell>
                  <TableCell>{returnedItem.returnedQuantity}</TableCell>
                  <TableCell>${originalItem.price.toFixed(2)}</TableCell>
                  <TableCell className="text-right">
                    ${(originalItem.price * returnedItem.returnedQuantity).toFixed(2)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>

        <div className="mt-6">
          <h3 className="text-lg font-semibold mb-4">Return Summary</h3>
          <div className="flex justify-between items-center mb-2">
            <span className="font-medium">Total Returned Value:</span>
            <span>${totalReturnedValue.toFixed(2)}</span>
          </div>
          <div className="flex justify-between items-center mb-2">
            <span className="font-medium">Refund Amount:</span>
            <span>${returnDetails.refundAmount.toFixed(2)}</span>
          </div>
          {returnDetails.exchangeDifference > 0 && (
             <div className="flex justify-between items-center mb-2">
             <span className="font-medium">Exchange Difference (Amount Paid by Customer):</span>
             <span>${returnDetails.exchangeDifference.toFixed(2)}</span>
           </div>
          )}
           {returnDetails.exchangeDifference < 0 && (
             <div className="flex justify-between items-center mb-2">
             <span className="font-medium">Exchange Difference (Amount Refunded to Customer):</span>
             <span>${Math.abs(returnDetails.exchangeDifference).toFixed(2)}</span>
           </div>
          )}
          <div className="flex justify-between items-center font-bold text-lg mt-4 pt-4 border-t border-gray-200">
            <span>Net Refund/Payment:</span>
            <span>${netRefundPayment.toFixed(2)}</span>
          </div>
        </div>

        {returnDetails.notes && (
          <div className="mt-6">
            <h3 className="text-lg font-semibold mb-2">Notes:</h3>
            <p>{returnDetails.notes}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ReturnSlip;