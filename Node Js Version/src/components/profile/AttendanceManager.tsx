
// src/components/profile/AttendanceManager.tsx
'use client';

import { useState, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import SelfieImageDisplay from '@/components/shared/SelfieImageDisplay';
import { Camera, CheckCircle, Clock, RotateCcw, Loader2 } from 'lucide-react'; 
import { captureAttendanceSelfie } from '@/lib/attendanceCameraUtils';
import { format, parseISO, isValid } from 'date-fns';
import type { AttendanceLog } from '@/types'; 

export default function AttendanceManager() {
  const { currentUser, addAttendanceLog, getTodayAttendanceForUser, loadDataFromDb, attendanceLogs: contextAttendanceLogs } = useApp();
  const { toast } = useToast();

  const [todayLog, setTodayLog] = useState<AttendanceLog | undefined>(() => currentUser ? getTodayAttendanceForUser(currentUser.id) : undefined);
  
  const [capturedSelfieDataUrl, setCapturedSelfieDataUrl] = useState<string | null>(null);
  const [showSelfieConfirmation, setShowSelfieConfirmation] = useState(false);
  const [isCapturingOrProcessing, setIsCapturingOrProcessing] = useState(false); 

  useEffect(() => {
    if (currentUser) {
      setTodayLog(getTodayAttendanceForUser(currentUser.id));
    }
  }, [currentUser, getTodayAttendanceForUser, contextAttendanceLogs]); 

  const markPresentWithMethod = async (method: 'button' | 'selfie', selfieData?: string) => {
    if (!currentUser) {
      toast({ title: 'Error', description: 'No user logged in.', variant: 'destructive' });
      return;
    }
    if (todayLog) {
      toast({ 
        title: 'Already Clocked In', 
        description: `You already clocked in today at ${isValid(parseISO(todayLog.timestamp)) ? format(parseISO(todayLog.timestamp), 'p') : 'Invalid Date'}.`, 
        variant: 'default' 
      });
      return;
    }

    setIsCapturingOrProcessing(true);
    try {
      const newLog = await addAttendanceLog(
        currentUser.id, 
        method, 
        method === 'selfie' ? selfieData : undefined
      );
      
      if (newLog) {
        toast({
          title: 'Attendance Recorded!',
          description: `Marked present via ${method} at ${isValid(parseISO(newLog.timestamp)) ? format(parseISO(newLog.timestamp), 'p') : 'Invalid Date'}.`,
          className: 'bg-accent text-accent-foreground border-accent',
        });
        setCapturedSelfieDataUrl(null); 
        setShowSelfieConfirmation(false);
        await loadDataFromDb({ isInitialLoad: false }); // Ensure data is refreshed
        setTodayLog(getTodayAttendanceForUser(currentUser.id)); // Re-fetch today's log
      }
    } catch (error) {
      toast({ 
        title: 'Clock-in Error', 
        description: error instanceof Error ? error.message : 'An unexpected error occurred.', 
        variant: 'destructive' 
      });
    } finally {
      setIsCapturingOrProcessing(false);
    }
  };

  const handleTakeSelfie = async () => {
    setIsCapturingOrProcessing(true);
    try {
      const dataUrl = await captureAttendanceSelfie(); // This directly returns dataUrl from the util
      setCapturedSelfieDataUrl(dataUrl);
      setShowSelfieConfirmation(true); 
    } catch (error) {
      toast({
        title: 'Camera Error',
        description: error instanceof Error ? error.message : 'Failed to capture selfie or capture cancelled.',
        variant: 'destructive'
      });
    } finally {
      setIsCapturingOrProcessing(false);
    }
  };

  const handleRetakeSelfie = () => {
    setCapturedSelfieDataUrl(null);
    setShowSelfieConfirmation(false);
  };

  const handleConfirmSelfieAndClockIn = () => {
    if (capturedSelfieDataUrl) {
      markPresentWithMethod('selfie', capturedSelfieDataUrl);
    } else {
      toast({ title: 'Error', description: 'No selfie available to confirm.', variant: 'destructive' });
    }
  };

  return (
    <Card className="shadow-lg">
      <CardHeader>
        <CardTitle className="text-xl flex items-center">
          <Clock className="mr-2 h-6 w-6 text-primary" /> Daily Attendance
        </CardTitle>
        <CardDescription>Clock in for the day. You can mark present or use a selfie.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {todayLog ? (
          <div className="text-center p-6 bg-green-50 rounded-md border border-green-200">
            <CheckCircle className="mx-auto h-12 w-12 text-green-600 mb-3" />
            <p className="text-lg font-semibold text-green-700">You are clocked in for today!</p>
            <p className="text-muted-foreground">
              Clocked in at: {isValid(parseISO(todayLog.timestamp)) ? format(parseISO(todayLog.timestamp), 'MM/dd/yyyy p') : 'Invalid Date'}
            </p>
            {todayLog.method === 'selfie' && (
              <div className="mt-4">
                <p className="text-sm font-medium mb-2">Your Clock-in Selfie:</p>
                <SelfieImageDisplay 
                  src={todayLog.selfieImagePath || todayLog.selfieDataUri} 
                  alt="Clock-in selfie"
                  width={150}
                  height={150}
                  className="rounded-md object-cover mx-auto shadow-md aspect-square"
                  placeholderText="Selfie Missing"
                />
              </div>
            )}
          </div>
        ) : (
          <>
            {!showSelfieConfirmation ? (
              <>
                <Button 
                  onClick={() => markPresentWithMethod('button')} 
                  className="w-full h-12 text-lg" 
                  disabled={!currentUser || isCapturingOrProcessing}
                >
                  Mark Present
                </Button>

                <div className="relative flex items-center">
                  <div className="flex-grow border-t border-muted"></div>
                  <span className="flex-shrink mx-4 text-muted-foreground text-xs">OR</span>
                  <div className="flex-grow border-t border-muted"></div>
                </div>
                
                <Button 
                  onClick={handleTakeSelfie}
                  variant="outline" 
                  className="w-full h-12 text-lg" 
                  disabled={!currentUser || isCapturingOrProcessing}
                >
                  {isCapturingOrProcessing ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : <Camera className="mr-2 h-5 w-5" />}
                  {isCapturingOrProcessing ? 'Processing...' : 'Take Selfie to Clock In'}
                </Button>
              </>
            ) : (
              // Selfie Confirmation Step
              capturedSelfieDataUrl && (
                <div className="mt-4 text-center space-y-4 p-4 border rounded-md bg-muted/20">
                  <p className="text-sm font-medium mb-2">Selfie Preview:</p>
                  <SelfieImageDisplay 
                      src={capturedSelfieDataUrl} // This is a dataURI
                      alt="Selfie preview for clock-in"
                      width={200}
                      height={200}
                      className="rounded-md object-cover mx-auto shadow-md aspect-square"
                  />
                  <div className="flex flex-col sm:flex-row gap-2 justify-center mt-3">
                    <Button variant="outline" onClick={handleRetakeSelfie} disabled={isCapturingOrProcessing}>
                      <RotateCcw className="mr-2 h-4 w-4" /> Retake Selfie
                    </Button>
                    <Button 
                      onClick={handleConfirmSelfieAndClockIn} 
                      className="bg-accent text-accent-foreground hover:bg-accent/90"
                      disabled={isCapturingOrProcessing}
                    >
                      {isCapturingOrProcessing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle className="mr-2 h-4 w-4" />}
                      Confirm & Clock In
                    </Button>
                  </div>
                </div>
              )
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
