'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { DocumentTable } from '@/components/documents/document-table';
import { UploadDialog } from '@/components/documents/upload-dialog';
import { DocumentDetail } from '@/components/documents/document-detail';
import { Skeleton } from '@/components/ui/skeleton';
import { Search, Filter, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function DocumentsPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'processing' | 'completed' | 'failed' | ''>('');
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['documents', { search, status: statusFilter }],
    queryFn: () => api.documents.list({
      limit: 50,
      offset: 0,
      search: search || undefined,
      status: statusFilter || undefined,
    }),
  });

  const TableSkeleton = () => (
    <div className="rounded-md border">
      <div className="overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b">
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-24" /></th>
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-20" /></th>
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-16" /></th>
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-32" /></th>
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-16" /></th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b">
                <td className="p-4"><Skeleton className="h-4 w-40" /></td>
                <td className="p-4"><Skeleton className="h-4 w-20" /></td>
                <td className="p-4"><Skeleton className="h-4 w-12" /></td>
                <td className="p-4"><Skeleton className="h-4 w-24" /></td>
                <td className="p-4"><Skeleton className="h-4 w-16" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Documents</h1>
          <p className="text-muted-foreground">Manage your document library</p>
        </div>
        <UploadDialog />
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as 'processing' | 'completed' | 'failed' | '')}>
          <SelectTrigger className="w-full sm:w-[180px]">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Statuses</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : (
        <DocumentTable
          documents={data?.items || []}
          onView={(id) => setSelectedDoc(id)}
        />
      )}

      {selectedDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b">
              <h2 className="text-lg font-semibold">Document Details</h2>
              <Button variant="ghost" size="icon" onClick={() => setSelectedDoc(null)}>
                <span className="sr-only">Close</span>
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </Button>
            </div>
            <div className="p-4 overflow-y-auto max-h-[calc(90vh-80px)]">
              <DocumentDetail id={selectedDoc} onClose={() => setSelectedDoc(null)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}