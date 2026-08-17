import { useState } from 'react';
import { submissionsAPI } from '../services/api';
import { Button, Input } from '../ui/components';

interface UploadComponentProps {
    onSuccess?: () => void;
}

export default function UploadComponent({ onSuccess }: UploadComponentProps) {
    const [file, setFile] = useState<File | null>(null);
    const [assignmentId, setAssignmentId] = useState('');
    const [uploading, setUploading] = useState(false);
    const [evaluating, setEvaluating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            const allowedExtensions = ['.pdf', '.docx', '.txt', '.py', '.java', '.cpp', '.js', '.ts', '.png', '.jpg', '.jpeg'];
            const fileExtension = '.' + selectedFile.name.split('.').pop()?.toLowerCase();

            if (!allowedExtensions.includes(fileExtension)) {
                setError(`File type not allowed. Allowed types: ${allowedExtensions.join(', ')}`);
                return;
            }

            setFile(selectedFile);
            setError(null);
        }
    };

    const handleUpload = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!file || !assignmentId) {
            setError('Please select a file and enter an assignment ID');
            return;
        }

        try {
            setUploading(true);
            setError(null);

            const response = await submissionsAPI.upload(file, assignmentId);
            const newSubmissionId = response.data.id;

            // Auto-start evaluation
            await handleEvaluate(newSubmissionId);

        } catch (err: any) {
            setError(err.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const handleEvaluate = async (id: number) => {
        try {
            setEvaluating(true);
            await submissionsAPI.evaluate(id, 1, true);
            setSuccess(true);

            setTimeout(() => {
                if (onSuccess) onSuccess();
            }, 2000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Evaluation failed');
        } finally {
            setEvaluating(false);
        }
    };

    return (
        <form onSubmit={handleUpload} className="space-y-4">
            <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                    Assignment ID
                </label>
                <Input
                    type="text"
                    value={assignmentId}
                    onChange={(e) => setAssignmentId(e.target.value)}
                    placeholder="e.g., CS101-Assignment-1"
                    required
                />
            </div>

            <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                    Upload File
                </label>
                <div className="border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:bg-muted/50 transition">
                    <input
                        type="file"
                        onChange={handleFileChange}
                        className="hidden"
                        id="file-input"
                        accept=".pdf,.docx,.txt,.py,.java,.cpp,.js,.ts,.png,.jpg,.jpeg"
                    />
                    <label htmlFor="file-input" className="cursor-pointer">
                        {file ? (
                            <div>
                                <p className="text-sm font-medium text-foreground">{file.name}</p>
                                <p className="text-xs text-muted-foreground mt-1">Click to change</p>
                            </div>
                        ) : (
                            <div>
                                <p className="text-sm font-medium text-foreground">📁 Click to upload or drag and drop</p>
                                <p className="text-xs text-muted-foreground mt-1">PDF, DOCX, Code files, or Images</p>
                            </div>
                        )}
                    </label>
                </div>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-800 text-sm">
                    {error}
                </div>
            )}

            {success && (
                <div className="p-3 bg-green-50 border border-green-200 rounded-md text-green-800 text-sm">
                    ✓ Assignment uploaded and evaluation started! Redirecting...
                </div>
            )}

            <Button
                type="submit"
                className="w-full"
                disabled={uploading || evaluating || !file}
            >
                {uploading
                    ? 'Uploading...'
                    : evaluating
                        ? 'Evaluating...'
                        : 'Upload & Evaluate'}
            </Button>
        </form>
    );
}
