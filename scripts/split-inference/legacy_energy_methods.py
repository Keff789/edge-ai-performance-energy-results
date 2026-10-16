"""Quantile convention retained from the source analysis."""
import math

def quantile(values, q):
    vals=sorted(values)
    if not vals:return None
    pos=(len(vals)-1)*q; lo=math.floor(pos); hi=math.ceil(pos)
    return vals[lo]+(vals[hi]-vals[lo])*(pos-lo)

