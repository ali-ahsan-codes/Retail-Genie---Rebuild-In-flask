
'use client';
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, Controller } from "react-hook-form";
import * as z from "zod";
import type { User, UserRole, Permission } from "@/types";
import { USER_ROLES, AVAILABLE_PERMISSIONS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DialogFooter } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import React from "react";

const userFormSchemaBase = z.object({
  username: z.string().min(3, { message: "Username must be at least 3 characters." }),
  role: z.enum(USER_ROLES as [UserRole, ...UserRole[]], {
    required_error: "You need to select a user role.",
  }),
  permissions: z.array(z.string()).optional(),
  autoEnterAfterScan: z.boolean().optional(),
});

const userFormSchemaCreate = userFormSchemaBase.extend({
  password: z.string().min(6, { message: "Password must be at least 6 characters." }),
});

const userFormSchemaEdit = userFormSchemaBase.extend({
  password: z.string().min(6, { message: "Password must be at least 6 characters." }).optional().or(z.literal('')),
});

interface UserFormProps {
  user?: User | null;
  onSubmit: (data: z.infer<typeof userFormSchemaCreate> | z.infer<typeof userFormSchemaEdit>) => void;
  onCancel?: () => void;
  isLoading?: boolean;
}

export default function UserForm({ user, onSubmit, onCancel, isLoading = false }: UserFormProps) {
  const schema = user ? userFormSchemaEdit : userFormSchemaCreate;

  const defaultValues = React.useMemo(() => user
    ? {
        username: user.username,
        role: user.role,
        password: "",
        permissions: user.permissions || [],
        autoEnterAfterScan: user.autoEnterAfterScan ?? true,
      }
    : {
        username: "",
        role: undefined as UserRole | undefined,
        password: "",
        permissions: [],
        autoEnterAfterScan: true,
      }, [user]);

  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues,
  });

  React.useEffect(() => {
    form.reset(defaultValues);
  }, [user, defaultValues, form]);

  const currentRole = form.watch("role");

  const handleSubmit = (data: z.infer<typeof schema>) => {
    // If editing and password is blank, we don't want to send it
    if (user && data.password === "") {
      const { password, ...rest } = data;
      onSubmit(rest as any); // The type will be correct based on schema
    } else {
      onSubmit(data);
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
        <FormField
          control={form.control}
          name="username"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Username</FormLabel>
              <FormControl>
                <Input placeholder="john.doe" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="role"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role</FormLabel>
              <Select
                onValueChange={(value) => {
                  field.onChange(value as UserRole);
                  if (value !== 'manager') {
                    form.setValue('permissions', []);
                  } else if (user && user.role === 'manager' && value === 'manager') {
                    form.setValue('permissions', user.permissions || []);
                  } else if (value === 'manager' && (!user || user.role !== 'manager')) {
                     form.setValue('permissions', []);
                  }
                }}
                defaultValue={field.value}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a role" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {USER_ROLES.map((roleValue) => (
                    <SelectItem key={roleValue} value={roleValue} className="capitalize">
                      {roleValue.charAt(0).toUpperCase() + roleValue.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{user ? "New Password (optional)" : "Password"}</FormLabel>
              <FormControl>
                <Input type="password" placeholder="******" {...field} />
              </FormControl>
              <FormDescription>
                {user ? "Leave blank to keep current password." : "Minimum 6 characters."}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {currentRole === 'manager' && (
          <FormField
            control={form.control}
            name="permissions"
            render={() => (
              <FormItem>
                <div className="mb-4">
                  <FormLabel className="text-base">Manager Permissions</FormLabel>
                  <FormDescription>
                    Select the actions this manager account can perform.
                  </FormDescription>
                </div>
                <ScrollArea className="h-40 rounded-md border p-4">
                  {AVAILABLE_PERMISSIONS.map((permission) => (
                    <FormField
                      key={permission}
                      control={form.control}
                      name="permissions"
                      render={({ field: permissionField }) => {
                        return (
                          <FormItem
                            key={permission}
                            className="flex flex-row items-start space-x-3 space-y-0 py-1"
                          >
                            <FormControl>
                              <Checkbox
                                checked={permissionField.value?.includes(permission)}
                                onCheckedChange={(checked) => {
                                  return checked
                                    ? permissionField.onChange([...(permissionField.value || []), permission])
                                    : permissionField.onChange(
                                        (permissionField.value || []).filter(
                                          (value) => value !== permission
                                        )
                                      );
                                }}
                              />
                            </FormControl>
                            <FormLabel className="text-sm font-normal capitalize">
                              {permission.replace(/_/g, ' ')}
                            </FormLabel>
                          </FormItem>
                        );
                      }}
                    />
                  ))}
                </ScrollArea>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {currentRole === 'express' && (
          <FormField
            control={form.control}
            name="autoEnterAfterScan"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3 shadow-sm">
                <div className="space-y-0.5">
                  <FormLabel>Auto-Submit Scan</FormLabel>
                  <FormDescription>
                    Enable to automatically search after a barcode is scanned.
                  </FormDescription>
                </div>
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
              </FormItem>
            )}
          />
        )}

        <DialogFooter className="pt-4">
          {onCancel && <Button type="button" variant="outline" onClick={onCancel} disabled={isLoading}>Cancel</Button>}
          <Button type="submit" disabled={isLoading}>
            {isLoading ? "Saving..." : (user ? "Save Changes" : "Add User")}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  );
}
