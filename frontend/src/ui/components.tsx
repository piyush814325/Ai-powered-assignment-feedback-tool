import React, { useEffect, useId, useRef } from 'react';
import { Loader2, X } from 'lucide-react';
import { cn } from '../lib/utils';

/* ---------------------------------------------------------------------- */
/* Button                                                                  */
/* ---------------------------------------------------------------------- */

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive';
    size?: 'sm' | 'md' | 'lg' | 'icon';
    isLoading?: boolean;
}

const buttonVariants = {
    primary: 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm',
    secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
    outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
    ghost: 'hover:bg-accent hover:text-accent-foreground',
    destructive: 'bg-red-600 text-white hover:bg-red-700 shadow-sm',
};

const buttonSizes = {
    sm: 'h-8 px-3 text-sm gap-1.5',
    md: 'h-10 px-4 text-sm gap-2',
    lg: 'h-11 px-6 text-base gap-2',
    icon: 'h-10 w-10',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant = 'primary', size = 'md', isLoading = false, disabled, children, ...props }, ref) => (
        <button
            ref={ref}
            disabled={disabled || isLoading}
            aria-busy={isLoading || undefined}
            className={cn(
                'inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                'disabled:opacity-50 disabled:pointer-events-none',
                buttonVariants[variant],
                buttonSizes[size],
                className,
            )}
            {...props}
        >
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {children}
        </button>
    ),
);
Button.displayName = 'Button';

/* ---------------------------------------------------------------------- */
/* Card                                                                    */
/* ---------------------------------------------------------------------- */

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
    interactive?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
    ({ className, interactive = false, ...props }, ref) => (
        <div
            ref={ref}
            className={cn(
                'rounded-lg border border-border bg-card text-card-foreground shadow-sm',
                interactive && 'cursor-pointer transition hover:shadow-md hover:border-border/60',
                className,
            )}
            {...props}
        />
    ),
);
Card.displayName = 'Card';

/* ---------------------------------------------------------------------- */
/* Label                                                                   */
/* ---------------------------------------------------------------------- */

export const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
    ({ className, ...props }, ref) => (
        <label
            ref={ref}
            className={cn('block text-sm font-medium text-foreground mb-1.5', className)}
            {...props}
        />
    ),
);
Label.displayName = 'Label';

/* ---------------------------------------------------------------------- */
/* Input / Textarea / Select                                              */
/* ---------------------------------------------------------------------- */

const fieldBase =
    'flex w-full rounded-md border border-input bg-background text-sm placeholder:text-muted-foreground ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
    'disabled:cursor-not-allowed disabled:opacity-50';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
    error?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
    ({ className, error, ...props }, ref) => (
        <input
            ref={ref}
            aria-invalid={error || undefined}
            className={cn(fieldBase, 'h-10 px-3 py-2', error && 'border-red-400 focus-visible:ring-red-400', className)}
            {...props}
        />
    ),
);
Input.displayName = 'Input';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
    error?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
    ({ className, error, ...props }, ref) => (
        <textarea
            ref={ref}
            aria-invalid={error || undefined}
            className={cn(fieldBase, 'px-3 py-2 min-h-[80px] resize-y', error && 'border-red-400 focus-visible:ring-red-400', className)}
            {...props}
        />
    ),
);
Textarea.displayName = 'Textarea';

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
    ({ className, children, ...props }, ref) => (
        <select ref={ref} className={cn(fieldBase, 'h-10 px-3 py-2 appearance-none', className)} {...props}>
            {children}
        </select>
    ),
);
Select.displayName = 'Select';

/* ---------------------------------------------------------------------- */
/* Badge                                                                   */
/* ---------------------------------------------------------------------- */

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
    variant?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
}

const badgeVariants = {
    neutral: 'bg-muted text-muted-foreground',
    success: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    warning: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    danger: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300',
    info: 'bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300',
};

export function Badge({ className, variant = 'neutral', ...props }: BadgeProps) {
    return (
        <span
            className={cn(
                'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide',
                badgeVariants[variant],
                className,
            )}
            {...props}
        />
    );
}

/* ---------------------------------------------------------------------- */
/* Alert                                                                   */
/* ---------------------------------------------------------------------- */

interface AlertProps {
    variant?: 'error' | 'success' | 'info' | 'warning';
    children: React.ReactNode;
    className?: string;
}

const alertVariants = {
    error: 'bg-red-50 border-red-200 text-red-800 dark:bg-red-950/40 dark:border-red-900 dark:text-red-300',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-900 dark:text-emerald-300',
    info: 'bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-950/40 dark:border-blue-900 dark:text-blue-300',
    warning: 'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-950/40 dark:border-amber-900 dark:text-amber-300',
};

export function Alert({ variant = 'info', children, className }: AlertProps) {
    return (
        <div role="alert" className={cn('p-3 rounded-md border text-sm font-medium', alertVariants[variant], className)}>
            {children}
        </div>
    );
}

/* ---------------------------------------------------------------------- */
/* Spinner                                                                 */
/* ---------------------------------------------------------------------- */

export function Spinner({ className }: { className?: string }) {
    return <Loader2 className={cn('animate-spin', className)} aria-hidden="true" />;
}

