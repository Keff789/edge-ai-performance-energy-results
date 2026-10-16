from __future__ import annotations
import numpy as np
from scipy.signal import welch
from .journal_signal import welch_chunks, cumulative, shape_comparison, integrate_band


def run_journal_selftest():
    rng=np.random.default_rng(390)
    x=rng.normal(size=19237)
    f,p=welch(x,fs=8192,window='hann',nperseg=1024,noverlap=512,
              detrend='constant',scaling='density',average='mean')
    chunks=(x[i:i+777] for i in range(0,len(x),777))
    ff,pp,meta=welch_chunks(chunks,8192,1024)
    np.testing.assert_array_equal(f,ff)
    np.testing.assert_allclose(p,pp,rtol=3e-13,atol=1e-18)
    assert meta['sample_count']==len(x)
    # A common constant gain cancels from a normalised cumulative spectrum.
    d=shape_comparison(f,p,f,p*7.)
    assert d['max_abs_difference_pp']<1e-10
    # Exact band edge interpolation conserves area across a partition.
    f=np.linspace(0,100,101); p=2+f
    total=sum(integrate_band(f,p,a,b) for a,b in [(0,12.3),(12.3,77.7),(77.7,100)])
    assert abs(total-5200)<1e-9
    zero,total=cumulative(f,np.zeros_like(f))
    assert total==0 and np.all(np.isnan(zero))
    print('Journal self-test passed: streamed/native Welch parity, correct density normalisation, '
          'band-integral conservation, cumulative-gain invariance, and zero-spectrum safeguards.')
