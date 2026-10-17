
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { useApp } from '@/context/AppContext';
import { LogIn, KeyRound, User as UserIcon } from 'lucide-react';
import { getUserByUsernameFromDb, ApiError } from '@/lib/database'; 
import { brandingConfig } from '@/config/branding';
import TowerLoader from '@/components/layout/TowerLoader'; 

export default function LoginPage() {
  const router = useRouter();
  const { setCurrentUser } = useApp();
  const [username, setUsername] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async () => {
    if (!username || !password) {
      setError('Please enter your username and password.');
      return;
    }
    setIsLoading(true);
    setError('');

    try {
      const user = await getUserByUsernameFromDb(username.trim());

      if (user && user.password === password) { 
        setCurrentUser(user);
        if (user.role === 'admin' || user.role === 'manager') {
          router.push('/admin/dashboard'); 
        } else if (user.role === 'auditor') { 
          router.push('/auditor/audits');
        } else if (user.role === 'display') {
          router.push('/lcd-display');
        } else if (user.role === 'express') {
          router.push('/express');
        } else { 
          router.push(`/${user.role}/dashboard`);
        }
      } else {
        // This branch is for correct username but incorrect password
        setError('Invalid username or password.');
      }
    } catch (dbError) {
      // If the error is an ApiError with status 404, it means the username was not found.
      if (dbError instanceof ApiError && dbError.status === 404) {
        setError('Invalid username or password.');
      } else {
        // For other errors (e.g., network issues, server errors), show a generic message.
        console.error("Login DB error:", dbError);
        setError('An error occurred during login. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/10 via-background to-secondary/10 p-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <LogIn size={32} />
          </div>
          <CardTitle className="text-3xl font-bold">{brandingConfig.appName} Access</CardTitle>
          <CardDescription>Enter your username and password to proceed.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="username_login" className="text-base flex items-center">
              <UserIcon className="mr-2 h-5 w-5 text-muted-foreground" /> Username
            </Label>
            <Input
              id="username_login"
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                setError('');
              }}
              className="h-12 text-base"
              disabled={isLoading}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password_login" className="text-base flex items-center">
                <KeyRound className="mr-2 h-5 w-5 text-muted-foreground" /> Password
            </Label>
            <Input
                id="password_login"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => {
                    setPassword(e.target.value);
                    setError('');
                }}
                onKeyPress={(e) => { if (e.key === 'Enter' && !isLoading) handleLogin();}}
                className="h-12 text-base"
                disabled={isLoading}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
        <CardFooter>
          <Button
            onClick={handleLogin}
            className="w-full text-lg h-12"
            disabled={!username || !password || isLoading}
          >
            {isLoading ? (
              <div className="flex flex-col items-center">
                <TowerLoader />
                <span className="mt-2 text-xs">Logging in...</span>
              </div>
            ) : (
              <><LogIn className="mr-2 h-5 w-5" /> Login</>
            )}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
