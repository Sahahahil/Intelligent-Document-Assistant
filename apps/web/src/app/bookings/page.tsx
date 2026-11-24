'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { BookingTable } from '@/components/bookings/booking-table';
import { BookingFormDialog } from '@/components/bookings/booking-form-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Search, Filter, Loader2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function BookingsPage() {
  const [statusFilter, setStatusFilter] = useState<'draft' | 'confirmed' | 'cancelled' | ''>('');

  const { data, isLoading } = useQuery({
    queryKey: ['bookings', { status: statusFilter }],
    queryFn: () => api.bookings.list({
      limit: 50,
      offset: 0,
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
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-24" /></th>
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-24" /></th>
              <th className="h-12 px-4 text-left"><Skeleton className="h-4 w-16" /></th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b">
                <td className="p-4"><Skeleton className="h-4 w-40" /></td>
                <td className="p-4"><Skeleton className="h-4 w-20" /></td>
                <td className="p-4"><Skeleton className="h-4 w-24" /></td>
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
          <h1 className="text-3xl font-bold">Bookings</h1>
          <p className="text-muted-foreground">Manage interview bookings</p>
        </div>
        <BookingFormDialog onSuccess={() => {}} />
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as 'draft' | 'confirmed' | 'cancelled' | '')}>
          <SelectTrigger className="w-full sm:w-[180px]">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All Statuses</SelectItem>
            <SelectItem value="confirmed">Confirmed</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : (
        <BookingTable
          bookings={data?.items || []}
        />
      )}
    </div>
  );
}