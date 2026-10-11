/**
 * Merge class names, filtering out falsy values.
 * A minimal stand-in for `clsx`/`classnames` so we don't add a dependency
 * just for string concatenation.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
    return classes.filter(Boolean).join(' ');
}