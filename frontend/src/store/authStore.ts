import { create } from 'zustand';
import { authAPI } from '../services/api';

interface User {
    id: number;
    email: string;
    full_name: string;
    role: 'student' | 'teacher' | 'admin';
    is_active: boolean;
    created_at: string;
}

interface AuthState {
    user: User | null;
    token: string | null;
    isLoading: boolean;
    error: string | null;
    register: (email: string, fullName: string, password: string, role: string) => Promise<void>;
    login: (email: string, password: string) => Promise<void>;
    logout: () => void;
    setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
    user: null,
    token: localStorage.getItem('access_token'),
    isLoading: false,
    error: null,

    register: async (email, fullName, password, role) => {
        set({ isLoading: true, error: null });
        try {
            const response = await authAPI.register(email, fullName, password, role);
            set({ user: response.data, isLoading: false });
        } catch (error: any) {
            set({ error: error.response?.data?.detail || 'Registration failed', isLoading: false });
            throw error;
        }
    },

    login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
            const response = await authAPI.login(email, password);
            const { access_token, user } = response.data;
            localStorage.setItem('access_token', access_token);
            set({ token: access_token, user, isLoading: false });
        } catch (error: any) {
            set({ error: error.response?.data?.detail || 'Login failed', isLoading: false });
            throw error;
        }
    },

    logout: () => {
        localStorage.removeItem('access_token');
        set({ user: null, token: null });
    },

    setUser: (user) => {
        set({ user });
    },
}));
