"""Native-rate, bounded-memory Welch PSD helpers for the journal extension.

Numerical operations are isolated from the frozen scope/Common-Reference path.
No extra low-pass filter, resampling, 2*pi correction, or deconvolution is used.
"""
from __future__ import annotations
from typing import Iterable, Any
from pathlib import Path
import numpy as np
from scipy.integrate import trapezoid
from scipy.signal import welch


def check_spectrum(f: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    f, p = np.asarray(f, dtype=np.float64), np.asarray(p, dtype=np.float64)
    if f.ndim != 1 or p.shape != f.shape or f.size < 2:
        raise ValueError('A spectrum needs matching 1-D frequency/density vectors')
    if not np.all(np.isfinite(f)) or not np.all(np.isfinite(p)):
        raise ValueError('Non-finite frequency or spectral density')
    if f[0] < 0 or np.any(np.diff(f) <= 0) or np.any(p < 0):
        raise ValueError('Frequencies must increase; frequencies/densities must be nonnegative')
    return f, p


def interval(f: np.ndarray, p: np.ndarray, low: float, high: float):
    """Use interpolated exact edges, never extrapolate outside measured support."""
    if low < f[0] - 1e-9 or high > f[-1] + 1e-9 or high <= low:
        raise ValueError(f'Interval [{low}, {high}] outside [{f[0]}, {f[-1]}]')
    x = np.r_[low, f[(f > low) & (f < high)], high]
    return x, np.interp(x, f, p)


def integrate_band(f: np.ndarray, p: np.ndarray, low: float, high: float) -> float:
    x, y = interval(f, p, low, high)
    return float(trapezoid(y, x))


def cumulative(f: np.ndarray, p: np.ndarray):
    f, p = check_spectrum(f, p)
    c = np.r_[0., np.cumsum((p[1:] + p[:-1]) * np.diff(f) * .5)]
    total = float(c[-1])
    return (c / total if total > 0 else np.full_like(c, np.nan)), total


def metrics(f: np.ndarray, p: np.ndarray, bandwidth: float = 77000.) -> dict[str, Any]:
    c, total = cumulative(f, p)
    result: dict[str, Any] = {'variance_integral': total,
        'status': 'valid' if total > 0 else 'no_positive_variance', 'support_high_hz': float(f[-1])}
    for q in (50, 90, 95, 99):
        result[f'f{q}_hz'] = float(np.interp(q / 100., c, f)) if total > 0 else None
    below = (100. * integrate_band(f, p, float(f[0]), bandwidth) / total
             if total > 0 and f[0] < bandwidth <= f[-1] else None)
    result['below_nominal_bandwidth_pct'] = below
    result['above_nominal_bandwidth_pct'] = 100. - below if below is not None else None
    return result


def shape_comparison(f1, p1, f2, p2, high=None):
    low = max(float(f1[0]), float(f2[0]))
    high = min(float(f1[-1]), float(f2[-1])) if high is None else float(high)
    x1, y1 = interval(f1, p1, low, high)
    x2, y2 = interval(f2, p2, low, high)
    f = np.union1d(x1, x2)
    # Interpolate spectral density BEFORE integrating it, not a decimated CDF.
    c1, a1 = cumulative(f, np.interp(f, x1, y1))
    c2, a2 = cumulative(f, np.interp(f, x2, y2))
    valid = a1 > 0 and a2 > 0
    return {'frequency_hz': f, 'tek_cumulative': c1, 'pico_cumulative': c2,
            'difference_pp': 100. * (c2 - c1),
            'max_abs_difference_pp': float(100. * np.max(np.abs(c2 - c1))) if valid else None,
            'pico_to_tek_variance_ratio_db': float(10. * np.log10(a2 / a1)) if valid else None,
            'normalisation_low_hz': low, 'normalisation_high_hz': high}


class StreamingWelch:
    """Exactly the same complete segments and mean as monolithic scipy Welch.

    Up to four overlapping segments per FFT batch. Memory is bounded by chunk
    size plus a few segment arrays, not by the duration of the recording.
    """
    def __init__(self, fs: float, nperseg: int, min_segments: int = 2):
        if fs <= 0 or nperseg < 64 or nperseg % 2:
            raise ValueError('Positive fs and even nperseg >= 64 are required')
        self.fs, self.n, self.hop = float(fs), int(nperseg), int(nperseg // 2)
        self.min_segments = int(min_segments)
        self.pending = np.empty(0, dtype=np.float64)
        self.psum = np.zeros(nperseg // 2 + 1, dtype=np.float64)
        self.count = self.segments = 0
        self.total = self.total_sq = 0.
        self.first = self.last = self.minimum = self.maximum = None
        self.frequencies = None

    def feed(self, incoming: np.ndarray) -> None:
        x = np.asarray(incoming, dtype=np.float64)
        if x.ndim != 1 or not np.all(np.isfinite(x)):
            raise ValueError('Signal is not finite, real, and one dimensional')
        if not x.size: return
        if self.first is None: self.first = float(x[0])
        self.last = float(x[-1])
        self.minimum = float(x.min()) if self.minimum is None else min(self.minimum, float(x.min()))
        self.maximum = float(x.max()) if self.maximum is None else max(self.maximum, float(x.max()))
        self.count += x.size
        self.total += float(x.sum(dtype=np.float64))
        self.total_sq += float(np.dot(x, x))
        b = np.concatenate((self.pending, x))
        k_all = max(0, 1 + (b.size - self.n) // self.hop)
        done = 0
        while done < k_all:
            k = min(4, k_all - done)
            part = b[done * self.hop:(done + k - 1) * self.hop + self.n]
            self.frequencies, p = welch(part, fs=self.fs, window='hann',
                nperseg=self.n, noverlap=self.hop, detrend='constant',
                scaling='density', return_onesided=True, average='mean')
            self.psum += p * k
            self.segments += k
            done += k
        self.pending = b[k_all * self.hop:].copy()

    def finish(self):
        if self.segments < self.min_segments or self.frequencies is None:
            raise ValueError(f'Only {self.segments} complete Welch segments; need {self.min_segments}')
        covered = (self.segments - 1) * self.hop + self.n
        mean = self.total / self.count
        meta = {'sample_count': int(self.count), 'duration_s': self.count / self.fs,
            'mean': mean, 'sample_variance': max(0., self.total_sq / self.count - mean * mean),
            'minimum': self.minimum, 'maximum': self.maximum,
            'rectangle_integral': self.total / self.fs,
            'trapezoid_integral': (self.total - .5 * (self.first + self.last)) / self.fs,
            'nperseg': self.n, 'noverlap': self.hop, 'welch_segments': self.segments,
            'frequency_resolution_hz': self.fs / self.n,
            'trailing_samples_excluded_from_welch': int(self.count - covered),
            'full_window_finite_check': True,
            'method': 'scipy_welch_hann_density_constant_detrend_onesided_mean',
            'welch_segments_are_not_physical_replicates': True}
        return self.frequencies, self.psum / self.segments, meta


def welch_chunks(chunks: Iterable[np.ndarray], fs: float, nperseg: int, min_segments: int = 2):
    state = StreamingWelch(fs, nperseg, min_segments)
    for chunk in chunks: state.feed(chunk)
    return state.finish()


def npy_chunks(path: Path, start: int, stop: int, chunk_size: int = 1048576):
    a = np.load(path, mmap_mode='r', allow_pickle=False)
    if a.ndim != 1 or a.dtype.kind not in 'fiu' or not 0 <= start < stop <= a.size:
        raise ValueError('Invalid numeric NPY shape or window')
    try:
        for pos in range(start, stop, chunk_size):
            yield np.asarray(a[pos:min(pos + chunk_size, stop)], dtype=np.float64)
    finally:
        del a
