'use client';

import * as React from 'react';
import { Calendar as CalendarIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DayPicker } from 'react-day-picker';

interface CalendarProps {
  mode?: 'single' | 'multiple' | 'range';
  selected?: Date | Date[] | { from: Date; to: Date } | undefined;
  onSelect?: (date: Date | Date[] | { from: Date; to: Date } | undefined) => void;
  disabled?: boolean;
  className?: string;
}

const Calendar = React.forwardRef<HTMLDivElement, CalendarProps>(
  ({ className, mode = 'single', selected, onSelect, disabled, ...props }) => {
    return (
      <DayPicker
        mode={mode as 'single'}
        selected={selected as Date | undefined}
        onSelect={onSelect as (date: Date | undefined) => void}
        disabled={disabled}
        className="p-3"
      />
    );
  },
);

Calendar.displayName = 'Calendar';

export { Calendar };