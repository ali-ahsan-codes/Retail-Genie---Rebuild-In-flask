
// src/app/(main)/profile/page.tsx
'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import AttendanceManager from "@/components/profile/AttendanceManager";
import BreakManager from "@/components/profile/BreakManager";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { UserCircle, Printer, ClockIcon, Zap, Settings } from "lucide-react"; 
import { ScrollArea } from "@/components/ui/scroll-area";
import { useApp } from "@/context/AppContext"; 
import CashierShiftSummary from "@/components/cashier/CashierShiftSummary"; 
import { Button } from "@/components/ui/button"; 
import { brandingConfig } from "@/config/branding";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";

export default function ProfileManagementPage() {
  const { currentUser, updateUserInDb, loadDataFromDb } = useApp();
  const { toast } = useToast();

  const handlePrintShiftSummary = () => {
    const printableArea = document.getElementById('shift-summary-printable-area-profile');
    if (!printableArea) {
      alert("Could not find printable summary content.");
      return;
    }

    const printWindow = window.open('', '_blank', 'height=800,width=1000');
    if (!printWindow) {
      alert("Popup blocked. Please allow popups for this site.");
      return;
    }

    // --- Data Extraction ---
    const reportTitle = printableArea.querySelector('h3.report-title-data')?.textContent || 'Shift Summary Report';
    
    const summaryCards: {title: string, value: string}[] = [];
    printableArea.querySelectorAll('.summary-card-data').forEach(card => {
        const title = card.querySelector('.title-data')?.textContent || '';
        const value = card.querySelector('.value-data')?.textContent || '';
        summaryCards.push({ title, value });
    });

    const grandTotalValue = printableArea.querySelector('.grand-total-value-data')?.textContent || 'OMR 0.00';

    const getTableData = (tableSelector: string): (string[])[] => {
      const table = printableArea.querySelector(tableSelector);
      if (!table) return [];
      const rows: (string[])[] = [];
      table.querySelectorAll('tbody tr').forEach(rowNode => {
          const rowData: string[] = [];
          rowNode.querySelectorAll('td').forEach(cellNode => {
              rowData.push(cellNode.innerText);
          });
          rows.push(rowData);
      });
      return rows;
    };
    
    const ordersData = getTableData('table.orders-table-data');
    const dnData = getTableData('table.dn-table-data');
    const orderHeaders = ['Order ID', 'Time', 'Paid/Applied', 'Order Total', 'Methods', 'Status', 'Closed Today?'];
    const dnHeaders = ['DN ID', 'Time', 'Product', 'Customer', 'Amount Paid', 'Methods', 'Total Agreed', 'Total DN Advance'];


    // --- HTML & CSS Generation ---
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const logoUrl = `${baseUrl}${brandingConfig.logoPath}`;

    const printStyles = `
      <style>
        @page { 
          size: A4 portrait; 
          margin: 0.75in; 
        }
        body { 
          font-family: Arial, sans-serif; 
          font-size: 10pt; 
          color: #333;
        }
        .print-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          border-bottom: 2px solid #333;
          padding-bottom: 1rem;
          margin-bottom: 1.5rem;
        }
        .print-header .logo { max-height: 50px; }
        .print-header .company-details { text-align: right; font-size: 9pt; color: #555; }
        .print-title { font-size: 18pt; font-weight: bold; margin-bottom: 0.5rem; }
        .print-title-container {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-bottom: 1.5rem;
        }
        .summary-card-container {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .summary-card {
          border: 1px solid #e0e0e0;
          border-radius: 8px;
          padding: 1rem;
          background-color: #f9f9f9;
        }
        .summary-card .title {
          font-size: 9pt;
          font-weight: bold;
          color: #666;
          margin-bottom: 0.5rem;
        }
        .summary-card .value {
          font-size: 16pt;
          font-weight: bold;
          color: #000;
        }
        .grand-total-line {
          text-align: right;
          font-size: 14pt;
          font-weight: bold;
          color: #16a34a; /* Green color for total */
        }
        .section-title { font-size: 12pt; font-weight: bold; margin-top: 2rem; margin-bottom: 0.5rem; border-bottom: 1px solid #ccc; padding-bottom: 0.25rem; }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 9pt;
        }
        th, td {
          border: 1px solid #ddd;
          padding: 0.5rem;
          text-align: left;
        }
        th {
          background-color: #f4f4f4;
          font-weight: bold;
        }
        tr:nth-child(even) { background-color: #f9f9f9; }
      </style>
    `;

    const printHtml = `
      <html>
        <head>
          <title>${reportTitle}</title>
          ${printStyles}
        </head>
        <body>
          <div class="print-header">
            <img src="${logoUrl}" alt="Logo" class="logo" />
            <div class="company-details">
              <strong>${brandingConfig.companyNameForInvoice}</strong><br/>
              ${brandingConfig.companyAddressForInvoice.replace(/, /g, '<br/>')}<br/>
              Tel: ${brandingConfig.companyPhoneForInvoice}
            </div>
          </div>
          <div class="print-title-container">
            <h1 class="print-title">${reportTitle}</h1>
            <div class="grand-total-line">${grandTotalValue}</div>
          </div>
          <div class="summary-card-container">
             ${summaryCards.map(card => `
                <div class="summary-card">
                    <div class="title">${card.title}</div>
                    <div class="value">${card.value}</div>
                </div>
             `).join('')}
          </div>
          ${ordersData.length > 0 ? `
            <h2 class="section-title">Orders with Activity</h2>
            <table>
              <thead><tr>${orderHeaders.map(h => `<th>${h}</th>`).join('')}</tr></thead>
              <tbody>${ordersData.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody>
            </table>
          ` : ''}
           ${dnData.length > 0 ? `
            <h2 class="section-title">Demand Notices with Activity</h2>
            <table>
              <thead><tr>${dnHeaders.map(h => `<th>${h}</th>`).join('')}</tr></thead>
              <tbody>${dnData.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody>
            </table>
          ` : ''}
        </body>
      </html>
    `;

    printWindow.document.write(printHtml);
    printWindow.document.close();
    
    setTimeout(() => {
      printWindow.focus();
      printWindow.print();
    }, 500);
  };
  
  const handleAutoEnterChange = async (checked: boolean) => {
    if (!currentUser) return;
    try {
      const updatedUser = await updateUserInDb({ ...currentUser, autoEnterAfterScan: checked });
      if (updatedUser) {
        toast({ title: "Setting Saved", description: `Auto Enter after scan is now ${checked ? 'enabled' : 'disabled'}.` });
        // The AppContext will automatically update the currentUser from the database response
      }
    } catch (error) {
      console.error("Failed to update user setting:", error);
      toast({ title: "Error", description: "Could not save your setting.", variant: "destructive" });
      await loadDataFromDb(); // Re-sync with DB on failure to revert optimistic UI if any
    }
  };
  
  const showShiftSummary = currentUser?.role === 'cashier' || currentUser?.role === 'express';
  const showExpressSettings = currentUser?.role === 'express';
  
  const tabListCols = `grid-cols-${[showShiftSummary, showExpressSettings].filter(Boolean).length + 2}`;

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <UserCircle className="mr-2 h-7 w-7 text-primary" /> Profile Management
          </CardTitle>
          <CardDescription>Manage your attendance, break times, and role-specific settings.</CardDescription>
        </CardHeader>
      </Card>

      <Tabs defaultValue="break" className="w-full">
        <TabsList className={`grid w-full ${tabListCols} md:w-auto`}>
          <TabsTrigger value="break">Break Time</TabsTrigger>
          <TabsTrigger value="attendance">Attendance</TabsTrigger>
          {showShiftSummary && <TabsTrigger value="shift_summary">Shift Summary</TabsTrigger>}
          {showExpressSettings && <TabsTrigger value="express_settings">Express Settings</TabsTrigger>}
        </TabsList>
        <TabsContent value="break">
          <ScrollArea className="h-[calc(100vh-20rem)]">
            <div className="p-1">
              <BreakManager />
            </div>
          </ScrollArea>
        </TabsContent>
        <TabsContent value="attendance">
          <ScrollArea className="h-[calc(100vh-20rem)]">
            <div className="p-1">
              <AttendanceManager />
            </div>
          </ScrollArea>
        </TabsContent>
        {showShiftSummary && (
          <TabsContent value="shift_summary">
            <ScrollArea className="h-[calc(100vh-22rem)]"> 
              <div className="p-1 space-y-4">
                <div id="shift-summary-printable-area-profile">
                  <CashierShiftSummary currentUser={currentUser} context="profile" />
                </div>
                <div className="flex justify-end print-button-container no-print">
                  <Button onClick={handlePrintShiftSummary}>
                    <Printer className="mr-2 h-4 w-4" /> Print Summary Statement
                  </Button>
                </div>
              </div>
            </ScrollArea>
          </TabsContent>
        )}
        {showExpressSettings && (
          <TabsContent value="express_settings">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center"><Zap className="h-5 w-5 mr-2" />Express Checkout Settings</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center space-x-2">
                  <Switch 
                    id="auto-enter" 
                    checked={currentUser?.autoEnterAfterScan}
                    onCheckedChange={handleAutoEnterChange}
                  />
                  <Label htmlFor="auto-enter">
                    Automatically submit after barcode scan
                  </Label>
                </div>
                <p className="text-sm text-muted-foreground mt-2">
                  When enabled, searches immediately after scanning. Disable to require manual 'Enter' press.
                </p>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
