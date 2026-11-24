'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileText, MessageSquare, Calendar, Plus, Search, Upload } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  const stats = [
    { name: 'Documents', value: '12', icon: FileText, href: '/documents', color: 'text-blue-500' },
    { name: 'Chat Sessions', value: '8', icon: MessageSquare, href: '/chat2', color: 'text-green-500' },
    { name: 'Bookings', value: '3', icon: Calendar, href: '/bookings', color: 'text-purple-500' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">Welcome back! Here's an overview of your activity.</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href="/documents">
              <Upload className="mr-2 h-4 w-4" />
              Upload Document
            </Link>
          </Button>
          <Button asChild>
            <Link href="/chat2">
              <MessageSquare className="mr-2 h-4 w-4" />
              New Chat
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {stats.map((stat) => (
          <Card key={stat.name}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.name}</CardTitle>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground">Total count</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button asChild variant="outline" className="w-full justify-start gap-2">
              <Link href="/documents">
                <FileText className="h-4 w-4" />
                Manage Documents
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start gap-2">
              <Link href="/chat2">
                <MessageSquare className="h-4 w-4" />
                Start Chat
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-start gap-2">
              <Link href="/bookings">
                <Calendar className="h-4 w-4" />
                View Bookings
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">No recent activity yet. Upload a document or start a chat to get started!</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}