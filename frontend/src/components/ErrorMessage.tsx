import { ApiError, errorMessage } from "../services/api";

interface Props {
  error: unknown;
  onRetry?: () => void;
}

/** Renders an API/transport error as plain text (never HTML), with field details and the request id. */
export function ErrorMessage({ error, onRetry }: Props) {
  if (error === null || error === undefined || error === "") return null;
  const message = typeof error === "string" ? error : errorMessage(error);
  const fields = error instanceof ApiError ? error.fields : [];
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div className="error" role="alert">
      <strong>{message}</strong>
      {fields.length > 0 && (
        <ul>
          {fields.map((f, i) => (
            <li key={`${f.field}-${i}`}>
              {f.field ? `${f.field}: ` : ""}
              {f.message}
            </li>
          ))}
        </ul>
      )}
      {requestId && <div className="muted small">Reference: {requestId}</div>}
      {onRetry && (
        <button type="button" className="secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
