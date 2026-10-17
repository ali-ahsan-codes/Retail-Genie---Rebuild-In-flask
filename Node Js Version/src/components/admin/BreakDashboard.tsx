
'use client';
import { useApp } from '@/context/AppContext';
import { formatDuration } from '@/lib/utils';
import { Clock, User as UserIcon, AlertCircle } from 'lucide-react'; // Changed User to UserIcon to avoid conflict
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { format, parseISO } from 'date-fns';
import React, { useMemo, useState, useEffect } from 'react';

export default function BreakDashboard() {
  const { users, breakLogs } = useApp();
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const activeBreaks = useMemo(() => {
    return breakLogs
      .filter(b => !b.endTime && b.startTime)
      .map(b => {
        const user = users.find(u => u.id === b.userId);
        const startTimeDate = parseISO(b.startTime);
        const durationMs = currentTime.getTime() - startTimeDate.getTime();
        return {
          ...b,
          userName: user?.username || 'Unknown User',
          role: user?.role || 'N/A',
          durationDisplay: formatDuration(durationMs),
          startTimeDisplay: format(startTimeDate, 'p'),
        };
      })
      .sort((a, b) => parseISO(b.startTime).getTime() - parseISO(a.startTime).getTime());
  }, [breakLogs, users, currentTime]);

  return (
    <Card className="shadow-lg">
      <CardHeader>
        <CardTitle className="text-xl flex items-center">
          <Clock className="w-6 h-6 mr-2 text-primary" /> Current Active Breaks
        </CardTitle>
        <CardDescription>
          Overview of users currently on break. Last updated: {format(currentTime, 'PPpp')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {activeBreaks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
            <AlertCircle className="w-12 h-12 mb-4" />
            <p className="text-lg">No users are currently on break.</p>
          </div>
        ) : (
          <ScrollArea className="h-[calc(100vh-20rem)]">
            <div className="space-y-3 pr-2">
              {activeBreaks.map(breakItem => (
                <Card key={breakItem.id} className="p-4 border rounded-lg bg-background/70">
                  <div className="flex items-center gap-3">
                    <div className="bg-primary/10 text-primary p-2 rounded-full">
                      <UserIcon className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                      <div className="flex justify-between items-center">
                        <span className="font-semibold text-base">{breakItem.userName}</span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground capitalize">
                          {breakItem.role}
                        </span>
                      </div>
                      <div className="text-sm text-muted-foreground flex justify-between mt-1">
                        <span>Duration: <span className="font-mono text-foreground">{breakItem.durationDisplay}</span></span>
                        <span>Started: {breakItem.startTimeDisplay}</span>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </ScrollArea>
        )}
        <div className="mt-4 text-sm text-muted-foreground text-center border-t pt-3">
          <p>{activeBreaks.length} user(s) currently on break.</p>
        </div>
      </CardContent>
    </Card>
  );
}
