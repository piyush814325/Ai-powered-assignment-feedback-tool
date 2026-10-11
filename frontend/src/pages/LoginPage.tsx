import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { Button, Input, FormField, Alert } from '../ui/components';
import AuthLayout from '../components/AuthLayout';

interface FormErrors {
    email?: string;
    password?: string;
}

function validateEmail(value: string) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [errors, setErrors] = useState<FormErrors>({});
    const navigate = useNavigate();
    const { login, isLoading, error } = useAuthStore();

    const validate = (): boolean => {
        const nextErrors: FormErrors = {};
        if (!email.trim()) nextErrors.email = 'Enter your email address.';
        else if (!validateEmail(email)) nextErrors.email = 'Enter a valid email address.';
        if (!password) nextErrors.password = 'Enter your password.';
        setErrors(nextErrors);
        return Object.keys(nextErrors).length === 0;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!validate()) return;
        try {
            await login(email, password);
            navigate('/dashboard');
        } catch {
            // Surfaced via `error` from the auth store.
        }
    };

    return (
        <AuthLayout title="Welcome back" subtitle="Sign in to your account to continue.">
            {error && (
                <Alert variant="error" className="mb-4">
                    {error}
                </Alert>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
                <FormField label="Email" htmlFor="login-email" error={errors.email}>
                    <Input
                        id="login-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        error={!!errors.email}
                        required
                    />
                </FormField>

                <FormField label="Password" htmlFor="login-password" error={errors.password}>
                    <div className="relative">
                        <Input
                            id="login-password"
                            type={showPassword ? 'text' : 'password'}
                            autoComplete="current-password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••"
                            error={!!errors.password}
                            className="pr-10"
                            required
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword((v) => !v)}
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                            className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                        >
                            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                    </div>
                </FormField>

                <Button type="submit" className="w-full" size="lg" isLoading={isLoading}>
                    {isLoading ? 'Signing in…' : 'Sign in'}
                </Button>
            </form>

            <div className="mt-6 text-center">
                <p className="text-muted-foreground text-sm">
                    Don&apos;t have an account?{' '}
                    <Link to="/register" className="text-accent hover:underline font-medium">
                        Sign up
                    </Link>
                </p>
            </div>
        </AuthLayout>
    );
}