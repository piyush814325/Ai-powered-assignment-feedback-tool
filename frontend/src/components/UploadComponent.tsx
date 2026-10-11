import { useState } from 'react';
import { submissionsAPI } from '../services/api';
import type { Assignment } from '../types/assignment';
import { Alert, Button, EmptyState, FormField, Select } from '../ui/components';

interface UploadComponentProps {
    assignments: Assignment[];
    onSuccess?: () => void;
}

interface ApiError {
    response?: { data?: { detail?: string } };
}

export default function UploadComponent({ assignments, onSuccess }: UploadComponentProps) {
    const [file, setFile] = useState<File | null>(null);
    const [assignmentId, setAssignmentId] = useState('');
    const [uploading, setUploading] = useState(false);
    const [evaluating, setEvaluating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            const assignment = assignments.find((item) => item.id === Number(assignmentId));
            if (!assignment) return;
            const fileExtension = '.' + selectedFile.name.split('.').pop()?.toLowerCase();
            const fileType = ['py', 'java', 'cpp', 'js', 'ts'].includes(fileExtension.slice(1))
                ? 'code'
                : ['png', 'jpg', 'jpeg'].includes(fileExtension.slice(1))
                    ? 'image'
                    : fileExtension.slice(1);
            if (!assignment.allowed_file_types.map((type) => type.toLowerCase()).includes(fileType) &&
                !assignment.allowed_file_types.map((type) => type.toLowerCase()).includes(fileExtension.slice(1))) {
                setError(`File type not allowed. This assignment accepts: ${assignment.allowed_file_types.join(', ')}`);
                return;
            }

            setFile(selectedFile);
            setError(null);
        }
    };

    const handleUpload = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!file) {
            setError('Please select a file');
            return;
        }

        if (!assignmentId) {
            setError('Please select an assignment');
            return;
        }
        const assignment = assignments.find((item) => item.id === Number(assignmentId));
        if (!assignment || (assignment.due_date && new Date(assignment.due_date) < new Date())) {
            setError('This assignment is closed or past its due date');
            return;
        }

        try {
            setUploading(true);
            setError(null);

            const response = await submissionsAPI.upload(file, Number(assignmentId));
            const newSubmissionId = response.data.id;

            // Auto-start evaluation
            await handleEvaluate(newSubmissionId);

        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const handleEvaluate = async (id: number) => {
        try {
            setEvaluating(true);
            await submissionsAPI.evaluate(id, undefined, true);
            setSuccess(true);

            setTimeout(() => {
                if (onSuccess) onSuccess();
            }, 2000);
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.response?.data?.detail || 'Evaluation failed');
        } finally {
            setEvaluating(false);
        }
    };

    return (
        <form onSubmit={handleUpload} className="space-y-4">
            {assignments.length === 0 ? <EmptyState title="No assignments have been posted yet" /> : (
                <FormField label="Assignment" htmlFor="assignment-select">
                    <Select id="assignment-select" value={assignmentId} onChange={(e) => { setAssignmentId(e.target.value); setFile(null); }} required>
                        <option value="">Select an assignment</option>
                        {assignments.map((assignment) => {
                            const closed = assignment.due_date ? new Date(assignment.due_date) < new Date() : false;
                            return <option key={assignment.id} value={assignment.id} disabled={closed}>
                                {assignment.subject_code} - {assignment.title}{closed ? ' (closed)' : ''}
                            </option>;
                        })}
                    </Select>
                </FormField>
            )}

            {assignments.find((assignment) => assignment.id === Number(assignmentId)) && (() => {
                const assignment = assignments.find((item) => item.id === Number(assignmentId))!;
                return <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                    <p className="font-semibold text-foreground">{assignment.title}</p>
                    <p className="mt-1 text-muted-foreground">{assignment.description || 'No additional instructions.'}</p>
                    {assignment.due_date && <p className="mt-1 text-muted-foreground">Due {new Date(assignment.due_date).toLocaleString()}</p>}
                </div>;
            })()}

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

            {error && <Alert variant="error">{error}</Alert>}

            {success && (
                <div className="p-3 bg-green-50 border border-green-200 rounded-md text-green-800 text-sm">
                    ✓ Assignment uploaded and evaluation started! Redirecting...
                </div>
            )}

            <Button
                type="submit"
                className="w-full"
                disabled={uploading || evaluating || !file || !assignmentId || assignments.length === 0}
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
