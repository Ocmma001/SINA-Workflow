"""Class-aware, one-to-one detection matching at explicit deployment thresholds."""


def intersection_over_union(a, b):
    width = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    union = ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection)
    return intersection / union if union > 0 else 0.0


def score_detections(truth, predictions, iou_threshold, confidence=.0):
    if not 0 <= iou_threshold <= 1 or not 0 <= confidence <= 1:
        raise ValueError('thresholds must be between zero and one')
    used, matches, false_positives = set(), [], []
    for index, predicted in sorted(enumerate(predictions), key=lambda item: -item[1]['confidence']):
        if predicted['confidence'] < confidence:
            continue
        eligible = [(intersection_over_union(predicted['bbox'], target['bbox']), target_index)
                    for target_index, target in enumerate(truth)
                    if target_index not in used and target['class'] == predicted['class']]
        overlap, target_index = max(eligible, default=(-1, -1))
        if target_index >= 0 and overlap >= iou_threshold:
            used.add(target_index)
            matches.append({'prediction': index, 'truth': target_index, 'iou': overlap})
        else:
            false_positives.append(index)
    false_negatives = [index for index in range(len(truth)) if index not in used]
    tp, fp, fn = len(matches), len(false_positives), len(false_negatives)
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': tp/(tp+fp) if tp+fp else 0,
            'recall': tp/(tp+fn) if tp+fn else 0, 'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
            'matches': matches, 'false_positives': false_positives, 'false_negatives': false_negatives}
