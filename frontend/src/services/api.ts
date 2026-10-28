import axios from 'axios';
import type {
    AssigneeList,
    AssignmentAssigneePayload,
    ImportPreview,
    ImportPreviewConfirmPayload,
    RosterConfirmRequest,
    RosterConfirmResponse,
    RosterPreviewRequest,
    RosterPreviewResponse,
    TeacherStudentsPage,
    UploadBatch,
    UploadBatchCreated,
    UploadBatchPage,
    UploadFileActionResult,
} from '../types/teacherUploads';
import type { Submission } from '../types/submission';
import type { Assignment } from '../types/assignment';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const ROLE_MISMATCH_EVENT = 'auth:role-mismatch';
export const ROLE_MISMATCH_CLEARED_EVENT = 'auth:role-mismatch-cleared';

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add token to requests
apiClient.interceptors.request.use((config) => {
    const token = sessionStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

apiClient.interceptors.response.use(
    (response) => response,
    (error: unknown) => {
        if (
            axios.isAxiosError<{ detail?: string }>(error)
            && error.response?.status === 403
            && error.response.data?.detail === 'Teacher access required'
        ) {
            window.dispatchEvent(new Event(ROLE_MISMATCH_EVENT));
        }
        return Promise.reject(error);
    },
);

// Auth API
export const authAPI = {
    register: (email: string, fullName: string, password: string, role: string, rollNo?: string) =>
        apiClient.post('/auth/register', {
            email,
            full_name: fullName,
            password,
            role,
            ...(rollNo?.trim() ? { roll_no: rollNo.trim() } : {}),
        }),

    login: (email: string, password: string) =>
        apiClient.post('/auth/login', { email, password }),

    getMe: () =>
        apiClient.get('/auth/me'),
};

// Assignments API
export const assignmentsAPI = {
    list: () => apiClient.get('/assignments'),
    create: (payload: Record<string, unknown>) => apiClient.post('/assignments', payload),
    update: (id: number, payload: Record<string, unknown>) =>
        apiClient.patch<Assignment>(`/assignments/${id}`, payload),
    deleteImpact: (id: number) => apiClient.get<{
        students_assigned: number;
        submissions: number;
        graded_submissions: number;
    }>(`/assignments/${id}/delete-impact`),
    remove: (id: number) => apiClient.delete(`/assignments/${id}`),
};

export const teacherUploadsAPI = {
    listStudents: (query: string, limit = 50, offset = 0) =>
        apiClient.get<TeacherStudentsPage>('/teacher/students', { params: { query, limit, offset } }),
    upload: (
        files: File[],
        assignmentId?: number,
        name?: string,
        onUploadProgress?: (progress: { loaded: number; total?: number }) => void,
    ) => {
        const formData = new FormData();
        files.forEach((file) => formData.append('files', file));
        if (assignmentId !== undefined) formData.append('assignment_id', String(assignmentId));
        if (name?.trim()) formData.append('name', name.trim());
        return apiClient.post<UploadBatchCreated>('/teacher/uploads', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress,
        });
    },
    listBatches: (limit = 10, offset = 0) =>
        apiClient.get<UploadBatchPage>('/teacher/uploads', { params: { limit, offset } }),
    getBatch: (batchId: number) => apiClient.get<UploadBatch>(`/teacher/uploads/${batchId}`),
    renameBatch: (batchId: number, name: string | null) =>
        apiClient.patch<{ id: number; name: string | null }>(`/teacher/uploads/${batchId}`, { name }),
    deleteBatch: (batchId: number) => apiClient.delete(`/teacher/upload-batches/${batchId}`),
    deleteFile: (batchId: number, fileId: number) =>
        apiClient.delete(`/teacher/upload-batches/${batchId}/files/${fileId}`),
    confirm: (batchId: number, fileId: number, studentId: number, assignmentId?: number, allowDuplicate = false) =>
        apiClient.post<UploadFileActionResult>(
            `/teacher/uploads/${batchId}/files/${fileId}/confirm`,
            { student_id: studentId, assignment_id: assignmentId, allow_duplicate: allowDuplicate },
        ),
    reject: (batchId: number, fileId: number, reason: string) =>
        apiClient.post<UploadFileActionResult>(
            `/teacher/uploads/${batchId}/files/${fileId}/reject`,
            { reason },
        ),
    retry: (batchId: number, fileId: number) =>
        apiClient.post<UploadFileActionResult>(`/teacher/uploads/${batchId}/files/${fileId}/retry`),
};

export const assignmentAssigneesAPI = {
    get: (assignmentId: number) =>
        apiClient.get<AssigneeList>(`/assignments/${assignmentId}/assignees`),
    replace: (assignmentId: number, payload: AssignmentAssigneePayload) =>
        apiClient.put<AssigneeList>(`/assignments/${assignmentId}/assignees`, payload),
    updateTopic: (assignmentId: number, studentId: number, topicText: string, topicNumber?: number | null) =>
        apiClient.patch(
            `/assignments/${assignmentId}/assignees/${studentId}`,
            { topic_text: topicText, topic_number: topicNumber ?? null },
        ),
    previewImport: (assignmentId: number, file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return apiClient.post<ImportPreview>(
            `/assignments/${assignmentId}/assignees/import-preview`,
            formData,
            { headers: { 'Content-Type': 'multipart/form-data' } },
        );
    },
    confirmImport: (assignmentId: number, payload: ImportPreviewConfirmPayload) =>
        apiClient.post<AssigneeList>(
            `/assignments/${assignmentId}/assignees/import-preview/confirm`,
            payload,
        ),
};

export const rosterImportAPI = {
    preview: (assignmentId: number, request: RosterPreviewRequest) => {
        if ('file' in request) {
            const formData = new FormData();
            formData.append('file', request.file);
            if (request.sheet_name) formData.append('sheet_name', request.sheet_name);
            return apiClient.post<RosterPreviewResponse>(
                `/assignments/${assignmentId}/roster/preview`,
                formData,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
        }
        return apiClient.post<RosterPreviewResponse>(
            `/assignments/${assignmentId}/roster/preview`,
            request,
        );
    },
    confirm: (assignmentId: number, request: RosterConfirmRequest) =>
        apiClient.post<RosterConfirmResponse>(
            `/assignments/${assignmentId}/roster/confirm`,
            request,
        ),
};

export function getApiErrorMessage(error: unknown): string {
    const response = axios.isAxiosError(error) ? error.response : undefined;
    const detail = typeof response?.data?.detail === 'string' ? response.data.detail : '';
    if (response?.status && response.status >= 500) {
        return 'The server could not complete this request. Please try again later.';
    }
    if (response?.status === 403 && detail === 'Teacher access required') {
        return 'You are signed in with a different account in another tab. Please sign in again.';
    }
    const friendlyByStatus: Record<number, string> = {
        403: 'You do not have permission to perform this action.',
        404: 'This item could not be found or is no longer available.',
        409: "This action cannot be completed in the item's current state.",
        413: 'The upload exceeds the allowed size or file-count limit.',
        415: 'This file type is not supported. Choose an .xlsx or .csv file.',
        422: 'Some submitted information is invalid. Check the fields and try again.',
    };
    const friendly = response?.status ? friendlyByStatus[response.status] : undefined;
    return response?.status === 403 || response?.status === 404
        ? friendly ?? 'Something went wrong. Please try again.'
        : [friendly, detail].filter(Boolean).join(' ') || 'Something went wrong. Please try again.';
}

// Submissions API
export const submissionsAPI = {
    remove: (submissionId: number) =>
        apiClient.delete(`/student/submissions/${submissionId}`),

    upload: (file: File, assignmentId: number, onUploadProgress?: (progress: { loaded: number; total?: number }) => void) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('assignment_id', assignmentId.toString());
        return apiClient.post('/submissions/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress,
        });
    },

    replace: (submissionId: number, file: File, onUploadProgress?: (progress: { loaded: number; total?: number }) => void) => {
        const formData = new FormData();
        formData.append('file', file);
        return apiClient.post(`/submissions/${submissionId}/replace`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress,
        });
    },

    overrideVerification: (submissionId: number, reason: string) =>
        apiClient.post(`/submissions/${submissionId}/verification/override`, { reason }),

    rerunVerification: (submissionId: number) =>
        apiClient.post(`/submissions/${submissionId}/verification/rerun`),

    evaluate: (submissionId: number, rubricId?: number, useMockLLM: boolean = true) =>
        apiClient.post(`/submissions/evaluate/${submissionId}`, null, {
            params: { rubric_id: rubricId, use_mock_llm: useMockLLM },
        }),

    getSubmission: (submissionId: number) =>
        apiClient.get<Submission>(`/submissions/${submissionId}`),

    listSubmissions: (studentId?: number) =>
        apiClient.get<Submission[]>('/submissions/', { params: { student_id: studentId } }),

    reviewEvaluation: (evaluationId: number) =>
        apiClient.patch(`/submissions/evaluate/${evaluationId}/review`),

    updateEvaluation: (evaluationId: number, data: { scores?: Record<string, number>; feedback?: Record<string, string>; is_reviewed?: boolean }) =>
        apiClient.put(`/submissions/evaluations/${evaluationId}`, data),
};

export default apiClient;
