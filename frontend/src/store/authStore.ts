import { create } from 'zustand';
import { isAxiosError } from 'axios';
import { authAPI, ROLE_MISMATCH_CLEARED_EVENT } from '../services/api';

interface AuthErrorResponse {
    detail?: string;
}

interface User {
    id: number;
    email: string;
    full_name: string;
    roll_no?: string | null;
    role: 'student' | 'teacher' | 'admin';
    is_active: boolean;
    created_at: string;
}

interface AuthState {
    user: User | null;
    token: string | null;
    isLoading: boolean;
    error: string | null;
    register: (email: string, fullName: string, password: string, role: string, rollNo?: string) => Promise<void>;
    login: (email: string, password: string) => Promise<void>;
    logout: () => void;
    setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
    user: null,
    token: sessionStorage.getItem('access_token'),
    isLoading: false,
    error: null,

    register: async (email, fullName, password, role, rollNo) => {
        set({ isLoading: true, error: null });
        try {
            const response = await authAPI.register(email, fullName, password, role, rollNo);
            set({ user: response.data, isLoading: false });
        } catch (error: unknown) {
            const detail = isAxiosError<AuthErrorResponse>(error) ? error.response?.data?.detail : undefined;
            set({ error: detail || 'Registration failed', isLoading: false });
            throw error;
        }
    },

    login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
            const response = await authAPI.login(email, password);
            const { access_token, user } = response.data;
            sessionStorage.setItem('access_token', access_token);
            window.dispatchEvent(new Event(ROLE_MISMATCH_CLEARED_EVENT));
            set({ token: access_token, user, isLoading: false });
        } catch (error: unknown) {
            const detail = isAxiosError<AuthErrorResponse>(error) ? error.response?.data?.detail : undefined;
            set({ error: detail || 'Login failed', isLoading: false });
            throw error;
        }
    },

    logout: () => {
        sessionStorage.removeItem('access_token');
        set({ user: null, token: null });
    },

    setUser: (user) => {
        set({ user });
    },
}));
