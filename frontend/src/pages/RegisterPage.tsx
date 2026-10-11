import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { Button, Input, Select, FormField, Alert } from '../ui/components';
import AuthLayout from '../components/AuthLayout';

type Role = 'student' | 'teacher';

interface FormErrors {
    fullName?: string;
    email?: string;
    password?: string;
    confirmPassword?: string;
}

function validateEmail(value: string) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function RegisterPage() {
    const [email, setEmail] = useState('');
    const [fullName, setFullName] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [role, setRole] = useState<Role>('student');
    const [errors, setErrors] = useState<FormErrors>({});
    const navigate = useNavigate();
    const { register, isLoading, error } = useAuthStore();

    const validate = (): boolean => {
        const nextErrors: FormErrors = {};
        if (!fullName.trim()) nextErrors.fullName = 'Enter your full name.';
        if (!email.trim()) nextErrors.email = 'Enter your email address.';
        else if (!validateEmail(email)) nextErrors.email = 'Enter a valid email address.';
        if (!password) nextErrors.password = 'Choose a password.';
        else if (password.length < 8) nextErrors.password = 'Use at least 8 characters.';
        if (confirmPassword !== password) nextErrors.confirmPassword = 'Passwords do not match.';
        setErrors(nextErrors);
        return Object.keys(nextErrors).length === 0;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!validate()) return;
        try {
            await register(email, fullName, password, role);
            navigate('/login');
        } catch {
            // Surfaced via `error` from the auth store.
        }
    };

    return (
        <AuthLayout title="Create your account" subtitle="Sign up to start submitting or reviewing assignments.">
            {error && (
                <Alert variant="error" className="mb-4">
                    {error}
                </Alert>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
                <FormField label="Full name" htmlFor="register-name" error={errors.fullName}>
                    <Input
                        id="register-name"
                        type="text"
                        autoComplete="name"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        placeholder="Jordan Lee"
                        error={!!errors.fullName}
                        required
                    />
                </FormField>

                <FormField label="Email" htmlFor="register-email" error={errors.email}>
                    <Input
                        id="register-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        error={!!errors.email}
                        required
                    />
                </FormField>

                <FormField label="Password" htmlFor="register-password" error={errors.password}>
                    <div className="relative">
                        <Input
                            id="register-password"
                            type={showPassword ? 'text' : 'password'}
                            autoComplete="new-password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="At least 8 characters"
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

                <FormField label="Confirm password" htmlFor="register-confirm" error={errors.confirmPassword}>
                    <Input
                        id="register-confirm"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete="new-password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Re-enter your password"
                        error={!!errors.confirmPassword}
                        required
                    />
                </FormField>

                <FormField label="I am a…" htmlFor="register-role">
                    <Select id="register-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                        <option value="student">Student</option>
                        <option value="teacher">Teacher</option>
                    </Select>
                </FormField>

                <Button type="submit" className="w-full" size="lg" isLoading={isLoading}>
                    {isLoading ? 'Creating account…' : 'Create account'}
                </Button>
            </form>

            <div className="mt-6 text-center">
                <p className="text-muted-foreground text-sm">
                    Already have an account?{' '}
                    <Link to="/login" className="text-accent hover:underline font-medium">
                        Sign in
                    </Link>
                </p>
            </div>
        </AuthLayout>
    );
}