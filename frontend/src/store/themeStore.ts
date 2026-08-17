import { create } from 'zustand';

type Theme = 'light' | 'dark';

interface ThemeState {
    theme: Theme;
    toggleTheme: () => void;
    setTheme: (theme: Theme) => void;
}

const getInitialTheme = (): Theme => {
    const saved = localStorage.getItem('app-theme') as Theme;
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

const applyTheme = (theme: Theme) => {
    const root = document.documentElement;
    if (theme === 'dark') {
        root.classList.add('dark');
    } else {
        root.classList.remove('dark');
    }
    localStorage.setItem('app-theme', theme);
};

// Apply initial theme immediately at script parse time
const initialTheme = getInitialTheme();
applyTheme(initialTheme);

export const useThemeStore = create<ThemeState>((set, get) => ({
    theme: initialTheme,
    toggleTheme: () => {
        const nextTheme = get().theme === 'light' ? 'dark' : 'light';
        applyTheme(nextTheme);
        set({ theme: nextTheme });
    },
    setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
    },
}));
