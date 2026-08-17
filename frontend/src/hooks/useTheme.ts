import { useCallback, useEffect, useMemo, useState } from 'react';

export type ThemeMode = 'light' | 'dark';
const STORAGE_KEY = 'app-theme';

const getStoredTheme = (): ThemeMode | null => {
    if (typeof window === 'undefined') return null;
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : null;
};

const getOsTheme = (): ThemeMode => {
    if (typeof window === 'undefined') return 'light';
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

const getInitialTheme = (): ThemeMode => getStoredTheme() ?? getOsTheme();

const applyThemeClass = (theme: ThemeMode) => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
};

const initialTheme = getInitialTheme();
if (typeof document !== 'undefined') {
    applyThemeClass(initialTheme);
}

export function useTheme() {
    const [theme, setTheme] = useState<ThemeMode>(initialTheme);

    useEffect(() => {
        applyThemeClass(theme);
        localStorage.setItem(STORAGE_KEY, theme);
    }, [theme]);

    const toggleTheme = useCallback(() => {
        setTheme((current) => (current === 'light' ? 'dark' : 'light'));
    }, []);

    const setThemeMode = useCallback((nextTheme: ThemeMode) => {
        setTheme(nextTheme);
    }, []);

    return useMemo(
        () => ({
            theme,
            isDark: theme === 'dark',
            toggleTheme,
            setTheme: setThemeMode,
        }),
        [theme, toggleTheme, setThemeMode],
    );
}
