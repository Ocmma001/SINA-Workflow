"""Bounded contact attachment; independent of OCR, YOLO and cloud review."""
def locate_pin(labels, x, y, radius=5):
    """Return nearest labelled pixel within a bounded radius, or unresolved."""
    height, width = labels.shape
    x, y = int(x), int(y)
    if not 0 <= x < width or not 0 <= y < height:
        return None
    best = None
    for py in range(max(0, y - radius), min(height, y + radius + 1)):
        for px in range(max(0, x - radius), min(width, x + radius + 1)):
            region = int(labels[py, px])
            distance2 = (px - x) ** 2 + (py - y) ** 2
            if region and distance2 <= radius ** 2 and (best is None or distance2 < best[0]):
                best = (distance2, px, py, region)
    return None if best is None else {'region': best[3], 'pixel': [best[1], best[2]],
                                      'distance': best[0] ** 0.5}


def attach_pins(circuit, labels, radius=5):
    return {c['id']: [{'image_point': point,
                      'connection_candidate': locate_pin(labels, *point, radius=radius)}
                     for point in c['connection_points']] for c in circuit}
