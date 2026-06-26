import { useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { useI18n } from '../i18n/I18nProvider';

type CopyState = 'idle' | 'copied' | 'error';

export function CopyLinkButton() {
  const [state, setState] = useState<CopyState>('idle');
  const timerRef = useRef<number | null>(null);
  const { t } = useI18n();

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, []);

  async function copyCurrentUrl() {
    const text = window.location.href;
    try {
      await copyText(text);
      setState('copied');
    } catch {
      setState('error');
    }
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => setState('idle'), 1600);
  }

  const label = state === 'copied' ? t('copyLinkSuccess') : state === 'error' ? t('copyLinkFailed') : t('copyLink');
  const Icon = state === 'copied' ? Check : Copy;

  return (
    <button
      className="text-button copy-link-button"
      type="button"
      onClick={copyCurrentUrl}
      title={t('copyLink')}
      aria-label={t('copyLink')}
      style={{ width: '34px', justifyContent: 'center' }}
    >
      <Icon size={16} />
      <span className="sr-only">{label}</span>
    </button>
  );
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.top = '-1000px';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error('Copy failed');
  }
}
