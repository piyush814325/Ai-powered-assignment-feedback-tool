import { useTheme } from '../hooks/useTheme';

const SunIcon = () => (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4 stroke-current">
        <circle cx="12" cy="12" r="5" fill="none" strokeWidth="2" />
        <path d="M12 1.5v2.5M12 20.5v2.5M4.22 4.22l1.77 1.77M17.01 17.01l1.77 1.77M1.5 12h2.5M20.5 12h2.5M4.22 19.78l1.77-1.77M17.01 6.99l1.77-1.77" fill="none" strokeWidth="2" />
    </svg>
);

const MoonIcon = () => (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4 fill-current">
        <path d="M21 12.79A9 9 0 0 1 11.21 3 7 7 0 1 0 21 12.79Z" />
    </svg>
);

export default function ThemeToggle() {
    const { theme, toggleTheme } = useTheme();
    const isDark = theme === 'dark';

    return (
        <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'Light' : 'Dark'} Mode`}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm transition-colors duration-200 hover:bg-muted focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-white dark:focus:ring-offset-slate-950"
        >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">
                {isDark ? <SunIcon /> : <MoonIcon />}
            </span>
            <span>{isDark ? 'Light Mode' : 'Dark Mode'}</span>
        </button>
    );
}
