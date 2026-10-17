
'use client';

import { useState, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import type { CommissionSetting } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/hooks/use-toast';
import { Target, Save, Info, ShieldAlert, Percent } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

export default function AdminCommissionSettingsPage() {
  const { commissionSetting: initialCommissionSetting, updateCommissionSetting, hasPermission } = useApp();
  const { toast } = useToast();

  const [salesTarget, setSalesTarget] = useState<number>(0);
  const [commissionInterval, setCommissionInterval] = useState<number>(0);
  const [commissionPercentage, setCommissionPercentage] = useState<number>(0);
  const [isActive, setIsActive] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState(false);

  const canManageSettings = hasPermission('manage_settings');

  useEffect(() => {
    if (initialCommissionSetting) {
      setSalesTarget(initialCommissionSetting.salesTarget);
      setCommissionInterval(initialCommissionSetting.commissionInterval);
      setCommissionPercentage(initialCommissionSetting.commissionPercentage);
      setIsActive(initialCommissionSetting.isActive);
    } else {
      setSalesTarget(5000); 
      setCommissionInterval(1000);
      setCommissionPercentage(2);
      setIsActive(false);
    }
  }, [initialCommissionSetting]);

  const handleSubmit = async () => {
    if (!canManageSettings) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to update settings.', variant: 'destructive' });
      return;
    }
    setIsLoading(true);
    if (salesTarget < 0) {
      toast({ title: 'Invalid Sales Target', description: 'Sales target must be a non-negative number.', variant: 'destructive' });
      setIsLoading(false);
      return;
    }
    if (commissionInterval <= 0) {
      toast({ title: 'Invalid Commission Interval', description: 'Commission interval must be a positive number.', variant: 'destructive' });
      setIsLoading(false);
      return;
    }
    if (commissionPercentage < 0 || commissionPercentage > 100) {
      toast({ title: 'Invalid Commission Percentage', description: 'Commission percentage must be between 0 and 100.', variant: 'destructive' });
      setIsLoading(false);
      return;
    }

    const newSetting: CommissionSetting = {
      id: initialCommissionSetting?.id || 'global_commission_rules', 
      salesTarget,
      commissionInterval,
      commissionPercentage,
      isActive,
    };

    try {
      await updateCommissionSetting(newSetting);
      toast({
        title: 'Commission Settings Updated',
        description: 'The commission rules have been saved successfully.',
        className: 'bg-accent text-accent-foreground border-accent'
      });
    } catch (error) {
      console.error("Error updating commission settings:", error);
      toast({
        title: 'Update Failed',
        description: 'Could not save commission settings.',
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
        <p className="text-muted-foreground">You do not have permission to manage commission settings.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Target className="mr-2 h-7 w-7 text-primary" /> Sales Commission Configuration
          </CardTitle>
          <CardDescription>
            Set up target-based commission rules for salespeople.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[calc(100vh-22rem)] p-1"> {/* Adjusted height and added padding to scroll area child if needed */}
            <div className="space-y-8 pr-4"> {/* Add padding to content if ScrollArea itself has p-0 */}
              <Card className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="space-y-2">
                    <Label htmlFor="sales-target">Sales Target (OMR)</Label>
                    <Input
                      id="sales-target"
                      type="number"
                      value={salesTarget}
                      onChange={(e) => setSalesTarget(parseFloat(e.target.value) || 0)}
                      min="0"
                      step="100"
                      placeholder="e.g., 5000"
                      disabled={isLoading || !canManageSettings}
                    />
                    <p className="text-xs text-muted-foreground">Sales amount a salesperson must reach before commission applies.</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="commission-interval">Commission Interval (OMR)</Label>
                    <Input
                      id="commission-interval"
                      type="number"
                      value={commissionInterval}
                      onChange={(e) => setCommissionInterval(parseFloat(e.target.value) || 0)}
                      min="1"
                      step="100"
                      placeholder="e.g., 1000"
                      disabled={isLoading || !canManageSettings}
                    />
                    <p className="text-xs text-muted-foreground">Commission is calculated for every full interval reached above the target.</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="commission-percentage" className="flex items-center">Commission Rate <Percent className="h-3 w-3 ml-1"/></Label>
                    <Input
                      id="commission-percentage"
                      type="number"
                      value={commissionPercentage}
                      onChange={(e) => setCommissionPercentage(parseFloat(e.target.value) || 0)}
                      min="0"
                      max="100"
                      step="0.1"
                      placeholder="e.g., 2 for 2%"
                      disabled={isLoading || !canManageSettings}
                    />
                    <p className="text-xs text-muted-foreground">Percentage applied to each commission interval.</p>
                  </div>
                </div>
              </Card>
              
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="is-active" className="text-lg font-semibold">Activate Commission System</Label>
                    <p className="text-sm text-muted-foreground">
                      Enable this to apply the commission rules.
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
                  <Save className="mr-2 h-5 w-5" /> {isLoading ? 'Saving...' : 'Save Commission Settings'}
                </Button>
              </div>
              
              <Card className="mt-6 border-dashed border-primary/50">
                <CardHeader className="flex flex-row items-center gap-2">
                  <Info className="h-5 w-5 text-primary" />
                  <CardTitle className="text-lg">How Commission Works</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground space-y-1">
                  <p>When activated, commission is calculated for salespeople based on their attributed sales (their share of 'paid' or 'completed' orders).</p>
                  <p>If a salesperson's total attributed sales for a period exceed the <span className="font-semibold">Sales Target</span>, they become eligible for commission.</p>
                  <p>Commission is earned for each full <span className="font-semibold">Commission Interval</span> of sales achieved above the target. The <span className="font-semibold">Commission Rate</span> is applied to the value of each such interval.</p>
                  <p>Example: Target 5000, Interval 1000, Rate 2%. If attributed sales are 7800:
                    <br/>- Sales above target = 2800.
                    <br/>- Full 1000 intervals = floor(2800/1000) = 2.
                    <br/>- Commission = 2 * (1000 * 2%) = 40 OMR.
                  </p>
                </CardContent>
              </Card>
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
