"""Scan the upper part of the plate (z > 100) for cylindrical features
along any axis, not just Y. The motor mount hole sits up there."""
from collections import defaultdict
from pathlib import Path

import numpy as np
from stl import mesh

STL = Path("/home/a8/git/personal/DIY-3-axis-CNC-machine/docs/stl_files/side_plates/left/LEFT_PLATE.stl")
m = mesh.Mesh.from_file(str(STL))
tris = m.vectors
n = m.normals.copy()
norms = np.linalg.norm(n, axis=1, keepdims=True)
nu = np.where(norms > 1e-12, n / norms, 0.0)

# Limit to upper portion
cent = tris.mean(axis=1)
upper = cent[:, 2] > 100
print(f"Upper triangles (z>100): {upper.sum()}")

# Histogram of dominant normal axis in upper region
dom = np.argmax(np.abs(nu[upper]), axis=1)
from collections import Counter
print("Dominant normal axis counts (0=X,1=Y,2=Z):", Counter(dom.tolist()))

# Histogram of Y centroid in upper region
y_face_mask = (np.abs(nu[upper, 1]) > 0.95)
yvals = cent[upper][y_face_mask, 1]
print("Y planes (upper, count rounded to 0.5):")
buckets = np.round(yvals * 2) / 2
print(Counter(buckets.tolist()).most_common(8))

# Print bbox of upper region
upper_pts = tris[upper].reshape(-1, 3)
print(f"Upper BBox X: [{upper_pts[:,0].min():.2f}, {upper_pts[:,0].max():.2f}]")
print(f"Upper BBox Y: [{upper_pts[:,1].min():.2f}, {upper_pts[:,1].max():.2f}]")
print(f"Upper BBox Z: [{upper_pts[:,2].min():.2f}, {upper_pts[:,2].max():.2f}]")

# Edges parallel to Y in upper region
grid = 1000
keys = np.round(tris * grid).astype(np.int64)
edge_to_tris = defaultdict(list)
for ti in range(len(tris)):
    for vi in range(3):
        a = tuple(keys[ti, vi])
        b = tuple(keys[ti, (vi + 1) % 3])
        e = (a, b) if a < b else (b, a)
        edge_to_tris[e].append(ti)

def collect_seams_along(axis):
    """axis 0=X, 1=Y, 2=Z. Return list of (other1, other2, length) where
    the seam is parallel to `axis`."""
    out = []
    for (a, b), owners in edge_to_tris.items():
        if len(owners) != 2:
            continue
        a_arr, b_arr = np.array(a), np.array(b)
        others = [i for i in range(3) if i != axis]
        if a[others[0]] == b[others[0]] and a[others[1]] == b[others[1]] and a[axis] != b[axis]:
            length = abs(a[axis] - b[axis]) / grid
            # midpoint in non-axis dims
            o1 = a[others[0]] / grid
            o2 = a[others[1]] / grid
            mid_z = (a[2] + b[2]) / 2 / grid if axis != 2 else a[2] / grid
            if mid_z > 100:
                out.append((o1, o2, length))
    return out

print("\n=== Upper-region seams along each axis (z>100) ===")
for axis, name in [(0, "X"), (1, "Y"), (2, "Z")]:
    s = collect_seams_along(axis)
    print(f"\n{name}-parallel seams: {len(s)}")
    if s:
        arr = np.asarray(s)
        print("  length histogram:", Counter(np.round(arr[:, 2]).astype(int).tolist()).most_common(5))
