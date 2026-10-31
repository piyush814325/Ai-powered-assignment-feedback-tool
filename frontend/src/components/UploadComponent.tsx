import { useRef, useState } from 'react';
import { submissionsAPI } from '../services/api';
import type { Assignment } from '../types/assignment';
import type { SubmissionEvaluationResult } from '../types/submission';
import { Alert, Button, EmptyState, FormField, Select } from '../ui/components';

interface UploadComponentProps {
    assignments: Assignment[];
    submittedAssignmentIds: ReadonlySet<number>;
    onSuccess?: (closeUpload?: boolean) => void;
    submissionToReplace?: { id: number; assignment_id: number };
}

interface ApiError {
    response?: { data?: { detail?: string } };
}

export default function UploadComponent({ assignments, submittedAssignmentIds, onSuccess, submissionToReplace }: UploadComponentProps) {
    const [file, setFile] = useState<File | null>(null);
    const [assignmentId, setAssignmentId] = useState(submissionToReplace ? String(submissionToReplace.assignment_id) : '');
    const [uploading, setUploading] = useState(false);
    const [evaluating, setEvaluating] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);
    const [verification, setVerification] = useState<SubmissionEvaluationResult | null>(null);
    const [replaceSubmissionId, setReplaceSubmissionId] = useState<number | null>(submissionToReplace?.id ?? null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            const assignment = assignments.find((item) => item.id === Number(assignmentId));
            if (!assignment) return;
            const fileExtension = '.' + selectedFile.name.split('.').pop()?.toLowerCase();
            const fileType = ['py', 'java', 'cpp', 'js', 'ts'].includes(fileExtension.slice(1))
                ? 'code'
                : fileExtension.slice(1);
            if (!assignment.allowed_file_types.map((type) => type.toLowerCase()).includes(fileType) &&
                !assignment.allowed_file_types.map((type) => type.toLowerCase()).includes(fileExtension.slice(1))) {
                setError(`File type not allowed. This assignment accepts: ${assignment.allowed_file_types.join(', ')}`);
                return;
            }

            setFile(selectedFile);
            setError(null);
            setSuccess(false);
        }
    };

    const finishEvaluation = (result: SubmissionEvaluationResult) => {
        setVerification(result);
        if (result.status === 'needs_attention') {
            setSuccess(false);
            onSuccess?.(false);
            return;
        }
        setReplaceSubmissionId(null);
        setSuccess(true);
        setTimeout(() => onSuccess?.(), 1200);
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
        if (!assignment || !assignment.is_active || (assignment.due_date && new Date(assignment.due_date) < new Date())) {
            setError('This assignment is closed or past its due date');
            return;
        }

        try {
            setUploading(true);
            setUploadProgress(0);
            setError(null);

            setVerification(null);
            const onUploadProgress = (progress: { loaded: number; total?: number }) => {
                if (progress.total) {
                    const percent = Math.min(100, Math.round((progress.loaded / progress.total) * 100));
                    setUploadProgress(percent);
                    if (percent === 100) {
                        setUploading(false);
                        setEvaluating(true);
                    }
                }
            };
            let response;
            if (replaceSubmissionId) {
                response = await submissionsAPI.replace(replaceSubmissionId, file, onUploadProgress);
            } else {
                const uploadResponse = await submissionsAPI.upload(
                    file,
                    Number(assignmentId),
                    onUploadProgress,
                );
                setUploading(false);
                setEvaluating(true);
                response = await submissionsAPI.evaluate(uploadResponse.data.id, undefined, false);
            }
            finishEvaluation(response.data as SubmissionEvaluationResult);

        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.response?.data?.detail || (replaceSubmissionId ? 'Replacement failed' : 'Upload failed'));
        } finally {
            setEvaluating(false);
            setUploading(false);
        }
    };

    return (
        <form onSubmit={handleUpload} className="space-y-4">
            {assignments.length === 0 ? <EmptyState title="No assignments have been posted yet" /> : (
                <FormField label="Assignment" htmlFor="assignment-select">
                    <Select id="assignment-select" value={assignmentId} disabled={!!replaceSubmissionId} onChange={(e) => { setAssignmentId(e.target.value); setFile(null); }} required>
                        <option value="">Select an assignment</option>
                        {assignments.map((assignment) => {
                            const closed = !assignment.is_active || (assignment.due_date ? new Date(assignment.due_date) < new Date() : false);
                            const alreadySubmitted = !submissionToReplace && submittedAssignmentIds.has(assignment.id);
                            return <option key={assignment.id} value={assignment.id} disabled={closed || alreadySubmitted}>
                                {assignment.subject_code} - {assignment.title}{closed ? ' (closed)' : alreadySubmitted ? ' (already submitted)' : ''}
                            </option>;
                        })}
                    </Select>
                    {!submissionToReplace && submittedAssignmentIds.size > 0 && (
                        <p className="mt-1 text-xs text-muted-foreground">Already submitted. Delete it to resubmit.</p>
                    )}
                </FormField>
            )}

            {assignments.find((assignment) => assignment.id === Number(assignmentId)) && (() => {
                const assignment = assignments.find((item) => item.id === Number(assignmentId))!;
                return <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                    <p className="font-semibold text-foreground">{assignment.title}</p>
                    <p className="mt-1 text-muted-foreground">{assignment.description || 'No additional instructions.'}</p>
                    {assignment.student_topic && <p className="mt-2 text-muted-foreground"><span className="font-semibold text-foreground">Your topic:</span> {assignment.student_topic}</p>}
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
                        ref={fileInputRef}
                        accept=".pdf,.docx,.py,.java,.cpp,.js,.ts"
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
                                <p className="text-xs text-muted-foreground mt-1">PDF, DOCX, or code files</p>
                            </div>
                        )}
                    </label>
                </div>
            </div>

            {error && <Alert variant="error">{error}</Alert>}

            {verification?.verification_verdict === 'mismatch' && (
                <Alert variant="error">
                    <p className="font-bold">This file doesn&apos;t appear to match {verification.verification_expected_topic || 'the selected assignment'}.</p>
                    {verification.verification_detected_topic && <p className="mt-1">Detected topic: {verification.verification_detected_topic}</p>}
                    {verification.verification_expected_topic && <p>Expected topic: {verification.verification_expected_topic}</p>}
                    {!!verification.verification_reasons?.length && (
                        <ul className="mt-2 list-disc pl-5">{verification.verification_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
                    )}
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={() => { setReplaceSubmissionId(Number(verification.submission_id)); setFile(null); fileInputRef.current?.click(); }}
                    >
                        Replace file
                    </Button>
                </Alert>
            )}
            {verification?.verification_verdict === 'unreadable_or_empty' && (
                <Alert variant="error">
                    <p className="font-bold">This file could not be read. Please upload a readable replacement.</p>
                    {!!verification.verification_reasons?.length && <ul className="mt-2 list-disc pl-5">{verification.verification_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={() => { setReplaceSubmissionId(Number(verification.submission_id)); setFile(null); fileInputRef.current?.click(); }}
                    >
                        Replace file
                    </Button>
                </Alert>
            )}
            {verification?.verification_verdict === 'partial_match' && (
                <Alert variant="warning">
                    <p className="font-semibold">This submission may not fully address the assignment.</p>
                    {!!verification.verification_missing_requirements?.length && (
                        <ul className="mt-2 list-disc pl-5">{verification.verification_missing_requirements.map((requirement, index) => <li key={index}>{requirement}</li>)}</ul>
                    )}
                </Alert>
            )}
            {verification?.verification_verdict === 'mismatch' && verification.status !== 'needs_attention' && (
                <Alert variant="warning">
                    <p className="font-semibold">This submission may not fully address the assignment, but it was sent for grading.</p>
                    {!!verification.verification_reasons?.length && <ul className="mt-2 list-disc pl-5">{verification.verification_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
                </Alert>
            )}
            {(verification?.verification_verdict === 'unverified' || verification?.verification_verdict === 'unverifiable') && (
                <Alert variant="warning">Automated assignment matching could not be confirmed. Your submission will be graded and reviewed manually if needed.</Alert>
            )}
            {verification?.verification_verdict === 'duplicate_submission' && (
                <Alert variant="info">This appears to be the same file you already submitted for this assignment. It will still be graded.</Alert>
            )}

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
                {evaluating
                    ? 'File uploaded — verifying and grading...'
                    : uploading
                        ? `Uploading file... ${uploadProgress}%`
                        : replaceSubmissionId
                            ? 'Replace & Verify'
                            : 'Upload & Evaluate'}
            </Button>
            {(uploading || evaluating) && (
                <p className="text-center text-sm text-muted-foreground" role="status" aria-live="polite">
                    {evaluating
                        ? 'The file has been sent. Assignment verification and AI grading are still running.'
                        : `Sending ${file?.name ?? 'file'} to secure storage: ${uploadProgress}%`}
                </p>
            )}
        </form>
    );
}
