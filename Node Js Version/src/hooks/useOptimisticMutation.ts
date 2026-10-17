
// src/hooks/useOptimisticMutation.ts
"use client";

import { useState, useCallback } from 'react';
import { useToast } from './use-toast'; // Assuming toast might be used for generic errors

interface UseOptimisticMutationOptions<TData, TError, TVariables, TContext> {
  onMutate?: (variables: TVariables) => Promise<TContext | void> | TContext | void;
  onSuccess?: (data: TData, variables: TVariables, context: TContext | void) => Promise<void> | void;
  onError?: (error: TError, variables: TVariables, context: TContext | void) => Promise<void> | void;
  onSettled?: (data: TData | undefined, error: TError | null, variables: TVariables, context: TContext | void) => Promise<void> | void;
}

export function useOptimisticMutation<
  TData = unknown,      // Type of data returned by the mutation function
  TError = Error,       // Type of error thrown by the mutation function
  TVariables = void,    // Type of variables passed to the mutation function
  TContext = unknown    // Type of context returned by onMutate and passed to onSuccess/onError/onSettled
>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: UseOptimisticMutationOptions<TData, TError, TVariables, TContext>
) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<TError | null>(null);
  const [data, setData] = useState<TData | undefined>(undefined);
  const [isSuccess, setIsSuccess] = useState(false);
  const { toast } = useToast();

  const mutate = useCallback(
    async (variables: TVariables) => {
      setIsLoading(true);
      setError(null);
      setData(undefined);
      setIsSuccess(false);

      let mutationContext: TContext | void;
      try {
        if (options?.onMutate) {
          mutationContext = await options.onMutate(variables);
        }

        const result = await mutationFn(variables);
        setData(result);
        setIsSuccess(true);

        if (options?.onSuccess) {
          await options.onSuccess(result, variables, mutationContext);
        }
        return result; // Return data on successful mutation
      } catch (err: any) {
        setError(err);
        setIsSuccess(false);
        console.error("Mutation Error in useOptimisticMutation:", err);

        if (options?.onError) {
          await options.onError(err, variables, mutationContext);
        } else {
          // Default error handling if no onError is provided
          toast({
            title: "Operation Failed",
            description: err.message || "An unexpected error occurred.",
            variant: "destructive",
          });
        }
        // Do not re-throw here if onError handles it, otherwise it could be re-thrown if caller awaits mutate
        // and doesn't have its own try-catch. Let the hook manage the error state.
        // throw err; // Optionally re-throw if the caller needs to catch it directly
      } finally {
        setIsLoading(false);
        if (options?.onSettled) {
          // If data is undefined (error occurred) and error is not null, pass error.
          // If data is defined (success) and error is null, pass data.
          await options.onSettled(data, error, variables, mutationContext);
        }
      }
    },
    [mutationFn, options, data, error, toast] // Added data and error to dependency array if onSettled uses them
  );

  return {
    mutate,
    isLoading,
    error,
    data,
    isSuccess,
  };
}
