import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

type FeedbackKind = 'success' | 'error' | 'info' | 'warning' | 'loading';

interface FeedbackToast {
  id: number;
  kind: FeedbackKind;
  message: string;
  autoCloseMs?: number;
}

interface ConfirmState {
  id: number;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
  danger: boolean;
  resolve: (value: boolean) => void;
}

interface FeedbackContextValue {
  pushToast: (message: string, kind?: FeedbackKind, autoCloseMs?: number) => number;
  closeToast: (id: number) => void;
  confirm: (options: {
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    danger?: boolean;
  }) => Promise<boolean>;
}

const FeedbackContext = createContext<FeedbackContextValue | null>(null);

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const nextToastId = useRef(1);
  const [toasts, setToasts] = useState<FeedbackToast[]>([]);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  const closeToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback<FeedbackContextValue['pushToast']>((message, kind = 'info', autoCloseMs = 2500) => {
    const id = nextToastId.current;
    nextToastId.current += 1;
    const toast: FeedbackToast = { id, message, kind, autoCloseMs };
    setToasts((current) => [...current, toast]);
    if (autoCloseMs && autoCloseMs > 0) {
      window.setTimeout(() => closeToast(id), autoCloseMs);
    }
    return id;
  }, [closeToast]);

  const confirm = useCallback<FeedbackContextValue['confirm']>(
    ({ title, message, confirmText = '确认', cancelText = '取消', danger = false }) => {
      const id = nextToastId.current;
      nextToastId.current += 1;
      return new Promise<boolean>((resolve) => {
        setConfirmState({
          id,
          title,
          message,
          confirmText,
          cancelText,
          danger,
          resolve,
        });
      });
    },
    [],
  );

  const value = useMemo(
    () => ({
      pushToast,
      closeToast,
      confirm,
    }),
    [pushToast, closeToast, confirm],
  );

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      {typeof window !== 'undefined'
        ? createPortal(
          <>
            <div className="feedback-toast-wrap" role="status" aria-live="polite">
              {toasts.map((toast) => (
                <div className={`feedback-toast feedback-toast-${toast.kind}`} key={toast.id} role="status">
                  <span>{toast.message}</span>
                  {toast.kind === 'loading' ? null : (
                    <button className="feedback-toast-close" type="button" onClick={() => closeToast(toast.id)}>
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
            {confirmState ? (
              <div
                className="feedback-dialog-overlay"
                onMouseDown={() =>
                  setConfirmState((current) => {
                    if (!current) return null;
                    current.resolve(false);
                    return null;
                  })
                }
              >
                <div
                  className="feedback-dialog"
                  onMouseDown={(event) => event.stopPropagation()}
                  role="dialog"
                  aria-modal="true"
                  aria-label={confirmState.title}
                >
                  <h3>{confirmState.title}</h3>
                  <p>{confirmState.message}</p>
                  <div className="feedback-dialog-actions">
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => {
                        confirmState.resolve(false);
                        setConfirmState(null);
                      }}
                    >
                      {confirmState.cancelText}
                    </button>
                    <button
                      type="button"
                      className={confirmState.danger ? 'danger-button' : 'text-button'}
                      onClick={() => {
                        confirmState.resolve(true);
                        setConfirmState(null);
                      }}
                    >
                      {confirmState.confirmText}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </>,
          document.body,
        )
        : null}
    </FeedbackContext.Provider>
  );
}

export function useFeedback() {
  const context = useContext(FeedbackContext);
  if (!context) {
    throw new Error('useFeedback must be used within FeedbackProvider');
  }
  return context;
}
