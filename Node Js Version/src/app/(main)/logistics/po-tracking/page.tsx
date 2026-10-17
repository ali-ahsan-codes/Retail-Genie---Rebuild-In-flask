// src/app/(main)/logistics/po-tracking/page.tsx
'use client';
import { useState, useMemo, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Bell, Truck, History, CalendarIcon, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useApp } from '@/context/AppContext';
import type { PurchaseOrder } from '@/types';
import Link from 'next/link';
import { format, parseISO } from 'date-fns';

export default function POTracking() {
  const { purchaseOrders, suppliers } = useApp();
  const [activeTab, setActiveTab] = useState('pending');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredPOs = useMemo(() => {
    return purchaseOrders.filter(po => {
        const supplierName = suppliers.find(s => s.id === po.supplier_id)?.name || '';
        const searchMatch =
            po.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            supplierName.toLowerCase().includes(searchTerm.toLowerCase()) ||
            po.status.toLowerCase().includes(searchTerm.toLowerCase());
        
        if (activeTab === 'pending') {
            return po.status === 'Confirmed' && searchMatch;
        }
        if (activeTab === 'in_transit') {
            return po.status === 'Shipped' && searchMatch;
        }
        if (activeTab === 'history') {
            return po.status === 'Received' && searchMatch;
        }
        return false;
    }).sort((a,b) => parseISO(b.updatedAt).getTime() - parseISO(a.updatedAt).getTime());
  }, [purchaseOrders, suppliers, searchTerm, activeTab]);

  return (
    <div className="space-y-6">
       <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Purchase Order Tracking</CardTitle>
          <CardDescription>Monitor deliveries and manage transportation logistics.</CardDescription>
        </CardHeader>
      </Card>

      <Tabs defaultValue="pending" className="w-full" onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-1 sm:grid-cols-3">
          <TabsTrigger value="pending"><Bell className="mr-2 h-4 w-4" />Awaiting Delivery ({purchaseOrders.filter(p => p.status === 'Confirmed').length})</TabsTrigger>
          <TabsTrigger value="in_transit"><Truck className="mr-2 h-4 w-4" />In Transit ({purchaseOrders.filter(p => p.status === 'Shipped').length})</TabsTrigger>
          <TabsTrigger value="history"><History className="mr-2 h-4 w-4" />Delivery History</TabsTrigger>
        </TabsList>
        
        <div className="my-4">
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search by PO Number, Supplier, or Status..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                />
            </div>
        </div>

        <TabsContent value="pending" className="mt-4">
            <Card>
                <CardContent className="p-4">
                    <Table>
                        <TableHeader><TableRow><TableHead>PO Number</TableHead><TableHead>Supplier</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                        <TableBody>
                            {filteredPOs.map(po => (
                                <TableRow key={po.id}>
                                    <TableCell>{po.id}</TableCell>
                                    <TableCell>{suppliers.find(s => s.id === po.supplier_id)?.name || 'N/A'}</TableCell>
                                    <TableCell><Badge variant="outline">{po.status}</Badge></TableCell>
                                    <TableCell className="text-right">
                                        <Button asChild variant="outline" size="sm">
                                            <Link href={`/admin/scm/po/${po.id}`}>View Details</Link>
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {filteredPOs.length === 0 && <TableRow><TableCell colSpan={4} className="text-center">No pending deliveries match your search.</TableCell></TableRow>}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </TabsContent>
        <TabsContent value="in_transit" className="mt-4">
            <Card>
                <CardContent className="p-4">
                    <Table>
                        <TableHeader><TableRow><TableHead>PO Number</TableHead><TableHead>Supplier</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                        <TableBody>
                            {filteredPOs.map(po => (
                                <TableRow key={po.id}>
                                    <TableCell>{po.id}</TableCell>
                                    <TableCell>{suppliers.find(s => s.id === po.supplier_id)?.name || 'N/A'}</TableCell>
                                    <TableCell><Badge variant="default" className="bg-cyan-100 text-cyan-700">{po.status}</Badge></TableCell>
                                    <TableCell className="text-right">
                                        <Button asChild variant="outline" size="sm">
                                            <Link href={`/admin/scm/po/${po.id}`}>View Details</Link>
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {filteredPOs.length === 0 && <TableRow><TableCell colSpan={4} className="text-center">No orders are currently in transit.</TableCell></TableRow>}
                        </TableBody>
                    </Table>
                </CardContent>
           </Card>
        </TabsContent>
        <TabsContent value="history" className="mt-4">
           <Card>
                <CardContent className="p-4">
                    <Table>
                        <TableHeader><TableRow><TableHead>PO Number</TableHead><TableHead>Supplier</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                        <TableBody>
                            {filteredPOs.map(po => (
                                <TableRow key={po.id}>
                                    <TableCell>{po.id}</TableCell>
                                    <TableCell>{suppliers.find(s => s.id === po.supplier_id)?.name || 'N/A'}</TableCell>
                                    <TableCell><Badge variant="default" className="bg-green-100 text-green-700">{po.status}</Badge></TableCell>
                                    <TableCell className="text-right">
                                        <Button asChild variant="outline" size="sm">
                                            <Link href={`/admin/scm/po/${po.id}`}>View Details</Link>
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                           {filteredPOs.length === 0 && <TableRow><TableCell colSpan={4} className="text-center">No delivery history matches your search.</TableCell></TableRow>}
                        </TableBody>
                    </Table>
                </CardContent>
           </Card>
        </TabsContent>

      </Tabs>
    </div>
  );
}
