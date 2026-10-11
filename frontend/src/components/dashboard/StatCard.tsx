import { Card } from '../../ui/components';
import { cn } from '../../lib/utils';

interface StatCardProps {
    label: string;
    value: React.ReactNode;
    accent?: 'indigo' | 'emerald' | 'amber' | 'violet' | 'purple' | 'slate';
    className?: string;
}

const ACCENT_BORDER: Record<NonNullable<StatCardProps['accent']>, string> = {
    indigo: 'border-l-indigo-500',
    emerald: 'border-l-emerald-500',
    amber: 'border-l-amber-500',
    violet: 'border-l-violet-500',
    purple: 'border-l-purple-500',
    slate: 'border-l-slate-400',
};

const ACCENT_TEXT: Record<NonNullable<StatCardProps['accent']>, string> = {
    indigo: 'text-indigo-600 dark:text-indigo-400',
    emerald: 'text-emerald-600 dark:text-emerald-400',
    amber: 'text-amber-600 dark:text-amber-400',
    violet: 'text-violet-600 dark:text-violet-400',
    purple: 'text-purple-600 dark:text-purple-400',
    slate: 'text-foreground',
};

export function StatCard({ label, value, accent = 'slate', className }: StatCardProps) {
    return (
        <Card className={cn('p-5 border-l-4 shadow-sm hover:shadow transition', ACCENT_BORDER[accent], className)}>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</p>
            <p className={cn('text-3xl font-extrabold mt-2', ACCENT_TEXT[accent])}>{value}</p>
        </Card>
    );
}