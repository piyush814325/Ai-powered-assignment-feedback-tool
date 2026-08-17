import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add token to requests
apiClient.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Auth API
export const authAPI = {
    register: (email: string, fullName: string, password: string, role: string) =>
        apiClient.post('/auth/register', { email, full_name: fullName, password, role }),

    login: (email: string, password: string) =>
        apiClient.post('/auth/login', { email, password }),

    getMe: () =>
        apiClient.get('/auth/me'),
};

// Submissions API
export const submissionsAPI = {
    upload: (file: File, assignmentId: string) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('assignment_id', assignmentId);
        return apiClient.post('/submissions/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    evaluate: (submissionId: number, rubricId: number = 1, useMockLLM: boolean = true) =>
        apiClient.post(`/submissions/evaluate/${submissionId}`, null, {
            params: { rubric_id: rubricId, use_mock_llm: useMockLLM },
        }),

    getSubmission: (submissionId: number) =>
        apiClient.get(`/submissions/${submissionId}`),

    listSubmissions: (studentId?: number) =>
        apiClient.get('/submissions/', { params: { student_id: studentId } }),

    reviewEvaluation: (evaluationId: number) =>
        apiClient.patch(`/submissions/evaluate/${evaluationId}/review`),

    updateEvaluation: (evaluationId: number, data: { scores?: Record<string, number>; feedback?: Record<string, string>; is_reviewed?: boolean }) =>
        apiClient.put(`/submissions/evaluations/${evaluationId}`, data),
};

export default apiClient;
