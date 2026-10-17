// src/components/ProductCard.tsx
'use client';
import Image from 'next/image';
import type { Product } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ShoppingCart, Package, Tag, AlertTriangle } from 'lucide-react';
import React, { useState, useEffect, useMemo } from 'react'; 
import { format, parseISO, isValid } from 'date-fns';
import { useApp } from '@/context/AppContext'; 

interface ProductCardProps {
  product: Product;
  onAddToCart: (product: Product, quantity: number) => void;
  allowPriceEdit?: boolean;
  currentPrice?: number; 
  onPriceChange?: (newPrice: number) => void;
}

const ProductCard = React.memo(function ProductCard({ product, onAddToCart, allowPriceEdit = false, currentPrice, onPriceChange }: ProductCardProps) {
  const { getEffectiveProductPrice } = useApp(); 
  const [quantity, setQuantity] = useState(1);
  
  const effectiveDisplayPrice = useMemo(() => {
    if (allowPriceEdit && currentPrice !== undefined) {
      return currentPrice;
    }
    return getEffectiveProductPrice(product);
  }, [allowPriceEdit, currentPrice, product, getEffectiveProductPrice]);

  const [editablePrice, setEditablePrice] = useState<number>(effectiveDisplayPrice);

  useEffect(() => {
    setEditablePrice(effectiveDisplayPrice);
  }, [effectiveDisplayPrice]);


  const handleAddToCart = () => {
    if (quantity > 0 && quantity <= product.quantityInStock) {
      onAddToCart(product, quantity);
      setQuantity(1); 
    }
  };

  const handlePriceInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newPriceValue = parseFloat(e.target.value);
    if (!isNaN(newPriceValue) && newPriceValue >=0) {
      setEditablePrice(newPriceValue); 
      if(onPriceChange && allowPriceEdit) {
        onPriceChange(newPriceValue); 
      }
    }
  };
  
  // product.imageUrl is now like "products/filename.ext"
  const imageApiSrc = product.imageUrl ? `/api/uploads/${product.imageUrl}` : null;
  
  const isLowStockPriceActive = product.lowStockThreshold !== undefined &&
                                product.lowStockPrice !== undefined &&
                                product.lowStockPrice > 0 &&
                                product.quantityInStock <= product.lowStockThreshold;

  return (
    <Card className="flex flex-col overflow-hidden shadow-lg hover:shadow-xl transition-shadow duration-300 h-full">
      <CardHeader className="p-0 relative">
        {imageApiSrc ? (
          <Image
            src={imageApiSrc} // Use the API path
            alt={product.name}
            width={400}
            height={300}
            className="object-cover w-full h-48"
            data-ai-hint="product item"
            unoptimized={true} 
            onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/400x300.png'; (e.target as HTMLImageElement).srcset = ''; }}
          />
        ) : (
          <div className="w-full h-48 flex items-center justify-center bg-muted">
            <Package className="w-16 h-16 text-muted-foreground" />
          </div>
        )}
      </CardHeader>
      <CardContent className="p-4 flex-grow">
        <CardTitle className="text-lg font-semibold mb-1 truncate" title={product.name}>{product.name}</CardTitle>
        <CardDescription className="text-sm text-muted-foreground mb-2">Product Code: {product.sku}</CardDescription>
        <div className="flex items-center justify-between mb-2">
          {allowPriceEdit ? (
            <div className="flex items-center">
               <Tag className="w-4 h-4 mr-1 text-primary" />
              <Input 
                type="number" 
                value={editablePrice.toString()} 
                onChange={handlePriceInputChange}
                className="h-8 w-24 text-base"
                min="0"
                step="0.01"
              />
            </div>
          ) : (
            <p className="text-xl font-bold text-primary">OMR {effectiveDisplayPrice.toFixed(2)}</p>
          )}
          <div className="flex items-center text-sm text-muted-foreground">
            <Package className="w-4 h-4 mr-1" />
            <span>{product.quantityInStock} in stock</span>
          </div>
        </div>
         {isLowStockPriceActive && (
            <p className="text-xs text-orange-600 font-semibold flex items-center mb-1">
              <AlertTriangle className="w-3 h-3 mr-1" /> Low Stock Price Applied!
            </p>
         )}
         {product.category && <p className="text-xs text-muted-foreground">Category: {product.category}</p>}
         {product.expiryDate && isValid(parseISO(product.expiryDate)) ? (
            <p className="text-xs text-muted-foreground">Expires: {format(parseISO(product.expiryDate), 'dd/MM/yyyy')}</p>
          ) : (
             product.expiryDate && product.expiryDate.trim() !== '' && product.expiryDate !== 'N/A' ? 
             <p className="text-xs text-muted-foreground">Expires: {product.expiryDate}</p> : 
             null 
          )}
      </CardContent>
      <CardFooter className="p-4 border-t">
        <div className="flex items-center gap-2 w-full">
          <Input
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
            min="1"
            max={product.quantityInStock}
            className="w-20 h-10 text-center"
            disabled={product.quantityInStock === 0}
          />
          <Button 
            onClick={handleAddToCart} 
            className="flex-1 h-10"
            disabled={product.quantityInStock === 0 || quantity <= 0 || quantity > product.quantityInStock}
          >
            <ShoppingCart className="mr-2 h-4 w-4" /> Add to Cart
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
});

export default ProductCard;
