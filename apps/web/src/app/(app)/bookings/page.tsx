'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';

const STEPS = ['Date', 'Time', 'Details', 'Confirm'];
const SLOTS = ['09:00', '09:30', '10:00', '10:30', '11:00', '13:00', '14:00', '14:30', '15:00', '16:00'];
const DOW = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function longDate(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function today(): Date {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return now;
}

export default function BookingsPage() {
  const queryClient = useQueryClient();
  const now = today();

  const [step, setStep] = useState(0);
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [date, setDate] = useState<Date | null>(null);
  const [time, setTime] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['bookings'],
    queryFn: () => api.bookings.list({ limit: 100, offset: 0 }),
  });
  const bookings = data?.items ?? [];

  const taken = useMemo(
    () => new Set(bookings.map((booking) => `${booking.interview_date}|${booking.interview_time.slice(0, 5)}`)),
    [bookings],
  );

  const create = useMutation({
    mutationFn: () =>
      api.bookings.create({
        name: name.trim(),
        email: email.trim(),
        interview_date: date ? isoDate(date) : '',
        interview_time: time,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
      setStep(4);
      setError('');
    },
    onError: (reason: Error) => setError(reason.message || 'The booking could not be saved'),
  });

  const first = new Date(view.year, view.month, 1);
  const days = new Date(view.year, view.month + 1, 0).getDate();

  const moveMonth = (delta: number) => {
    const next = new Date(view.year, view.month + delta, 1);
    setView({ year: next.getFullYear(), month: next.getMonth() });
  };

  const canContinue =
    (step === 0 && date !== null) ||
    (step === 1 && time !== '') ||
    (step === 2 && name.trim() !== '' && /^\S+@\S+\.\S+$/.test(email.trim())) ||
    // The review step has nothing left to fill in.
    step === 3;

  const next = () => {
    setError('');
    if (step === 2 && !canContinue) {
      setError('Enter your name and a valid email address.');
      return;
    }
    if (step === 3) {
      create.mutate();
      return;
    }
    setStep(step + 1);
  };

  const upcoming = bookings
    .filter((booking) => booking.interview_date >= isoDate(now))
    .sort((a, b) =>
      `${a.interview_date}${a.interview_time}`.localeCompare(`${b.interview_date}${b.interview_time}`),
    );

  return (
    <div className="h-full w-full overflow-auto px-8 py-7 max-[820px]:px-4 max-[820px]:py-5">
      <div className="mx-auto max-w-[900px]">
        <div className="mb-[22px] flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[28px]">Interview bookings</h1>
            <p className="mt-1 text-muted-foreground">
              Pick a date, a time and tell us who&apos;s joining.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_300px] items-start gap-6 max-[820px]:grid-cols-1">
          <div className="card">
            <div className="mb-[18px] flex flex-wrap gap-1.5">
              {STEPS.map((label, index) => (
                <span
                  key={label}
                  className={`rounded-full border px-3 py-1 text-[13px] ${
                    index === step
                      ? 'border-primary bg-secondary font-semibold text-secondary-foreground'
                      : index < step
                        ? 'border-line text-success'
                        : 'border-line text-muted-foreground'
                  }`}
                >
                  {label}
                </span>
              ))}
            </div>

            {step === 0 && (
              <>
                <div className="mb-2.5 flex items-center justify-between">
                  <button type="button" className="ghost" onClick={() => moveMonth(-1)} aria-label="Previous month">
                    ‹
                  </button>
                  <h3 className="text-[20px]">
                    {first.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                  </h3>
                  <button type="button" className="ghost" onClick={() => moveMonth(1)} aria-label="Next month">
                    ›
                  </button>
                </div>
                <div className="grid grid-cols-7 gap-1 text-center">
                  {DOW.map((day, index) => (
                    <div key={index} className="py-1 text-[12px] text-muted-foreground">
                      {day}
                    </div>
                  ))}
                  {Array.from({ length: first.getDay() }).map((_, index) => (
                    <div key={`pad-${index}`} />
                  ))}
                  {Array.from({ length: days }).map((_, index) => {
                    const day = index + 1;
                    const candidate = new Date(view.year, view.month, day);
                    const weekend = candidate.getDay() % 6 === 0;
                    const past = candidate < now;
                    const selected = date !== null && +date === +candidate;
                    return (
                      <button
                        key={day}
                        type="button"
                        disabled={weekend || past}
                        onClick={() => {
                          setDate(candidate);
                          setTime('');
                        }}
                        className={`aspect-square rounded-lg text-[14px] disabled:cursor-default disabled:text-line ${
                          selected
                            ? 'bg-primary font-semibold text-primary-foreground'
                            : 'hover:bg-secondary'
                        } ${+candidate === +now ? 'shadow-[inset_0_0_0_1px_var(--acc)]' : ''}`}
                      >
                        {day}
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            {step === 1 && date && (
              <>
                <p className="mb-3 text-muted-foreground">Available on {longDate(date)}</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2">
                  {SLOTS.map((slot) => {
                    const booked = taken.has(`${isoDate(date)}|${slot}`);
                    const selected = time === slot;
                    return (
                      <button
                        key={slot}
                        type="button"
                        disabled={booked}
                        onClick={() => setTime(slot)}
                        className={`rounded-lg border px-2.5 py-2 ${
                          selected
                            ? 'border-primary bg-primary font-semibold text-primary-foreground'
                            : 'border-line hover:border-primary'
                        } disabled:cursor-default disabled:opacity-40 disabled:line-through`}
                      >
                        {slot}
                      </button>
                    );
                  })}
                </div>
                {taken.size > 0 && (
                  <p className="mt-3 text-[13px] text-muted-foreground">
                    A slot with a line through it is already booked.
                  </p>
                )}
              </>
            )}

            {step === 2 && (
              <>
                <label className="field">
                  Full name
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    placeholder="Priya Shah"
                  />
                </label>
                <label className="field">
                  Email
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    placeholder="priya@example.com"
                  />
                </label>
              </>
            )}

            {step === 3 && date && (
              <>
                <h3 className="mb-2.5 text-[22px]">Review your booking</h3>
                {[
                  ['Date', longDate(date)],
                  ['Time', time],
                  ['Name', name],
                  ['Email', email],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="flex justify-between gap-2.5 border-b border-line py-2.5 text-[14px] last:border-0"
                  >
                    <span>{label}</span>
                    <b className="font-semibold">{value}</b>
                  </div>
                ))}
              </>
            )}

            {step === 4 && (
              <>
                <h3 className="text-[22px]">Booking confirmed</h3>
                <p className="font-semibold text-success">
                  {date && longDate(date)} at {time}
                </p>
                <p className="text-muted-foreground">
                  A confirmation will go to {email}.
                </p>
                <button
                  type="button"
                  className="btn sec mt-3"
                  onClick={() => {
                    setStep(0);
                    setDate(null);
                    setTime('');
                    setName('');
                    setEmail('');
                  }}
                >
                  Book another
                </button>
              </>
            )}

            {error && <p className="mt-3 text-[13px] text-destructive">{error}</p>}

            {step < 4 && (
              <div className="mt-[18px] flex justify-between gap-3">
                <button
                  type="button"
                  className="btn sec"
                  style={step === 0 ? { visibility: 'hidden' } : undefined}
                  onClick={() => setStep(step - 1)}
                >
                  Back
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={!canContinue || create.isPending}
                  onClick={next}
                >
                  {step === 3 ? 'Confirm booking' : 'Continue'}
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="mb-1.5 text-[19px]">Upcoming</h3>
            {isLoading ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : upcoming.length === 0 ? (
              <p className="text-muted-foreground">No interviews booked yet.</p>
            ) : (
              upcoming.map((booking) => (
                <div
                  key={booking.id}
                  className="flex justify-between gap-2.5 border-b border-line py-2.5 text-[14px] last:border-0"
                >
                  <div className="min-w-0">
                    <b className="block truncate font-semibold">{booking.name}</b>
                    <small className="block truncate text-muted-foreground">{booking.email}</small>
                  </div>
                  <div className="shrink-0 text-right">
                    {new Date(`${booking.interview_date}T00:00:00`).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                    <small className="block text-muted-foreground">
                      {booking.interview_time.slice(0, 5)}
                    </small>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
