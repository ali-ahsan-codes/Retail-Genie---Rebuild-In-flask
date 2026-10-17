
'use client';

import type { User, AttendanceLog, BreakLog } from '@/types';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogClose } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import SelfieImageDisplay from '@/components/shared/SelfieImageDisplay'; // Import the new component
import { format, intervalToDuration, parseISO, isValid } from 'date-fns';
import { X, Camera, Coffee, UserCircle } from 'lucide-react';

interface UserActivityLogsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  user: User;
  attendanceLogs: AttendanceLog[];
  breakLogs: BreakLog[];
}

export default function UserActivityLogsDialog({ isOpen, onClose, user, attendanceLogs, breakLogs }: UserActivityLogsDialogProps) {
  
  const formatDuration = (duration: Duration | null | undefined): string => {
    if (!duration) return '-';
    const { hours = 0, minutes = 0, seconds = 0 } = duration;
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-2xl p-0">
        <DialogHeader className="p-6 pb-0">
          <DialogTitle className="text-xl flex items-center">
            <UserCircle className="mr-2 h-6 w-6 text-primary" /> Activity Logs for {user.username}
            </DialogTitle>
        </DialogHeader>
        <div className="p-6">
        <Tabs defaultValue="attendance" className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-4">
            <TabsTrigger value="attendance">Attendance</TabsTrigger>
            <TabsTrigger value="breaks">Breaks</TabsTrigger>
          </TabsList>
          <TabsContent value="attendance">
            <CardWithLogs title="Attendance Logs" icon={<Camera className="mr-2 h-5 w-5" />} logsEmpty={attendanceLogs.length === 0}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date & Time</TableHead>
                    <TableHead>Method</TableHead>
                    <TableHead>Selfie</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {attendanceLogs.map(log => (
                    <TableRow key={log.id}>
                      <TableCell>{isValid(parseISO(log.timestamp)) ? format(parseISO(log.timestamp), 'MM/dd/yyyy p') : 'Invalid Date'}</TableCell>
                      <TableCell className="capitalize">{log.method || '-'}</TableCell>
                      <TableCell>
                        {log.method === 'selfie' ? (
                          <SelfieImageDisplay 
                            src={log.selfieImagePath || log.selfieDataUri}
                            alt={`Selfie for attendance ${log.id}`}
                            width={64}
                            height={64}
                            className="rounded-md object-cover aspect-square"
                          />
                        ) : (
                          '-'
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardWithLogs>
          </TabsContent>
          <TabsContent value="breaks">
             <CardWithLogs title="Break Logs" icon={<Coffee className="mr-2 h-5 w-5" />} logsEmpty={breakLogs.length === 0}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Start Time</TableHead>
                    <TableHead>End Time</TableHead>
                    <TableHead className="text-right">Duration</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {breakLogs.map(log => (
                    <TableRow key={log.id}>
                      <TableCell>{isValid(parseISO(log.startTime)) ? format(parseISO(log.startTime), 'MM/dd/yyyy p') : 'Invalid Date'}</TableCell>
                      <TableCell>{log.endTime && isValid(parseISO(log.endTime)) ? format(parseISO(log.endTime), 'MM/dd/yyyy p') : 'Ongoing'}</TableCell>
                      <TableCell className="text-right">
                        {log.durationMs ? formatDuration(intervalToDuration({ start: 0, end: log.durationMs })) : (log.endTime ? '-' : 'In Progress')}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
             </CardWithLogs>
          </TabsContent>
        </Tabs>
        </div>
        <div className="px-6 pb-6 flex justify-end">
            <DialogClose asChild>
                <Button variant="outline"><X className="mr-2 h-4 w-4" />Close</Button>
            </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface CardWithLogsProps {
    title: string;
    icon: React.ReactNode;
    logsEmpty: boolean;
    children: React.ReactNode;
}

const CardWithLogs: React.FC<CardWithLogsProps> = ({ title, icon, logsEmpty, children }) => (
    <div className="border rounded-lg shadow-sm">
        <div className="flex items-center p-3 border-b">
            {icon}
            <h3 className="text-md font-semibold">{title}</h3>
        </div>
        {logsEmpty ? (
            <p className="p-4 text-sm text-muted-foreground">No logs found.</p>
        ) : (
            <ScrollArea className="h-[300px]">
                <div className="p-0">{children}</div>
            </ScrollArea>
        )}
    </div>
);