/* ---------------------------------------------------------------------- */
/* EmptyState                                                              */
/* ---------------------------------------------------------------------- */

interface EmptyStateProps {
    icon?: React.ReactNode;
    title: string;
    description?: string;
    action?: React.ReactNode;
    className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
    return (
        <div className={cn('flex flex-col items-center justify-center text-center p-12 gap-2', className)}>
            {icon && <div className="text-muted-foreground/60 mb-2">{icon}</div>}
            <p className="text-foreground font-semibold">{title}</p>
            {description && <p className="text-sm text-muted-foreground max-w-sm">{description}</p>}
            {action && <div className="mt-3">{action}</div>}
        </div>
    );
}

/* ---------------------------------------------------------------------- */
/* Modal                                                                   */
/* ---------------------------------------------------------------------- */

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: React.ReactNode;
    subtitle?: React.ReactNode;
    children: React.ReactNode;
    footer?: React.ReactNode;
    headerClassName?: string;
    widthClassName?: string;
}

const modalStack: symbol[] = [];
let bodyOverflowBeforeModal = '';

/**
 * Accessible dialog that traps focus, restores it on close, and locks body scroll.
 */
export function Modal({ open, onClose, title, subtitle, children, footer, headerClassName, widthClassName = 'max-w-4xl' }: ModalProps) {
    const closeButtonRef = useRef<HTMLButtonElement>(null);
    const dialogRef = useRef<HTMLDivElement>(null);
    const returnFocusRef = useRef<HTMLElement | null>(null);
    const onCloseRef = useRef(onClose);
    const modalId = useRef(Symbol('modal'));
    const titleId = useId();
    const subtitleId = useId();

    useEffect(() => {
        onCloseRef.current = onClose;
    }, [onClose]);

    useEffect(() => {
        if (!open) return;
        const activeModalId = modalId.current;
        if (modalStack.length === 0) bodyOverflowBeforeModal = document.body.style.overflow;
        modalStack.push(activeModalId);
        document.body.style.overflow = 'hidden';
        returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        closeButtonRef.current?.focus();

        const onKeyDown = (e: KeyboardEvent) => {
            if (modalStack.at(-1) !== activeModalId) return;
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                onCloseRef.current();
                return;
            }
            if (e.key !== 'Tab') return;

            const focusable = Array.from(
                dialogRef.current?.querySelectorAll<HTMLElement>(
                    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
                ) ?? [],
            ).filter((element) => element.getAttribute('aria-hidden') !== 'true');
            if (focusable.length === 0) {
                e.preventDefault();
                dialogRef.current?.focus();
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            const active = document.activeElement;
            if (e.shiftKey && (active === first || !dialogRef.current?.contains(active))) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && (active === last || !dialogRef.current?.contains(active))) {
                e.preventDefault();
                first.focus();
            }
        };
        document.addEventListener('keydown', onKeyDown);
        return () => {
            document.removeEventListener('keydown', onKeyDown);
            const index = modalStack.lastIndexOf(activeModalId);
            if (index >= 0) modalStack.splice(index, 1);
            document.body.style.overflow = modalStack.length > 0 ? 'hidden' : bodyOverflowBeforeModal;
            if (returnFocusRef.current?.isConnected) returnFocusRef.current.focus();
        };
    }, [open]);

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
            role="presentation"
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                aria-describedby={subtitle ? subtitleId : undefined}
                tabIndex={-1}
                ref={dialogRef}
                className={cn(
                    'bg-card w-full rounded-2xl shadow-2xl border border-border overflow-hidden max-h-[90vh] flex flex-col my-8',
                    widthClassName,
                )}
            >
                <div className={cn('p-6 flex justify-between items-start gap-4 bg-slate-900 text-white', headerClassName)}>
                    <div className="min-w-0">
                        <div id={titleId} className="text-2xl font-bold truncate">{title}</div>
                        {subtitle && <div id={subtitleId} className="text-xs text-slate-300 mt-1">{subtitle}</div>}
                    </div>
                    <button
                        ref={closeButtonRef}
                        onClick={onClose}
                        aria-label="Close dialog"
                        className="shrink-0 rounded-md p-1.5 text-slate-300 hover:text-white hover:bg-white/10 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="overflow-y-auto flex-1">{children}</div>

                {footer && <div className="p-4 border-t border-border bg-muted/20 flex justify-between items-center gap-3">{footer}</div>}
            </div>
        </div>
    );
}

/* ---------------------------------------------------------------------- */
/* FormField — label + control + error, so pages don't hand-roll markup   */
/* ---------------------------------------------------------------------- */

interface FormFieldProps {
    label: string;
    htmlFor: string;
    error?: string;
    children: React.ReactNode;
    className?: string;
}

export function FormField({ label, htmlFor, error, children, className }: FormFieldProps) {
    return (
        <div className={className}>
            <Label htmlFor={htmlFor}>{label}</Label>
            {children}
            {error && (
                <p className="mt-1.5 text-xs font-medium text-red-600 dark:text-red-400" role="alert">
                    {error}
                </p>
            )}
        </div>
    );
}