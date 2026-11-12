interface Props {
  samples: number[] | null | undefined;
  width?: number;
  height?: number;
  label?: string;
}

/** Synthetic ECG trace drawn as an SVG polyline from readings.ecg (numeric samples only). */
export function EcgTrace({ samples, width = 720, height = 160, label = "ECG lead II (synthetic)" }: Props) {
  const data = (samples ?? []).filter((v) => typeof v === "number" && Number.isFinite(v)).slice(0, 500);
  if (data.length < 2) {
    return (
      <div className="ecg ecg-empty" role="img" aria-label={`${label}: no signal`}>
        No ECG signal
      </div>
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = 8;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = pad + (1 - (v - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const gridX = Array.from({ length: Math.floor(width / 40) + 1 }, (_, i) => i * 40);
  const gridY = Array.from({ length: Math.floor(height / 40) + 1 }, (_, i) => i * 40);
  return (
    <figure className="ecg">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label={label} preserveAspectRatio="none">
        {gridX.map((x) => (
          <line key={`x${x}`} x1={x} y1={0} x2={x} y2={height} className="ecg-grid" />
        ))}
        {gridY.map((y) => (
          <line key={`y${y}`} x1={0} y1={y} x2={width} y2={y} className="ecg-grid" />
        ))}
        <polyline points={points} className="ecg-line" fill="none" />
      </svg>
      <figcaption className="muted small">{label}</figcaption>
    </figure>
  );
}
