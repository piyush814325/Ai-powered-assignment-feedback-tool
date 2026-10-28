import { useCallback, useEffect, useState } from 'react';
import { getApiErrorMessage, teacherUploadsAPI } from '../services/api';
import type { UploadBatch, UploadBatchFileStatus } from '../types/teacherUploads';

const ACTIVE_STATUSES: UploadBatchFileStatus[] = [
    'uploaded',
    'processing',
    'parsed',
    'name_detected',
    'matched',
    'grading',
];

export function useBatchPolling(batchId: number | null) {
    const [batch, setBatch] = useState<UploadBatch | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [refreshKey, setRefreshKey] = useState(0);

    const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

    useEffect(() => {
        if (batchId === null) {
            return;
        }

        let cancelled = false;
        let timeout: ReturnType<typeof setTimeout> | undefined;
        let failures = 0;
        let hasLoaded = false;

        const poll = async () => {
            if (cancelled || document.hidden) return;
            if (!hasLoaded) setLoading(true);
            try {
                const response = await teacherUploadsAPI.getBatch(batchId);
                if (cancelled) return;
                const nextBatch = response.data;
                setBatch(nextBatch);
                setError(null);
                setLastUpdated(new Date());
                setLoading(false);
                failures = 0;
                hasLoaded = true;
                const shouldContinue = nextBatch.files.some((file) =>
                    ACTIVE_STATUSES.includes(file.status),
                );
                if (shouldContinue) timeout = setTimeout(poll, 3000);
            } catch (requestError) {
                if (cancelled) return;
                failures += 1;
                setError(getApiErrorMessage(requestError));
                setLoading(false);
                hasLoaded = true;
                const backoff = Math.min(3000 * (2 ** (failures - 1)), 30000);
                timeout = setTimeout(poll, backoff);
            }
        };

        const onVisibilityChange = () => {
            if (!document.hidden) {
                if (timeout) clearTimeout(timeout);
                void poll();
            } else if (timeout) {
                clearTimeout(timeout);
                timeout = undefined;
            }
        };

        document.addEventListener('visibilitychange', onVisibilityChange);
        void poll();
        return () => {
            cancelled = true;
            if (timeout) clearTimeout(timeout);
            document.removeEventListener('visibilitychange', onVisibilityChange);
        };
    }, [batchId, refreshKey]);

    return { batch: batch?.id === batchId ? batch : null, loading, error, lastUpdated, refresh };
}
