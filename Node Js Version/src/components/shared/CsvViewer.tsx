
import { useState, useEffect } from 'react';
import { Input } from '../ui/input'; // Assuming ShadCN input
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'; // Assuming ShadCN select

interface CsvViewerProps {
  data: any[]; // Define a more specific type if possible
}

const CsvViewer: React.FC<CsvViewerProps> = ({ data = [] }) => {
  const [search, setSearch] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [filterOptions, setFilterOptions] = useState<string[]>(['All']);
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc' | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10; // You can make this configurable

  if (!data || data.length === 0) {
    return <div className="p-4 text-center text-gray-500">No CSV data available.</div>;
  }

  const headers = Object.keys(data[0]);

  // Extract unique values for filtering (assuming a 'vendor' column for now)
  useEffect(() => {
    if (data && data.length > 0) {
      const uniqueVendors = Array.from(new Set(data.map(item => item.vendor))).filter(Boolean);
      setFilterOptions(['All', ...uniqueVendors]);
      setCurrentPage(1); // Reset to first page when data or filter options change
    }
  }, [data]); // Recalculate options when data changes
  const filteredData = data.filter(item => {
    // Filter by search term (case-insensitive, check all values)
    const searchTermMatch = Object.values(item).some(value =>
      String(value).toLowerCase().includes(search.toLowerCase())
    );

    // Filter by selected filter value (e.g., 'vendor' column)
    const filterMatch = filterValue === '' || filterValue === 'All' || (item.vendor && item.vendor === filterValue);

    return searchTermMatch && filterMatch;
  });

  // Sorting Logic
  const sortedData = [...filteredData].sort((a, b) => {
    if (!sortColumn) return 0;

    const aValue = a[sortColumn] ?? '';
    const bValue = b[sortColumn] ?? '';

    if (aValue < bValue) {
      return sortDirection === 'asc' ? -1 : 1;
    }
    if (aValue > bValue) {
      return sortDirection === 'asc' ? 1 : -1;
    }
    return 0;
  });

  // Reset to first page when sorting changes
  useEffect(() => {
    setCurrentPage(1);
  }, [sortColumn, sortDirection]); // Reset page when sort criteria change

  // Calculate pagination values (based on sortedData)
  const totalPages = Math.ceil(sortedData.length / itemsPerPage); // Use sortedData.length
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const displayedData = sortedData.slice(startIndex, endIndex); // Use sortedData for display

  return (
    <div className="overflow-x-auto">
      <div className="flex space-x-4 mb-4">
        <Input
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Select onValueChange={setFilterValue} value={filterValue}>
          <SelectTrigger className="max-w-[180px]">
            <SelectValue placeholder="Filter by Vendor" />
          </SelectTrigger>
          <SelectContent>
            {filterOptions.map(option => <SelectItem key={option} value={option}>{option}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <table className="min-w-full bg-white border border-gray-300">
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th
                key={index}
                className="py-2 px-4 border-b border-gray-300 bg-gray-100 text-left text-sm font-semibold text-gray-600 cursor-pointer hover:bg-gray-200"
                onClick={() => {
                  if (sortColumn === header) {
                    setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
                  } else {
                    setSortColumn(header);
                    setSortDirection('asc');
                  }}}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayedData.map((row, rowIndex) => ( 
            <tr key={rowIndex} className="hover:bg-gray-50">
              {headers.map((header, cellIndex) => (
                <td key={cellIndex} className="py-2 px-4 border-b border-gray-300 text-sm text-gray-700">
                  {String(row[header] ?? '')} {/* Ensure value is a string and handle null/undefined */}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex justify-between items-center mt-4">
          <button
            onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
            disabled={currentPage === 1}
            className="px-4 py-2 border rounded disabled:opacity-50"
          >
            Previous
          </button>
          <span>Page {currentPage} of {totalPages}</span>
          <button
            onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
            disabled={currentPage === totalPages}
            className="px-4 py-2 border rounded disabled:opacity-50"

          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default CsvViewer;
