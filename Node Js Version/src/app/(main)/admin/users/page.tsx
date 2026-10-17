
'use client';
import React, { useState, useCallback, useEffect } from 'react';
import type { User, UserRole, Permission } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogClose } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { PlusCircle, Edit, Trash2, MoreHorizontal, Search, Users2, Eye, History, ShieldCheck, ShieldAlert } from 'lucide-react';
import UserForm from '@/components/admin/UserForm';
import { useToast } from '@/hooks/use-toast';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import UserActivityLogsDialog from '@/components/admin/UserActivityLogsDialog';
import { addUserToDb, updateUserInDb, deleteUserFromDb } from '@/lib/database';
import type * as z from "zod"; // For UserFormValues type

interface MemoizedUserAdminRowProps {
  user: User;
  adminUser: User | null;
  onEdit: (user: User) => void;
  onDelete: (userId: string) => void;
  onViewLogs: (user: User) => void;
  isSubmitting: boolean;
  canManageUsers: boolean;
  getRoleBadgeVariant: (role: UserRole) => "default" | "secondary" | "destructive" | "outline";
}

const MemoizedUserAdminRow = React.memo(function MemoizedUserAdminRow({
  user, adminUser, onEdit, onDelete, onViewLogs, isSubmitting, canManageUsers, getRoleBadgeVariant
}: MemoizedUserAdminRowProps) {
  return (
    <TableRow>
      <TableCell className="font-medium">{user.username}</TableCell>
      <TableCell>
        <Badge variant={getRoleBadgeVariant(user.role)} className="capitalize">
          {user.role}
        </Badge>
      </TableCell>
      <TableCell>
        {user.role === 'admin' ? (
          <Badge variant="outline" className="border-green-500 text-green-600">All Permissions</Badge>
        ) : user.role === 'manager' && user.permissions && user.permissions.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="link" className="p-0 h-auto text-xs text-muted-foreground hover:text-primary">
                  {user.permissions.length} permission(s) <MoreHorizontal className="ml-1 h-3 w-3"/>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-48 overflow-y-auto">
              <DropdownMenuLabel className="flex items-center"><ShieldCheck className="mr-2 h-4 w-4 text-primary"/>Granted Permissions</DropdownMenuLabel>
              <DropdownMenuSeparator/>
              {user.permissions.map(p => (
                  <DropdownMenuItem key={p} disabled className="text-xs capitalize cursor-default">{p.replace(/_/g, ' ')}</DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : user.role === 'manager' ? (
          <span className="text-xs text-muted-foreground">No specific permissions</span>
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
        )}
      </TableCell>
      <TableCell>
        {canManageUsers && (
            <AlertDialog>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-8 w-8 p-0" disabled={isSubmitting}>
                    <span className="sr-only">Open menu</span>
                    <MoreHorizontal className="h-4 w-4" />
                </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                <DropdownMenuLabel>Actions</DropdownMenuLabel>
                <DropdownMenuItem onClick={() => onEdit(user)} disabled={isSubmitting || (user.role === 'admin' && user.id !== adminUser?.id)}>
                    <Edit className="mr-2 h-4 w-4" /> Edit User
                </DropdownMenuItem>
                {(user.role !== 'admin' && user.role !== 'manager') && (
                <DropdownMenuItem onClick={() => onViewLogs(user)} disabled={isSubmitting}>
                    <History className="mr-2 h-4 w-4" /> View Activity Logs
                </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <AlertDialogTrigger asChild>
                    <DropdownMenuItem
                        className="text-destructive focus:text-destructive focus:bg-destructive/10"
                        disabled={adminUser?.id === user.id || isSubmitting || (user.role === 'admin' && user.id !== adminUser?.id)}
                    >
                        <Trash2 className="mr-2 h-4 w-4" /> Delete User
                    </DropdownMenuItem>
                </AlertDialogTrigger>
                </DropdownMenuContent>
            </DropdownMenu>
                <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                    <AlertDialogDescription>
                    This action cannot be undone. This will permanently delete the user account for "{user.username}".
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel disabled={isSubmitting}>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => onDelete(user.id)} className="bg-destructive hover:bg-destructive/90" disabled={isSubmitting}>
                    {isSubmitting ? "Deleting..." : "Delete User"}
                    </AlertDialogAction>
                </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        )}
      </TableCell>
    </TableRow>
  );
});
MemoizedUserAdminRow.displayName = 'MemoizedUserAdminRow';


// Define the type for the data coming from UserForm
type UserFormData = Omit<User, 'id' | 'activeBreakId'> & { id?: string; permissions?: string[], password?: string };


export default function AdminUsersPage() {
  const { users: contextUsers, currentUser: adminUser, loadDataFromDb, getAttendanceLogsForUser, getBreakLogsForUser, hasPermission, isDataLoaded } = useApp();
  const { toast } = useToast();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [viewingLogsUser, setViewingLogsUser] = useState<User | null>(null);
  const [isLogsDialogOpen, setIsLogsDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [localUsers, setLocalUsers] = useState<User[]>([]);

  useEffect(() => {
    const uniqueContextUsers = Array.from(new Map(contextUsers.map(item => [item.id, item])).values());
    setLocalUsers(uniqueContextUsers);
  }, [contextUsers]);

  const canManageUsers = hasPermission('manage_users');

  const handleAddUser = useCallback(() => {
    if (!canManageUsers) {
        toast({ title: "Permission Denied", description: "You do not have permission to add users.", variant: "destructive"});
        return;
    }
    setEditingUser(null);
    setIsFormOpen(true);
  }, [canManageUsers, toast]);

  const handleEditUser = useCallback((user: User) => {
    if (!canManageUsers) {
        toast({ title: "Permission Denied", description: "You do not have permission to edit users.", variant: "destructive"});
        return;
    }
    setEditingUser(user);
    setIsFormOpen(true);
  }, [canManageUsers, toast]);

  const handleDeleteUser = useCallback(async (userId: string) => {
    if (!canManageUsers) {
        toast({ title: "Permission Denied", description: "You do not have permission to delete users.", variant: "destructive"});
        return;
    }
    if (adminUser && userId === adminUser.id) {
      toast({ title: 'Action Denied', description: 'You cannot delete your own account.', variant: 'destructive' });
      return;
    }
    const userToDelete = localUsers.find(u => u.id === userId);
    if (userToDelete && userToDelete.role === 'admin' && userToDelete.id !== adminUser?.id) {
        toast({ title: 'Action Denied', description: 'Cannot delete another admin account.', variant: 'destructive' });
        return;
    }

    setIsSubmitting(true);
    try {
      await deleteUserFromDb(userId);
      await loadDataFromDb();
      toast({ title: 'User Deleted', description: 'The user account has been removed.', variant: 'destructive' });
    } catch (error) {
      console.error("Error deleting user:", error);
      toast({ title: 'Error Deleting User', description: (error as Error).message || 'Could not delete user.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  }, [adminUser, localUsers, toast, loadDataFromDb, canManageUsers]);

  const handleSubmitForm = useCallback(async (data: UserFormData) => {
    if (!canManageUsers) {
        toast({ title: "Permission Denied", description: "You do not have permission to save users.", variant: "destructive"});
        return;
    }
    setIsSubmitting(true);
    try {
      if (editingUser) {
        const updatePayload: User = {
            ...editingUser,
            username: data.username,
            role: data.role,
            permissions: data.role === 'manager' ? (data.permissions || []) : [],
            // Conditionally include password if it's provided and not empty string
            ...(data.password && data.password.trim() !== "" && { password: data.password.trim() }),
        };
        await updateUserInDb(updatePayload);
        toast({ title: 'User Updated', description: `User ${data.username} has been updated.` });
      } else {
        if (!data.password || data.password.trim() === "") {
           toast({ title: 'Password Required', description: 'Password is required for new users.', variant: 'destructive' });
           setIsSubmitting(false);
           return;
        }
        const newUserPayload: Omit<User, 'id' | 'activeBreakId'> = {
          username: data.username,
          role: data.role,
          password: data.password, 
          permissions: data.role === 'manager' ? (data.permissions || []) : [],
        };
        await addUserToDb(newUserPayload);
        toast({ title: 'User Added', description: `User ${newUserPayload.username} has been created.` });
      }
      await loadDataFromDb();
      setIsFormOpen(false);
      setEditingUser(null);
    } catch (error) {
      console.error("Error submitting user form:", error);
      toast({ title: 'Error Saving User', description: (error as Error).message || 'Could not save user. Please try again.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  }, [editingUser, toast, loadDataFromDb, canManageUsers]);

  const filteredUsers = localUsers.filter(user =>
    user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.role.toLowerCase().includes(searchTerm.toLowerCase())
  ).sort((a,b) => a.username.localeCompare(b.username));

  const getRoleBadgeVariant = useCallback((role: UserRole): "default" | "secondary" | "destructive" | "outline" => {
    switch (role) {
      case 'admin': return 'destructive';
      case 'manager': return 'default';
      case 'salesperson': return 'default';
      case 'storekeeper': return 'secondary';
      case 'cashier': return 'outline';
      case 'logistics': return 'secondary';
      default: return 'default';
    }
  }, []);

  const handleViewLogs = useCallback((user: User) => {
    setViewingLogsUser(user);
    setIsLogsDialogOpen(true);
  }, []);

  if (!isDataLoaded && (adminUser?.role === 'admin' || (adminUser?.role === 'manager' && canManageUsers))) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
        <p className="ml-4 text-muted-foreground">Loading user data...</p>
      </div>
    );
  }

  if (!adminUser || (!canManageUsers && !hasPermission('view_admin_dashboard'))) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage users.</p>
      </div>
    );
  }


  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-col md:flex-row items-start md:items-center justify-between">
          <div>
            <CardTitle className="text-2xl">User Management</CardTitle>
            <CardDescription>Manage user accounts and their roles within the system.</CardDescription>
          </div>
          {canManageUsers && (
            <Dialog open={isFormOpen} onOpenChange={(isOpen) => { if (!isSubmitting) setIsFormOpen(isOpen); if(!isOpen) setEditingUser(null); }}>
              <DialogTrigger asChild>
                <Button onClick={handleAddUser} disabled={isSubmitting}>
                  <PlusCircle className="mr-2 h-4 w-4" /> Add User
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>{editingUser ? 'Edit User' : 'Add New User'}</DialogTitle>
                </DialogHeader>
                {isFormOpen && ( 
                  <UserForm
                    user={editingUser}
                    onSubmit={handleSubmitForm}
                    onCancel={() => { setIsFormOpen(false); setEditingUser(null); }}
                    isLoading={isSubmitting}
                  />
                )}
              </DialogContent>
            </Dialog>
          )}
        </CardHeader>
        <CardContent>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search users by username or role..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 h-10"
            />
          </div>
           {filteredUsers.length === 0 ? (
             <div className="flex flex-col items-center justify-center py-12 text-center">
                <Users2 className="w-24 h-24 text-muted-foreground mb-6" />
                <p className="text-2xl font-semibold mb-2">No users found.</p>
                <p className="text-muted-foreground mb-6">
                  {searchTerm ? "Try a different search term." : (canManageUsers ? "Get started by adding a new user." : "No users to display.")}
                </p>
                {!searchTerm && canManageUsers && (
                  <Button onClick={handleAddUser} disabled={isSubmitting}>
                    <PlusCircle className="mr-2 h-4 w-4" /> Add Your First User
                  </Button>
                )}
            </div>
          ) : (
          <ScrollArea className="h-[calc(100vh-18rem)]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Permissions</TableHead>
                  <TableHead className="w-[50px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.map((user) => (
                  <MemoizedUserAdminRow
                    key={user.id}
                    user={user}
                    adminUser={adminUser}
                    onEdit={handleEditUser}
                    onDelete={handleDeleteUser}
                    onViewLogs={handleViewLogs}
                    isSubmitting={isSubmitting}
                    canManageUsers={canManageUsers}
                    getRoleBadgeVariant={getRoleBadgeVariant}
                  />
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
          )}
        </CardContent>
      </Card>

      {viewingLogsUser && (
        <UserActivityLogsDialog
          isOpen={isLogsDialogOpen}
          onClose={() => {
            setIsLogsDialogOpen(false);
            setViewingLogsUser(null);
          }}
          user={viewingLogsUser}
          attendanceLogs={getAttendanceLogsForUser(viewingLogsUser.id)}
          breakLogs={getBreakLogsForUser(viewingLogsUser.id)}
        />
      )}
    </div>
  );
}
