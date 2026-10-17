
'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Timer, PlayCircle, PauseCircle, Users, Coffee, Info } from 'lucide-react'; // Added Users, Coffee, Info
import { format, intervalToDuration, isValid, parseISO } from 'date-fns';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';
import { formatDuration as formatDurationUtil } from '@/lib/utils'; // Import the utility

const isValidDateObj = (date: Date): boolean => isValid(date) && !isNaN(date.getTime());

export default function BreakManager() {
  const {
    currentUser,
    startBreak,
    endBreak,
    getCurrentBreakForUser,
    getBreakLogsForUser,
    breakLogs: contextBreakLogs,
    users,
  } = useApp();
  const { toast } = useToast();

  const [currentBreak, setCurrentBreak] = useState(currentUser ? getCurrentBreakForUser(currentUser.id) : undefined);
  const [userBreakLogs, setUserBreakLogs] = useState(currentUser ? getBreakLogsForUser(currentUser.id) : []);
  const [currentTime, setCurrentTime] = useState(new Date()); // For live duration update

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (currentUser) {
      setCurrentBreak(getCurrentBreakForUser(currentUser.id));
      setUserBreakLogs(getBreakLogsForUser(currentUser.id));
    }
  }, [currentUser, getCurrentBreakForUser, getBreakLogsForUser, contextBreakLogs]);

  const activeBreaksForAllUsers = useMemo(() => {
    return contextBreakLogs
      .filter(b => !b.endTime && b.startTime && isValid(parseISO(b.startTime)))
      .map(b => {
        const user = users.find(u => u.id === b.userId);
        const startTimeDate = parseISO(b.startTime);
        const durationMs = currentTime.getTime() - startTimeDate.getTime();
        return {
          ...b,
          userName: user?.username || 'Unknown User',
          durationDisplay: formatDurationUtil(durationMs),
        };
      })
      .sort((a, b) => parseISO(b.startTime).getTime() - parseISO(a.startTime).getTime());
  }, [contextBreakLogs, users, currentTime]);

  const displayedDurationString = useMemo(() => {
    if (currentBreak && !currentBreak.endTime && currentBreak.startTime) {
      const startDate = parseISO(currentBreak.startTime);
      if (isValid(startDate)) {
        const ms = currentTime.getTime() - startDate.getTime();
        return formatDurationUtil(ms);
      }
      return 'Error';
    } else if (currentBreak && currentBreak.endTime && typeof currentBreak.durationMs === 'number') {
      return formatDurationUtil(currentBreak.durationMs);
    }
    return '0s';
  }, [currentBreak, currentTime]);

  const handleStartBreak = async () => {
    if (!currentUser) return;
    const newBreak = await startBreak(currentUser.id);
    if (newBreak) {
      toast({ title: 'Break Started', description: 'Enjoy your break!', className: 'bg-primary/10 border-primary/20' });
    }
  };

  const handleEndBreak = async () => {
    if (!currentUser || !currentBreak) return;
    const endedBreak = await endBreak(currentUser.id);
    if (endedBreak) {
      toast({ title: 'Break Ended', description: 'Welcome back!', className: 'bg-accent text-accent-foreground border-accent' });
    }
  };

  const userStatus = currentBreak && !currentBreak.endTime ? 'On Break' : 'Online';

  return (
    <Card className="shadow-lg">
      <CardHeader>
        <CardTitle className="text-xl flex items-center">
          <Timer className="mr-2 h-6 w-6 text-primary" /> Break Time Management
        </CardTitle>
        <CardDescription>Manage your break sessions for the day. Coordinate with your team.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="text-center p-6 bg-muted/50 rounded-md border">
          <p className="text-lg font-semibold">Current Status:
            <span className={userStatus === 'On Break' ? 'text-orange-500' : 'text-green-600'}> {userStatus}</span>
          </p>
          {currentBreak && !currentBreak.endTime && currentBreak.startTime && (() => {
            const startDate = parseISO(currentBreak.startTime);
            if (!isValid(startDate)) {
              return <p className="text-sm text-muted-foreground text-destructive">Error: Invalid break start time data.</p>;
            }
            return (
              <>
                <p className="text-2xl font-mono my-2">{displayedDurationString}</p>
                <p className="text-sm text-muted-foreground">
                  Break started at: {format(startDate, 'p')}
                </p>
              </>
            );
          })()}
        </div>

        <Card className="border-blue-200 bg-blue-50/70">
            <CardHeader className="pb-3 pt-4">
                <CardTitle className="text-md flex items-center text-blue-700"><Coffee className="mr-2 h-5 w-5"/>Currently On Break ({activeBreaksForAllUsers.length})</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 pb-4">
            {activeBreaksForAllUsers.length === 0 ? (
                <p className="text-sm text-blue-600">No one is currently on break. Great time to take yours!</p>
            ) : (
                <ScrollArea className="h-28">
                    <ul className="space-y-1 text-sm">
                        {activeBreaksForAllUsers.map(b => (
                            <li key={b.id} className="flex justify-between items-center text-blue-700">
                                <span className="flex items-center"><Users className="w-3 h-3 mr-1.5"/>{b.userName}</span>
                                <span className="font-mono text-xs bg-blue-100 px-1.5 py-0.5 rounded">{b.durationDisplay}</span>
                            </li>
                        ))}
                    </ul>
                </ScrollArea>
            )}
            </CardContent>
        </Card>
         <Alert variant="default" className="border-sky-300 bg-sky-50 text-sky-700">
            <Info className="h-5 w-5 text-sky-600" />
            <UITitle className="text-sky-800">Team Coordination</UITitle>
            <UIDescription className="text-sky-700 text-xs">
                Please check who is currently on break before starting yours to ensure adequate coverage.
            </UIDescription>
        </Alert>

        <div className="flex gap-4">
          {!currentBreak || currentBreak.endTime ? (
            <Button
              onClick={handleStartBreak}
              className="flex-1 h-12 text-lg"
              disabled={!currentUser}
            >
              <PlayCircle className="mr-2 h-5 w-5" /> Start Break
            </Button>
          ) : (
            <Button onClick={handleEndBreak} className="flex-1 h-12 text-lg bg-accent hover:bg-accent/90 text-accent-foreground" disabled={!currentUser}>
              <PauseCircle className="mr-2 h-5 w-5" /> End Break
            </Button>
          )}
        </div>

        {userBreakLogs.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-md font-semibold">Today's Breaks:</h3>
            <ScrollArea className="max-h-60 border rounded-md bg-background">
              <ul className="space-y-2 p-3">
                {userBreakLogs
                  .filter(log => {
                    if (!log.startTime) return false;
                    const logStartDate = parseISO(log.startTime);
                    return isValid(logStartDate) && format(logStartDate, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd');
                  })
                  .map(log => {
                    const logStartDate = parseISO(log.startTime);
                    const logEndDate = log.endTime ? parseISO(log.endTime) : null;

                    return (
                      <li key={log.id} className="p-2 border-b text-sm text-muted-foreground">
                        <div className="flex justify-between items-center">
                          <span>
                            {format(logStartDate, 'p')}{' '}
                            -{' '}
                            {logEndDate && isValid(logEndDate) ? format(logEndDate, 'p') : 'Ongoing'}
                          </span>
                          {log.durationMs && (
                            <span className="font-medium text-foreground">
                              {formatDurationUtil(log.durationMs)}
                            </span>
                          )}
                        </div>
                      </li>
                    );
                })}
                {userBreakLogs.filter(log => {
                    if (!log.startTime) return false;
                    const logStartDate = parseISO(log.startTime);
                    return isValid(logStartDate) && format(logStartDate, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd');
                  }).length === 0 && (
                  <li className="p-2 text-sm text-muted-foreground text-center">No breaks taken today.</li>
                )}
              </ul>
            </ScrollArea>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
