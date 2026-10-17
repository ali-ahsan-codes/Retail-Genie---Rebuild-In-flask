
'use client';

import { useState, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import type { GlobalDiscountSetting } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/hooks/use-toast';
import { Percent, CalendarDays, Save, Info, ShieldAlert } from 'lucide-react';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { format, parseISO } from 'date-fns';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';

export default function AdminGlobalDiscountPage() {
  const { globalDiscountSetting: initialGlobalDiscount, updateGlobalDiscountSetting, hasPermission } = useApp();
  const { toast } = useToast();

  const [percentage, setPercentage] = useState<number>(0);
  const [startDate, setStartDate] = useState<Date | undefined>(undefined);
  const [endDate, setEndDate] = useState<Date | undefined>(undefined);
  const [isActive, setIsActive] = useState<boolean>(false);
  const [description, setDescription] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  const canManageSettings = hasPermission('manage_settings');

  useEffect(() => {
    if (initialGlobalDiscount) {
      setPercentage(initialGlobalDiscount.percentage);
      setStartDate(initialGlobalDiscount.startDate ? parseISO(initialGlobalDiscount.startDate) : undefined);
      setEndDate(initialGlobalDiscount.endDate ? parseISO(initialGlobalDiscount.endDate) : undefined);
      setIsActive(initialGlobalDiscount.isActive);
      setDescription(initialGlobalDiscount.description || '');
    } else {
      setPercentage(0);
      setStartDate(undefined);
      setEndDate(undefined);
      setIsActive(false);
      setDescription('');
    }
  }, [initialGlobalDiscount]);

  const handleSubmit = async () => {
    if (!canManageSettings) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to update settings.', variant: 'destructive' });
      return;
    }
    setIsLoading(true);
    if (percentage < 0 || percentage > 100) {
      toast({ title: 'Invalid Percentage', description: 'Discount percentage must be between 0 and 100.', variant: 'destructive' });
      setIsLoading(false);
      return;
    }
    if (startDate && endDate && startDate > endDate) {
      toast({ title: 'Invalid Dates', description: 'Start date cannot be after end date.', variant: 'destructive' });
      setIsLoading(false);
      return;
    }

    const newSetting: GlobalDiscountSetting = {
      id: initialGlobalDiscount?.id || 'main_promo', 
      percentage,
      startDate: startDate ? startDate.toISOString() : null,
      endDate: endDate ? endDate.toISOString() : null,
      isActive,
      description,
    };

    try {
      await updateGlobalDiscountSetting(newSetting);
      toast({
        title: 'Global Discount Updated',
        description: 'The global discount settings have been saved.',
        className: 'bg-accent text-accent-foreground border-accent'
      });
    } catch (error) {
      console.error("Error updating global discount:", error);
      toast({
        title: 'Update Failed',
        description: 'Could not save global discount settings.',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (!canManageSettings && !hasPermission('view_admin_dashboard')) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage global discounts.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Percent className="mr-2 h-7 w-7 text-primary" /> Global Discount Configuration
          </CardTitle>
          <CardDescription>
            Set up a site-wide discount that applies automatically to new orders within the specified period.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[calc(100vh-22rem)] p-1">
            <div className="space-y-8 pr-4">
              <Card className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label htmlFor="discount-percentage">Discount Percentage (%)</Label>
                    <Input
                      id="discount-percentage"
                      type="number"
                      value={percentage}
                      onChange={(e) => setPercentage(parseFloat(e.target.value) || 0)}
                      min="0"
                      max="100"
                      step="0.01"
                      placeholder="e.g., 10 for 10%"
                      disabled={isLoading || !canManageSettings}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="discount-description">Discount Description (Optional)</Label>
                    <Input
                      id="discount-description"
                      type="text"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="e.g., Holiday Sale"
                      disabled={isLoading || !canManageSettings}
                    />
                  </div>
                </div>
              </Card>

              <Card className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label htmlFor="start-date">Start Date (Optional)</Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          id="start-date"
                          variant={"outline"}
                          className={cn(
                            "w-full justify-start text-left font-normal h-10",
                            !startDate && "text-muted-foreground"
                          )}
                          disabled={isLoading || !canManageSettings}
                        >
                          <CalendarDays className="mr-2 h-4 w-4" />
                          {startDate ? format(startDate, "PPP") : <span>Pick a start date</span>}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0">
                        <Calendar
                          mode="single"
                          selected={startDate}
                          onSelect={setStartDate}
                          initialFocus
                        />
                      </PopoverContent>
                    </Popover>
                    <p className="text-xs text-muted-foreground">Leave blank for discount to start immediately (if active).</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="end-date">End Date (Optional)</Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          id="end-date"
                          variant={"outline"}
                          className={cn(
                            "w-full justify-start text-left font-normal h-10",
                            !endDate && "text-muted-foreground"
                          )}
                          disabled={isLoading || !canManageSettings}
                        >
                          <CalendarDays className="mr-2 h-4 w-4" />
                          {endDate ? format(endDate, "PPP") : <span>Pick an end date</span>}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0">
                        <Calendar
                          mode="single"
                          selected={endDate}
                          onSelect={setEndDate}
                          disabled={(date) => startDate ? date < startDate : false}
                          initialFocus
                        />
                      </PopoverContent>
                    </Popover>
                    <p className="text-xs text-muted-foreground">Leave blank for discount to run indefinitely (if active).</p>
                  </div>
                </div>
              </Card>
              
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="is-active" className="text-lg font-semibold">Activate Global Discount</Label>
                    <p className="text-sm text-muted-foreground">
                      Enable this to apply the discount globally based on the dates configured.
                    </p>
                  </div>
                  <Switch
                    id="is-active"
                    checked={isActive}
                    onCheckedChange={setIsActive}
                    disabled={isLoading || !canManageSettings}
                  />
                </div>
              </Card>

              <div className="flex justify-end mt-6">
                <Button onClick={handleSubmit} className="h-11" disabled={isLoading || !canManageSettings}>
                  <Save className="mr-2 h-5 w-5" /> {isLoading ? 'Saving...' : 'Save Global Discount'}
                </Button>
              </div>
              
              <Card className="mt-6 border-dashed border-primary/50">
                <CardHeader className="flex flex-row items-center gap-2">
                  <Info className="h-5 w-5 text-primary" />
                  <CardTitle className="text-lg">How it Works</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground space-y-1">
                  <p>When activated, this discount will automatically apply to the subtotal of all new orders created by salespeople during the specified date range (if any).</p>
                  <p>The applied discount percentage will be stored with each order.</p>
                  <p>Cashiers will see this discount reflected when processing payments. This discount does not stack with manually entered discounts on the cashier screen but can be overridden by an admin editing an order directly.</p>
                </CardContent>
              </Card>
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
