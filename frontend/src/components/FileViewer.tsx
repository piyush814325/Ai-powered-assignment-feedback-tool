import { useEffect, useState } from 'react';
import { Download, ExternalLink } from 'lucide-react';
import { getApiErrorMessage, submissionsAPI } from '../services/api';
import type { Submission } from '../types/submission';
import { Alert, Button, Spinner } from '../ui/components';

const MAX_PREVIEW_BYTES = 5 * 1024 * 1024;
const SAFE_DOCX_ELEMENTS = new Set([
    'ARTICLE', 'BLOCKQUOTE', 'BR', 'COL', 'COLGROUP', 'DEL', 'DIV', 'H1', 'H2', 'H3',
    'H4', 'H5', 'H6', 'HR', 'IMG', 'INS', 'LI', 'OL', 'P', 'PRE', 'SECTION', 'SPAN',
    'STRONG', 'SUB', 'SUP', 'TABLE', 'TBODY', 'TD', 'TFOOT', 'TH', 'THEAD', 'TR',
    'U', 'UL',
]);
const DROP_DOCX_ELEMENTS = new Set([
    'EMBED', 'FORM', 'IFRAME', 'INPUT', 'LINK', 'META', 'OBJECT', 'SCRIPT', 'STYLE', 'SVG',
]);

interface FileViewerProps {
    submission: Pick<
        Submission,
        | 'id'
        | 'file_type'
        | 'original_filename'
        | 'file_path'
        | 'extracted_text'
        | 'extracted_code'
        | 'text_extraction_warning'
    >;
}

type FileTab = 'original' | 'extracted';

function sanitizeFilename(value: string): string {
    const name = value.replace(/[\\/\s]/g, '_').replace(/[^A-Za-z0-9._ -]/g, '_').trim().replace(/^[. ]+|[. ]+$/g, '');
    return name.slice(0, 180) || 'submission-file';
}

function filenameFromDisposition(header: string | undefined, fallback: string | null | undefined): string {
    const match = header?.match(/filename="([^"]*)"/i);
    return sanitizeFilename(match?.[1] || fallback || 'submission-file');
}

function safeDocxNode(node: Node): Node | null {
    if (node.nodeType === Node.TEXT_NODE) return node.cloneNode();
    if (!(node instanceof Element)) return null;

    const tag = node.tagName.toUpperCase();
    if (DROP_DOCX_ELEMENTS.has(tag)) return null;
    if (tag === 'A') {
        const fragment = document.createDocumentFragment();
        for (const child of Array.from(node.childNodes)) {
            const safeChild = safeDocxNode(child);
            if (safeChild) fragment.appendChild(safeChild);
        }
        return fragment;
    }
    if (!SAFE_DOCX_ELEMENTS.has(tag)) {
        const fragment = document.createDocumentFragment();
        for (const child of Array.from(node.childNodes)) {
            const safeChild = safeDocxNode(child);
            if (safeChild) fragment.appendChild(safeChild);
        }
        return fragment;
    }

    const clean = document.createElement(tag.toLowerCase());
    if (tag === 'IMG') {
        const source = node.getAttribute('src') || '';
        if (!/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(source)) return null;
        clean.setAttribute('src', source);
        const alt = node.getAttribute('alt');
        if (alt) clean.setAttribute('alt', alt.slice(0, 500));
    }
    if (tag === 'TD' || tag === 'TH' || tag === 'COL') {
        for (const attribute of ['colspan', 'rowspan', 'span']) {
            const value = node.getAttribute(attribute);
            if (value && /^\d{1,3}$/.test(value)) clean.setAttribute(attribute, value);
        }
    }
    for (const child of Array.from(node.childNodes)) {
        const safeChild = safeDocxNode(child);
        if (safeChild) clean.appendChild(safeChild);
    }
    return clean;
}

function buildIsolatedDocxHtml(body: HTMLElement): string {
    const safeRoot = document.createElement('div');
    for (const child of Array.from(body.childNodes)) {
        const safeChild = safeDocxNode(child);
        if (safeChild) safeRoot.appendChild(safeChild);
    }
    const content = new XMLSerializer().serializeToString(safeRoot);
    return `<!doctype html><html><head><meta charset="utf-8"><style>
        *{box-sizing:border-box}body{margin:0;padding:16px;background:#fff;color:#20242a;font:14px/1.55 Georgia,serif}
        table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #cbd2d8;padding:5px 8px;vertical-align:top}
        img{max-width:100%;height:auto}p{white-space:pre-wrap}section{margin:0 auto 18px;max-width:100%}
        </style></head><body>${content}</body></html>`;
}

