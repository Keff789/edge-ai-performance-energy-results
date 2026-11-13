# Runner boundary illustration

Generic uses a common implementation for single- and multi-tensor boundaries. Native is tailored to the accelerator–GPU combination and requires exactly one input to the GPU suffix. The diagram illustrates different supported cut positions. In the paired evaluation, both runners execute the same cut with one input to the GPU suffix.

[PDF](system_overview.pdf) · [SVG](system_overview.svg) · [PNG](system_overview.png) · [Vector source and renderer](source.zip)

This diagram retains the author-supplied boundary illustration, with the two Task Completion labels corrected. The frozen R22 profile retains its original same-cut schematic. The R26 palette update uses blue `#4477AA` for the accelerator, orange `#EE7733` for the GPU, and green `#228833` for the cut. Text, geometry, neutral outlines and pale backgrounds are unchanged. The source provenance records the color mapping and source hashes. Numerical figures and tables are unchanged.
