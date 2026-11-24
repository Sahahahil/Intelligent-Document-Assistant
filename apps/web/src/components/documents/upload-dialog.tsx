'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { Upload, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { createQueryClient } from '@/lib/query-client';

interface UploadDialogProps {
  onSuccess?: () => void;
}

export function UploadDialog({ onSuccess }: UploadDialogProps) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [strategy, setStrategy] = useState<'fixed_size' | 'recursive'>('recursive');
  const [chunkSize, setChunkSize] = useState(1000);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [progress, setProgress] = useState(0);
  const { toast } = useToast();

  const mutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/documents/ingest`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }
      return response.json();
    },
    onSuccess: () => {
      setOpen(false);
      setFile(null);
      setProgress(0);
      toast({ title: 'Success', description: 'Document uploaded successfully' });
      createQueryClient().invalidateQueries({ queryKey: ['documents'] });
      onSuccess?.();
    },
    onError: (error: Error) => {
      toast({ title: 'Error', description: error.message, variant: 'destructive' });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('chunking_strategy', strategy);
    fd.append('chunk_size', String(chunkSize));
    fd.append('chunk_overlap', String(chunkOverlap));
    mutation.mutate(fd);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Upload className="mr-2 h-4 w-4" />
          Upload Document
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Upload Document</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="file">File</Label>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                file ? 'border-green-500 bg-green-50' : 'border-muted'
              }`}
            >
              <input
                type="file"
                id="file"
                accept=".pdf,.txt"
                onChange={(e) => {
                  const selectedFile = e.target.files?.[0];
                  if (selectedFile) {
                    if (!['application/pdf', 'text/plain'].includes(selectedFile.type)) {
                      toast({ title: 'Error', description: 'Only PDF and TXT files are allowed', variant: 'destructive' });
                      return;
                    }
                    if (selectedFile.size > 20 * 1024 * 1024) {
                      toast({ title: 'Error', description: 'File size must be less than 20MB', variant: 'destructive' });
                      return;
                    }
                    setFile(selectedFile);
                  }
                }}
                className="hidden"
                required={!file}
                disabled={mutation.isPending}
              />
              <label
                htmlFor="file"
                className="cursor-pointer flex flex-col items-center gap-2"
              >
                <Upload className="h-8 w-8 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">
                    {file ? file.name : 'Click to upload or drag and drop'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    PDF or TXT, max 20MB
                  </p>
                </div>
              </label>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="strategy">Chunking Strategy</Label>
            <Select value={strategy} onValueChange={(v) => setStrategy(v as 'fixed_size' | 'recursive')}>
              <SelectTrigger>
                <SelectValue placeholder="Select strategy" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="recursive">Recursive (recommended)</SelectItem>
                <SelectItem value="fixed_size">Fixed Size</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {strategy === 'fixed_size' && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="chunkSize">Chunk Size (words)</Label>
                <Input
                  id="chunkSize"
                  type="number"
                  min="100"
                  max="4000"
                  value={chunkSize}
                  onChange={(e) => setChunkSize(Math.max(100, Math.min(4000, parseInt(e.target.value) || 1000)))}
                  disabled={mutation.isPending}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="chunkOverlap">Chunk Overlap (words)</Label>
                <Input
                  id="chunkOverlap"
                  type="number"
                  min="0"
                  max="1000"
                  value={chunkOverlap}
                  onChange={(e) => setChunkOverlap(Math.max(0, Math.min(1000, parseInt(e.target.value) || 200)))}
                  disabled={mutation.isPending}
                />
              </div>
            </div>
          )}

          {mutation.isPending && (
            <div className="space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-sm text-muted-foreground">Uploading... {progress}%</p>
            </div>
          )}

          <Button type="submit" disabled={!file || mutation.isPending} className="w-full">
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Upload
              </>
            )}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}