function parseSpreadsheetPreview(text: string): string[][] {
    const rows: string[][] = [];
    for (const line of text.split(/\r?\n/)) {
        if (line.startsWith('## Sheet:') && rows.length) break;
        if (!line.trim().startsWith('|')) continue;
        const cells: string[] = [];
        let value = '';
        for (let index = 0; index < line.length; index += 1) {
            const character = line[index];
            if (character === '\\' && line[index + 1] === '|') {
                value += '|';
                index += 1;
            } else if (character === '|') {
                if (value || cells.length) cells.push(value.trim());
                value = '';
            } else {
                value += character;
            }
        }
        if (value.trim()) cells.push(value.trim());
        if (cells.length && !cells.every((cell) => /^:?-{3,}:?$/.test(cell))) {
            rows.push(cells.slice(0, 12));
            if (rows.length === 8) break;
        }
    }
    return rows;
}

export function FileViewer({ submission }: FileViewerProps) {
    const [activeTab, setActiveTab] = useState<FileTab>('original');
    const [blob, setBlob] = useState<Blob | null>(null);
    const [objectUrl, setObjectUrl] = useState<string | null>(null);
    const [downloadName, setDownloadName] = useState('submission-file');
    const [codeText, setCodeText] = useState<string | null>(null);
    const [docxHtml, setDocxHtml] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [docxLoading, setDocxLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        let localUrl: string | null = null;

        void (async () => {
            try {
                const response = await submissionsAPI.getFile(submission.id);
                if (cancelled) return;
                const fileBlob = response.data;
                localUrl = URL.createObjectURL(fileBlob);
                setBlob(fileBlob);
                setObjectUrl(localUrl);
                setDownloadName(filenameFromDisposition(
                    response.headers['content-disposition'],
                    submission.original_filename,
                ));
                if (submission.file_type === 'code' && fileBlob.size <= MAX_PREVIEW_BYTES) {
                    setCodeText(await fileBlob.text());
                }
            } catch (requestError) {
                if (!cancelled) setError(getApiErrorMessage(requestError));
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();

        return () => {
            cancelled = true;
            if (localUrl) URL.revokeObjectURL(localUrl);
        };
    }, [submission.id, submission.file_type, submission.original_filename]);

    useEffect(() => {
        if (
            submission.file_type !== 'docx'
            || !blob
            || blob.size > MAX_PREVIEW_BYTES
            || activeTab !== 'original'
            || docxHtml
        ) return;
        let cancelled = false;
        const body = document.createElement('div');
        const styles = document.createElement('div');
        void Promise.resolve().then(async () => {
            if (cancelled) return;
            setDocxLoading(true);
            const { renderAsync } = await import('docx-preview');
            await renderAsync(blob, body, styles, {
            useBase64URL: true,
            renderAltChunks: false,
            renderComments: false,
            ignoreFonts: true,
            });
            if (!cancelled) setDocxHtml(buildIsolatedDocxHtml(body));
        }).catch(() => {
            if (!cancelled) setError('The DOCX preview could not be rendered. Download the original file instead.');
        }).finally(() => {
            if (!cancelled) setDocxLoading(false);
        });
        return () => {
            cancelled = true;
        };
    }, [activeTab, blob, docxHtml, submission.file_type]);

    const isCode = submission.file_type === 'code';
    const extractedText = submission.extracted_code || submission.extracted_text || '';
    const spreadsheetRows = parseSpreadsheetPreview(submission.extracted_text || '');
    const lines = codeText?.split(/\r?\n/) ?? [];

    const downloadFile = () => {
        if (!objectUrl) return;
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = downloadName;
        anchor.rel = 'noopener noreferrer';
        anchor.click();
    };

    const openPdf = () => {
        if (objectUrl) window.open(objectUrl, '_blank', 'noopener,noreferrer');
    };

    return (
        <section className="space-y-4" aria-label="Submission file viewer">
            {submission.text_extraction_warning && <Alert variant="warning">{submission.text_extraction_warning}</Alert>}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border">
                <div className="flex gap-4" role="tablist" aria-label="Submission file views">
                    {([
                        ['original', 'Original file'],
                        ['extracted', 'Extracted text (what the AI read)'],
                    ] as const).map(([tab, label]) => (
                        <button
                            key={tab}
                            type="button"
                            role="tab"
                            aria-selected={activeTab === tab}
                            onClick={() => setActiveTab(tab)}
                            className={`border-b-2 px-1 pb-2 text-sm font-medium ${activeTab === tab
                                ? 'border-primary text-foreground'
                                : 'border-transparent text-muted-foreground hover:text-foreground'}`}
                        >
                            {label}
                        </button>
                    ))}
                </div>
                {activeTab === 'original' && objectUrl && (
                    <div className="flex gap-2 pb-2">
                        {submission.file_type === 'pdf' && (
                            <Button type="button" size="sm" variant="outline" onClick={openPdf}>
                                <ExternalLink className="h-4 w-4" />Open in new tab
                            </Button>
                        )}
                        <Button type="button" size="sm" variant="outline" onClick={downloadFile}>
                            <Download className="h-4 w-4" />Download
                        </Button>
                    </div>
                )}
            </div>

            {activeTab === 'extracted' ? (
                <div className="space-y-3">
                    {extractedText ? (
                        <pre className={`max-h-[34rem] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-4 text-sm leading-relaxed ${isCode ? 'font-mono' : 'font-sans'}`}>
                            {extractedText}
                        </pre>
                    ) : (
                        <p className="text-sm text-muted-foreground">No extracted text is available.</p>
                    )}
                </div>
            ) : loading ? (
                <div className="flex items-center gap-2 p-8 text-sm text-muted-foreground"><Spinner className="h-4 w-4" />Loading original file…</div>
            ) : error && !blob ? (
                <Alert variant="error">{error}</Alert>
            ) : blob && blob.size > MAX_PREVIEW_BYTES ? (
                <Alert variant="info">This file is too large to preview here. Download the original file to view it.</Alert>
            ) : submission.file_type === 'pdf' && objectUrl ? (
                <iframe
                    title={`Original PDF: ${downloadName}`}
                    src={objectUrl}
                    className="h-[65vh] min-h-96 w-full rounded-md border border-border bg-white"
                />
            ) : submission.file_type === 'docx' ? (
                <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">This preview may differ slightly from Microsoft Word.</p>
                    {docxLoading && <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Spinner className="h-4 w-4" />Preparing isolated preview…</div>}
                    {error && <Alert variant="error">{error}</Alert>}
                    {docxHtml && !docxLoading && (
                        <iframe
                            title={`Isolated DOCX preview: ${downloadName}`}
                            sandbox=""
                            referrerPolicy="no-referrer"
                            srcDoc={docxHtml}
                            className="h-[65vh] min-h-96 w-full rounded-md border border-border bg-white"
                        />
                    )}
                </div>
            ) : submission.file_type === 'code' && codeText !== null ? (
                <div className="max-h-[65vh] overflow-auto rounded-md border border-border bg-muted/20 p-3 font-mono text-xs leading-5">
                    <ol className="list-none">
                        {lines.map((line, index) => (
                            <li key={index} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3 whitespace-pre">
                                <span className="select-none text-right text-muted-foreground" aria-hidden="true">{index + 1}</span>
                                <span>{line || ' '}</span>
                            </li>
                        ))}
                    </ol>
                </div>
            ) : submission.file_type === 'spreadsheet' ? (
                <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Spreadsheet formula results are not recalculated in this viewer.</p>
                    {spreadsheetRows.length > 0 && (
                        <div className="max-h-80 overflow-auto rounded-md border border-border">
                            <table className="w-full border-collapse text-left text-xs">
                                <thead className="bg-muted/50">
                                    <tr>{spreadsheetRows[0].map((cell, index) => <th key={index} className="border-b border-border p-2 font-semibold">{cell}</th>)}</tr>
                                </thead>
                                <tbody>
                                    {spreadsheetRows.slice(1).map((row, rowIndex) => (
                                        <tr key={rowIndex}>
                                            {spreadsheetRows[0].map((_, columnIndex) => (
                                                <td key={columnIndex} className="border-b border-border p-2">{row[columnIndex] ?? ''}</td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            ) : (
                <div className="p-6 text-sm text-muted-foreground">This file type is available as a download only.</div>
            )}
            {activeTab === 'original' && error && blob && <Alert variant="error">{error}</Alert>}
        </section>
    );
}
