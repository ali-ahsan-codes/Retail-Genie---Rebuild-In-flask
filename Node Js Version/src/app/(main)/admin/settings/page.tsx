
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '@/context/AppContext';
import type { TaxSetting, SeriesNumberSetting, AttendanceSetting, SeriesId } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/hooks/use-toast';
import { SlidersHorizontal, Save, ShieldAlert, Hash, ClockIcon, Users, Ticket, BookOpen, AlertCircle } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertTitle as AlertTitleComponent, AlertDescription as AlertDescriptionComponent } from '@/components/ui/alert';


export default function AdminSettingsPage() {
  const {
    taxSettings: initialTaxSettings,
    updateTaxSettings,
    seriesNumberSettings: initialSeriesSettings,
    updateSeriesNumberSettings,
    attendanceSetting: initialAttendanceSetting,
    updateAttendanceSetting,
    hasPermission
  } = useApp();
  const { toast } = useToast();

  const [currentTaxSettings, setCurrentTaxSettings] = useState<TaxSetting[]>([]);
  const [isLoadingTax, setIsLoadingTax] = useState(false);

  const [formNextInvoiceNumber, setFormNextInvoiceNumber] = useState<number>(1);
  const [formNextQuotationNumber, setFormNextQuotationNumber] = useState<number>(1);
  const [formNextDemandNoticeNumber, setFormNextDemandNoticeNumber] = useState<number>(1);
  const [isLoadingSeries, setIsLoadingSeries] = useState(false);

  const [formMandatoryTime, setFormMandatoryTime] = useState<string>("09:00");
  const [formIsMandatoryActive, setFormIsMandatoryActive] = useState<boolean>(false);
  const [formMaxConcurrentBreaks, setFormMaxConcurrentBreaks] = useState<string>('');
  const [isLoadingAttendance, setIsLoadingAttendance] = useState(false);

  const canManageSettings = hasPermission('manage_settings');

  useEffect(() => {
    setCurrentTaxSettings(JSON.parse(JSON.stringify(initialTaxSettings)));
  }, [initialTaxSettings]);

  useEffect(() => {
    setFormNextInvoiceNumber(initialSeriesSettings.invoice?.nextNumber || 1);
    setFormNextQuotationNumber(initialSeriesSettings.quotation?.nextNumber || 1);
    setFormNextDemandNoticeNumber(initialSeriesSettings.demand_notice?.nextNumber || 1);
  }, [initialSeriesSettings]);

  useEffect(() => {
    if (initialAttendanceSetting) {
      setFormMandatoryTime(initialAttendanceSetting.mandatory_attendance_time || "09:00");
      setFormIsMandatoryActive(initialAttendanceSetting.is_mandatory_attendance_active);
      setFormMaxConcurrentBreaks(initialAttendanceSetting.max_concurrent_breaks === null || initialAttendanceSetting.max_concurrent_breaks === undefined ? '' : String(initialAttendanceSetting.max_concurrent_breaks));
    } else {
      setFormMandatoryTime("09:00");
      setFormIsMandatoryActive(false);
      setFormMaxConcurrentBreaks('');
    }
  }, [initialAttendanceSetting]);


  const handleRateChange = (id: string, newRate: string) => {
    const rateValue = parseFloat(newRate);
    if (isNaN(rateValue) && newRate !== '') {
        return;
    }
    setCurrentTaxSettings(prevSettings =>
      prevSettings.map(setting =>
        setting.id === id ? { ...setting, rate: isNaN(rateValue) ? 0 : rateValue / 100 } : setting
      )
    );
  };

  const handleEnabledChange = (id: string, checked: boolean) => {
    setCurrentTaxSettings(prevSettings =>
      prevSettings.map(setting =>
        setting.id === id ? { ...setting, enabled: checked } : setting
      )
    );
  };

  const handleTaxSubmit = async () => {
    if (!canManageSettings) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to update settings.', variant: 'destructive' });
      return;
    }
    setIsLoadingTax(true);
    try {
      const isValid = currentTaxSettings.every(setting => typeof setting.rate === 'number' && setting.rate >= 0 && setting.rate <= 1);
      if (!isValid) {
        toast({
          title: 'Invalid Tax Rate',
          description: 'Please ensure all tax rates are valid percentages between 0 and 100.',
          variant: 'destructive',
        });
        setIsLoadingTax(false);
        return;
      }

      await updateTaxSettings(currentTaxSettings);
      toast({
        title: 'Tax Settings Updated',
        description: 'Tax rates and statuses have been saved successfully.',
        className: 'bg-accent text-accent-foreground border-accent'
      });
    } catch (error) {
      console.error("Error updating tax settings:", error);
      toast({
        title: 'Update Failed',
        description: 'Could not save tax settings. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsLoadingTax(false);
    }
  };

  const handleSeriesSettingSubmit = async (seriesId: SeriesId, nextNumber: number) => {
    if (!canManageSettings) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to update document numbering.', variant: 'destructive' });
      return;
    }
    if (nextNumber < 1 || nextNumber > 99999999) {
      toast({ title: 'Invalid Number', description: `Next ${seriesId} Number must be a positive integer (1-99,999,999).`, variant: 'destructive' });
      return;
    }

    setIsLoadingSeries(true);
    try {
      await updateSeriesNumberSettings({ id: seriesId, nextNumber });
      toast({
        title: `${seriesId.charAt(0).toUpperCase() + seriesId.slice(1)} Number Settings Updated`,
        description: `Next ${seriesId} number configuration has been saved.`,
        className: 'bg-accent text-accent-foreground border-accent'
      });
    } catch (error) {
      console.error(`Error updating ${seriesId} settings:`, error);
      toast({
        title: 'Update Failed',
        description: `Could not save ${seriesId} number settings.`,
        variant: 'destructive',
      });
    } finally {
      setIsLoadingSeries(false);
    }
  };

  const handleAttendanceSettingSubmit = async () => {
    if (!canManageSettings) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to update attendance settings.', variant: 'destructive' });
      return;
    }
    if (!/^(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$/.test(formMandatoryTime) && formIsMandatoryActive) {
        toast({ title: 'Invalid Time', description: 'Please enter a valid time in HH:MM format if mandatory attendance is active.', variant: 'destructive' });
        return;
    }
    
    let maxBreaks: number | null = null;
    if (formMaxConcurrentBreaks.trim() !== '') {
        const parsedMaxBreaks = parseInt(formMaxConcurrentBreaks, 10);
        if (isNaN(parsedMaxBreaks) || parsedMaxBreaks < 0) {
            toast({ title: 'Invalid Max Breaks', description: 'Maximum concurrent breaks must be a non-negative whole number or blank (for no limit).', variant: 'destructive' });
            return;
        }
        maxBreaks = parsedMaxBreaks;
    }


    setIsLoadingAttendance(true);
    try {
      const newSetting: AttendanceSetting = {
        id: initialAttendanceSetting?.id || 'global_attendance_config',
        mandatory_attendance_time: formIsMandatoryActive ? formMandatoryTime : null,
        is_mandatory_attendance_active: formIsMandatoryActive,
        max_concurrent_breaks: maxBreaks,
      };
      await updateAttendanceSetting(newSetting);
      toast({
        title: 'Attendance Settings Updated',
        description: 'Mandatory attendance and break rules have been saved.',
        className: 'bg-accent text-accent-foreground border-accent'
      });
    } catch (error) {
      console.error("Error updating attendance settings:", error);
      toast({
        title: 'Update Failed',
        description: 'Could not save attendance settings.',
        variant: 'destructive',
      });
    } finally {
      setIsLoadingAttendance(false);
    }
  };


  if (!canManageSettings && !hasPermission('view_admin_dashboard')) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage application settings.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
        <Card className="shadow-md">
            <CardHeader>
                <CardTitle className="text-2xl flex items-center">
                    <SlidersHorizontal className="mr-2 h-7 w-7 text-primary" /> Application Settings
                </CardTitle>
                <CardDescription>Manage tax rates, document numbering, and attendance/break rules.</CardDescription>
            </CardHeader>
        </Card>

        <Tabs defaultValue="tax_settings" className="w-full">
            <TabsList className="grid w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3">
                <TabsTrigger value="tax_settings">Tax Config</TabsTrigger>
                <TabsTrigger value="doc_numbering_settings">Document Numbering</TabsTrigger>
                <TabsTrigger value="attendance_settings">Attendance & Breaks</TabsTrigger>
            </TabsList>

            <TabsContent value="tax_settings" className="mt-4">
                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle>Tax Rates & Statuses</CardTitle>
                        <CardDescription>Set up tax rates (e.g., GST, Service Tax) and enable/disable them.</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ScrollArea className="h-[calc(100vh-26rem)] p-1">
                        <div className="space-y-8 pr-4">
                          {currentTaxSettings.length === 0 && canManageSettings ? (
                              <p>Loading tax settings or no tax settings configured...</p>
                          ) : (
                              currentTaxSettings.map(setting => (
                                  <Card key={setting.id} className="p-4">
                                  <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                                      <div className="flex-grow">
                                      <Label htmlFor={`rate-${setting.id}`} className="text-lg font-semibold">{setting.name}</Label>
                                      <p className="text-sm text-muted-foreground">
                                          Set the percentage for {setting.name}.
                                      </p>
                                      </div>
                                      <div className="flex items-center gap-4">
                                      <Input
                                          id={`rate-${setting.id}`}
                                          type="number"
                                          value={(setting.rate * 100).toString()}
                                          onChange={(e) => handleRateChange(setting.id, e.target.value)}
                                          className="w-24 h-10 text-right"
                                          placeholder="e.g., 5 for 5%"
                                          min="0"
                                          max="100"
                                          step="0.01"
                                          disabled={isLoadingTax || !canManageSettings}
                                      />
                                      <span className="text-lg text-muted-foreground">%</span>
                                      <div className="flex items-center space-x-2">
                                          <Switch
                                              id={`enabled-${setting.id}`}
                                              checked={setting.enabled}
                                              onCheckedChange={(checked) => handleEnabledChange(setting.id, checked)}
                                              disabled={isLoadingTax || !canManageSettings}
                                          />
                                          <Label htmlFor={`enabled-${setting.id}`} className="text-sm">
                                              {setting.enabled ? 'Enabled' : 'Disabled'}
                                          </Label>
                                          </div>
                                      </div>
                                  </div>
                                  </Card>
                              ))
                          )}
                          <div className="flex justify-end mt-6">
                              <Button onClick={handleTaxSubmit} className="h-11" disabled={isLoadingTax || !canManageSettings}>
                              <Save className="mr-2 h-5 w-5" /> {isLoadingTax ? 'Saving Taxes...' : 'Save Tax Settings'}
                              </Button>
                          </div>
                        </div>
                      </ScrollArea>
                    </CardContent>
                </Card>
            </TabsContent>

            <TabsContent value="doc_numbering_settings" className="mt-4">
                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle>Document Numbering Configuration</CardTitle>
                        <CardDescription>
                            Set the starting serial number for Invoices, Quotations, and Demand Notices.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ScrollArea className="h-[calc(100vh-26rem)] p-1">
                        <div className="space-y-6 pr-4">
                          
                          <Card className="p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Ticket className="h-5 w-5 text-primary"/>
                                <Label htmlFor="nextInvoiceNumber" className="text-md font-semibold">Invoice Numbering</Label>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
                                <Input
                                id="nextInvoiceNumber"
                                type="number"
                                value={formNextInvoiceNumber}
                                onChange={(e) => setFormNextInvoiceNumber(parseInt(e.target.value) || 1)}
                                min="1" placeholder="e.g., 1" disabled={isLoadingSeries || !canManageSettings}
                                />
                                <Button onClick={() => handleSeriesSettingSubmit('invoice', formNextInvoiceNumber)} className="h-10" disabled={isLoadingSeries || !canManageSettings}>
                                <Save className="mr-2 h-4 w-4" /> Set Next Invoice No.
                                </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-2">Current next system invoice number: {initialSeriesSettings.invoice?.nextNumber || 'N/A'}. Format: INV-000001</p>
                          </Card>
                          
                          <Card className="p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <BookOpen className="h-5 w-5 text-primary"/>
                                <Label htmlFor="nextQuotationNumber" className="text-md font-semibold">Quotation Numbering</Label>
                            </div>
                             <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
                                <Input
                                id="nextQuotationNumber"
                                type="number"
                                value={formNextQuotationNumber}
                                onChange={(e) => setFormNextQuotationNumber(parseInt(e.target.value) || 1)}
                                min="1" placeholder="e.g., 1" disabled={isLoadingSeries || !canManageSettings}
                                />
                                <Button onClick={() => handleSeriesSettingSubmit('quotation', formNextQuotationNumber)} className="h-10" disabled={isLoadingSeries || !canManageSettings}>
                                <Save className="mr-2 h-4 w-4" /> Set Next Quotation No.
                                </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-2">Current next system quotation number: {initialSeriesSettings.quotation?.nextNumber || 'N/A'}. Format: QUO-000001</p>
                          </Card>

                          <Card className="p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <AlertCircle className="h-5 w-5 text-primary"/>
                                <Label htmlFor="nextDemandNoticeNumber" className="text-md font-semibold">Demand Notice Numbering</Label>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
                                <Input
                                id="nextDemandNoticeNumber"
                                type="number"
                                value={formNextDemandNoticeNumber}
                                onChange={(e) => setFormNextDemandNoticeNumber(parseInt(e.target.value) || 1)}
                                min="1" placeholder="e.g., 1" disabled={isLoadingSeries || !canManageSettings}
                                />
                                <Button onClick={() => handleSeriesSettingSubmit('demand_notice', formNextDemandNoticeNumber)} className="h-10" disabled={isLoadingSeries || !canManageSettings}>
                                <Save className="mr-2 h-4 w-4" /> Set Next DN No.
                                </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-2">Current next system demand notice number: {initialSeriesSettings.demand_notice?.nextNumber || 'N/A'}. Format: DN-000001</p>
                          </Card>
                          
                          <Card className="mt-6 border-dashed border-primary/50">
                              <CardHeader className="flex flex-row items-center gap-2">
                                  <Hash className="h-5 w-5 text-primary" />
                                  <AlertTitleComponent>Document ID Formatting</AlertTitleComponent>
                              </CardHeader>
                              <AlertDescriptionComponent className="text-sm text-muted-foreground space-y-1 px-6 pb-4">
                                  <p>Document IDs are generated using a prefix (e.g., "INV-", "QUO-", "DN-") followed by a 6-digit number padded with leading zeros.</p>
                                  <p>Setting the "Next Number" here changes the starting point for subsequent documents of that type.</p>
                              </AlertDescriptionComponent>
                          </Card>
                        </div>
                      </ScrollArea>
                    </CardContent>
                </Card>
            </TabsContent>

            <TabsContent value="attendance_settings" className="mt-4">
                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle className="flex items-center"><ClockIcon className="mr-2 h-5 w-5 text-primary"/> Staff Attendance & Break Rules</CardTitle>
                        <CardDescription>
                            Configure mandatory attendance times and concurrent break limits.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ScrollArea className="h-[calc(100vh-26rem)] p-1">
                        <div className="space-y-6 pr-4">
                            <Card className="p-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                                    <div className="space-y-2">
                                        <Label htmlFor="mandatoryAttendanceTime">Mandatory Clock-in Time</Label>
                                        <Input
                                            id="mandatoryAttendanceTime"
                                            type="time"
                                            value={formMandatoryTime}
                                            onChange={(e) => setFormMandatoryTime(e.target.value)}
                                            className="h-10"
                                            disabled={isLoadingAttendance || !canManageSettings || !formIsMandatoryActive}
                                        />
                                        <p className="text-xs text-muted-foreground">Set the time (e.g., 09:00 AM) after which attendance is mandatory for applicable roles.</p>
                                    </div>
                                    <div className="flex items-center space-x-2 pt-6 md:pt-0">
                                        <Switch
                                            id="isMandatoryAttendanceActive"
                                            checked={formIsMandatoryActive}
                                            onCheckedChange={setFormIsMandatoryActive}
                                            disabled={isLoadingAttendance || !canManageSettings}
                                        />
                                        <Label htmlFor="isMandatoryAttendanceActive" className="text-sm font-medium">
                                            {formIsMandatoryActive ? 'Mandatory Attendance is Active' : 'Mandatory Attendance is Inactive'}
                                        </Label>
                                    </div>
                                </div>
                            </Card>
                            <Card className="p-4">
                                 <div className="space-y-2">
                                    <Label htmlFor="maxConcurrentBreaks" className="flex items-center"><Users className="mr-2 h-4 w-4 text-muted-foreground"/>Maximum Concurrent Breaks</Label>
                                    <Input
                                        id="maxConcurrentBreaks"
                                        type="number"
                                        value={formMaxConcurrentBreaks}
                                        onChange={(e) => setFormMaxConcurrentBreaks(e.target.value)}
                                        placeholder="Leave blank for no limit"
                                        min="0"
                                        step="1"
                                        className="h-10"
                                        disabled={isLoadingAttendance || !canManageSettings}
                                    />
                                    <p className="text-xs text-muted-foreground">Set the maximum number of staff allowed on break at the same time. Leave blank or set to a high number for no limit. Set to 0 to disallow breaks entirely.</p>
                                </div>
                            </Card>
                             <Alert variant="default" className="bg-blue-50 border-blue-200">
                                <ClockIcon className="h-5 w-5 text-blue-600" />
                                <AlertTitleComponent className="text-blue-700">How it Works</AlertTitleComponent>
                                <AlertDescriptionComponent className="text-blue-600 text-xs">
                                    If "Mandatory Attendance is Active", users in Sales, Storekeeper, and Logistics roles
                                    will be required to clock in via their profile page *after* the specified "Mandatory Clock-in Time"
                                    before they can perform core actions on their respective dashboards.
                                    <br/>
                                    The "Maximum Concurrent Breaks" limit applies to all users who can take breaks. If the number of active breaks reaches this limit, others cannot start a new break until someone returns.
                                </AlertDescriptionComponent>
                            </Alert>
                            <div className="flex justify-end mt-6">
                                <Button onClick={handleAttendanceSettingSubmit} className="h-11" disabled={isLoadingAttendance || !canManageSettings}>
                                <Save className="mr-2 h-5 w-5" /> {isLoadingAttendance ? 'Saving Rules...' : 'Save Attendance & Break Rules'}
                                </Button>
                            </div>
                        </div>
                      </ScrollArea>
                    </CardContent>
                </Card>
            </TabsContent>

        </Tabs>
    </div>
  );
}
