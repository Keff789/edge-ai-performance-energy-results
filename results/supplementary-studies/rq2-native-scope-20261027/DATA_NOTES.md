# Measurement notes

H8/YOLOv7/b009 is included using its matching executable artifacts, recorded runtime parameters and retained image/tensor checks. The complete historical Native preprocessing recipe was not logged, and its missing hash has not been reconstructed. The source review is in `inputs/PAIRING_REVIEW_b009.json`. The compact `data/pairing_sensitivity.csv` reports results with and without this pair. All Generic recommendation losses and the number of Native winners found remain unchanged.

Quality uses Top-1 accuracy for classifiers and COCO AP50:95 for detectors, relative to the CPU-ONNX reference. The recorded Native quality evaluations for YOLO26m/b043 on H8 and H10 include an additional NMS step, which is absent from their timed completion paths. These quality values therefore describe the recorded evaluation pipeline. Their exact source mapping is retained in `data/quality_contract_provenance.json`.

Native, Full and energy measurements retain their recorded values. Generic throughput is not combined with energy from a different run. The archived import receipts preserve the acquisition history; the current input manifest identifies the observations used here.
