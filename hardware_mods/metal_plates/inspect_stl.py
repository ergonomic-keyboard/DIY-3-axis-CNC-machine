"""Inspect LEFT_PLATE.stl: bbox, plate orientation, and Y-face histogram."""
from collections import Counter
from pathlib import Path

import numpy as np
from stl import mesh

STL = Path("/home/a8/git/personal/DIY-3-axis-CNC-machine/docs/stl_files/side_plates/left/LEFT_PLATE.stl")

m = mesh.Mesh.from_file(str(STL))
print(f"Triangles: {len(m.vectors)}")

pts = m.vectors.reshape(-1, 3)
mins, maxs = pts.min(axis=0), pts.max(axis=0)
print(f"BBox min: {mins}")
print(f"BBox max: {maxs}")
print(f"Size:     {maxs - mins}")

n = m.normals.copy()
norms = np.linalg.norm(n, axis=1, keepdims=True)
n_unit = np.where(norms > 1e-12, n / norms, 0.0)
dominant = np.argmax(np.abs(n_unit), axis=1)

# Centroid Y of triangles whose normal is along Y (perpendicular to plate face)
y_face_mask = (dominant == 1) & (np.abs(n_unit[:, 1]) > 0.95)
y_centroids = m.vectors[y_face_mask].mean(axis=1)[:, 1]
print(f"\nY-face triangles: {y_face_mask.sum()}")

# Histogram of Y centroids rounded to 0.5mm
buckets = np.round(y_centroids * 2) / 2
y_counts = Counter(buckets.tolist())
print("Top Y planes (centroid Y, triangle count):")
for y, c in sorted(y_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"  Y = {y:7.2f}  count={c}")

# Same for the other axes
for ax_i, name in enumerate(("X", "Y", "Z")):
    if ax_i == 1:
        continue
    mask = (dominant == ax_i) & (np.abs(n_unit[:, ax_i]) > 0.95)
    cents = m.vectors[mask].mean(axis=1)[:, ax_i]
    buckets = np.round(cents * 2) / 2
    c = Counter(buckets.tolist())
    print(f"\nTop {name} planes:")
    for v, n_ in sorted(c.items(), key=lambda x: -x[1])[:5]:
        print(f"  {name} = {v:7.2f}  count={n_}")
