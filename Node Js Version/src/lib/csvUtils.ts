// src/lib/csvUtils.ts
import Papa from 'papaparse';

/**
 * Converts an array of objects to a CSV string using PapaParse.
 * @param data Array of objects.
 * @param headers Optional array of header strings (fields to include and their order).
 *                If not provided, PapaParse will use keys from the first object.
 * @returns CSV string.
 */
export function arrayToCsv(data: any[], headers?: string[]): string {
  if (!data || data.length === 0) {
    return '';
  }
  return Papa.unparse(data, {
    columns: headers, // PapaParse uses 'columns' for specifying fields/order
    header: true,     // Include the header row in the output
    skipEmptyLines: true,
  });
}

/**
 * Converts a CSV string to an array of objects using PapaParse.
 * Assumes the first row is the header row.
 * @param csvString The CSV string.
 * @returns Array of objects.
 */
export function csvToArray(csvString: string): any[] {
  if (!csvString || csvString.trim() === '') {
    return [];
  }

  const result = Papa.parse(csvString.trim(), {
    header: true,        // Treat the first row as headers and return objects
    skipEmptyLines: true,// Skip empty lines
    dynamicTyping: true, // Automatically convert numerics, booleans, null
  });

  if (result.errors.length > 0) {
    console.warn("CSV parsing errors encountered:", result.errors);
    // Depending on strictness, you might throw an error or return partial data
    // For now, return data even with minor errors, as PapaParse often still provides useful data
  }

  return result.data as any[];
}

/**
 * Parses a CSV value, converting to number or boolean if appropriate.
 * This can be used for post-processing if PapaParse's dynamicTyping isn't sufficient
 * or if specific non-standard boolean/date formats need handling.
 * With PapaParse's dynamicTyping, its direct necessity is reduced for common types.
 * @param value The string value from CSV.
 * @returns Parsed value (string, number, boolean, or original string if no conversion).
 */
export function parseCsvValue(value: any): any {
    // If PapaParse dynamicTyping is on, `value` might already be typed.
    if (typeof value !== 'string') return value; // Already converted by PapaParse or not a string

    const trimmedValue = value.trim();
    if (trimmedValue === "") return undefined;

    // Boolean check (if dynamicTyping didn't catch it or for custom strings)
    if (trimmedValue.toLowerCase() === 'true') return true;
    if (trimmedValue.toLowerCase() === 'false') return false;

    // Number check (if dynamicTyping didn't catch it)
    const num = Number(trimmedValue);
    if (!isNaN(num) && trimmedValue !== '') return num;

    // Date check (basic ISO format check - can be expanded)
    if (/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$/.test(trimmedValue)) {
        return trimmedValue; // Return as string for further processing (e.g., with date-fns)
    }
    
    // JSON array/object check (simple check for strings starting with [ or { and ending with ] or })
    if ((trimmedValue.startsWith('[') && trimmedValue.endsWith(']')) || (trimmedValue.startsWith('{') && trimmedValue.endsWith('}'))) {
        try {
            return JSON.parse(trimmedValue);
        } catch (e) {
            // Not a valid JSON, return as string
        }
    }
    return value; // Return original string if no other type matches
}
