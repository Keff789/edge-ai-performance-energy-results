# Implemented window rule v0.2.0

Scope: offline operational signal envelope from archived power; not a hardware-triggered inference boundary. No new calibration. The existing integration window, reconstructed original detector window (where independently recoverable), and new envelope are different quantities.

## Integration and detector bins

Uniform data: integrate every original interval using `(P[i]+P[i+1])/(2*fs)`; there are N-1 intervals. Requested 0.1-s bin edges are rounded with `numpy.rint` to real sample indices. Detector means are bin energy divided by actual bin duration. At low rates, actual bin lengths need not be identical. The energy is not computed by taking every kth sample.

Timestamped data: integrate the piecewise-linear POWER function on stored timestamps. Interpolated 0.1-s bins do not create new temporal information. v0.2.0 stops on negative timestamp differences; identical timestamps are retained as zero-duration intervals with a note. The result-only postpass has a separate, narrow eight-case terminal-prefix overlay; it is not a global time-axis repair.

## Baseline, contrast and activity

1. For span T, use fully contained bins within `edge=min(2 s,T/5)` at each side. Require at least two edge bins per side, at least eight total bins and T>=1 s.
2. Let m_pre and m_post be the two edge medians. Set `B=min(m_pre,m_post)` and `H=percentile(all bin means,95)`. The P95 is within one trace, not trimming physical repetitions.
3. Set `D=H-B` and `s=1.4826*max(MAD_pre,MAD_post)`. Require D to be strictly greater than `max(1e-9 W,0.005*max(abs(H),abs(B),1e-6 W),6*s)`. A pre/post difference greater than `max(0.1*D,6*s)` produces a separate warning.
4. Apply `theta=B+f*D` for fixed f=0.4,0.5,0.6. Bins must be strictly above threshold; a sustained segment lasts at least 0.2 s, with numerical comparison tolerance 1e-10 s.
5. The envelope covers the first through last qualifying segment. All INTERNAL pauses are retained. No maximum-energy search or fit to nominal/dry-run duration is used.
6. Main candidate f=0.5; the other two are sensitivity variants. Flag a boundary within 0.5 s of capture edge or an edge median above threshold. Stationary series retain an explicitly named legacy interval rather than inventing a load transition.
7. If three boundary-valid variants span more than 1% of the absolute f=0.5 energy, flag sensitivity. This was only a warning in v0.2.0; the v0.3.0 reporting policy excludes these candidates from new primary curves while retaining every value.
8. Interior windows trim at least 1/5/10 s at both ends, rounded inward to existing bin edges. Their actual durations are reported. Parent boundary flags must also apply to these child windows.

Legacy mismatch gate: `abs(delta_E)>max(2e-6 J,1e-7*abs(E_legacy))`. This blocks new main values, but does not remove the original stored YAML result.

## Determinism and validity are different

No random start, training, per-run hand selection or optimization for flat rate curves. Same input, timebase, code and numerical environment give the same rule decision. Fourteen focused cache traces reproduced decisions; three supplied original arrays were each processed five times with varied chunk sizes and identical boundaries. Largest observed summation difference was about 2e-11 J. This is not a cross-architecture bitwise guarantee or validation of every physical boundary.

Small early/late bursts can remain below the relative P95 threshold. A high baseline at capture start can make the start unidentifiable. Equal rules therefore do not guarantee an unbiased physical envelope for every signal class. Independently detected sensor envelopes are not necessarily the same physical interval. No universal 10-s cut is inferred from the operator's approximate capture description.
