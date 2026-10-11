import { GraduationCap } from 'lucide-react';
import { Card } from '../ui/components';
import ThemeToggle from './ThemeToggle';

interface AuthLayoutProps {
    title: string;
    subtitle: string;
    children: React.ReactNode;
    footer?: React.ReactNode;
}

/**
 * Consistent shell for /login and /register: same background, brand mark,
 * and card treatment so the two flows read as one product.
 */
export default function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex flex-col items-center justify-center p-4 relative">
            <div className="absolute top-4 right-4">
                <ThemeToggle />
            </div>

            <div className="mb-8 flex flex-col items-center gap-2">
                <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md">
                    <GraduationCap className="h-6 w-6" aria-hidden="true" />
                </div>
                <span className="font-bold text-lg text-foreground">AI Grading Studio</span>
            </div>

            <Card className="w-full max-w-md p-8 shadow-xl">
                <div className="mb-8">
                    <h1 className="text-3xl font-extrabold text-foreground">{title}</h1>
                    <p className="text-muted-foreground mt-2">{subtitle}</p>
                </div>

                {children}
            </Card>

            {footer && <div className="mt-6">{footer}</div>}
        </div>
    );
}