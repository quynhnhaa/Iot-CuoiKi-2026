from dataclasses import dataclass
from collections import Counter, defaultdict
import json
import random


@dataclass
class SplitResult:
    assignments: dict[str, str]
    counts: dict[str, int]


def make_group_split(records, ratios=(0.70, 0.15, 0.15), seed=20261025) -> SplitResult:
    names = ('train', 'validation', 'test')
    if len(ratios) != 3 or abs(sum(ratios)-1) > 1e-8 or any(r <= 0 for r in ratios):
        raise ValueError('ratios must be three positive values totaling one')
    groups = defaultdict(list)
    global_labels = Counter()
    for record in records:
        group = record['group_id']
        if not group: raise ValueError('empty group_id')
        labels = record['labels']
        if isinstance(labels, str): labels = json.loads(labels)
        groups[group].append((record, Counter(labels)))
        global_labels.update(labels)
    rng = random.Random(seed)
    keys = list(groups)
    rng.shuffle(keys)
    keys.sort(key=lambda g: (-sum(sum(c.values()) for _, c in groups[g]), -len(groups[g])))
    target_images = {n: ratios[i]*len(records) for i,n in enumerate(names)}
    target_labels = {n: {label: ratios[i]*count for label,count in global_labels.items()} for i,n in enumerate(names)}
    image_counts = Counter(); group_counts = Counter(); label_counts = {n: Counter() for n in names}; assignments = {}
    for group in keys:
        n_images = len(groups[group]); counts = sum((c for _,c in groups[group]), Counter())
        def score(name):
            before = abs(image_counts[name]-target_images[name]) / max(1,target_images[name])
            after = abs(image_counts[name]+n_images-target_images[name]) / max(1,target_images[name])
            label_delta = sum(abs(label_counts[name][label]+count-target_labels[name][label])-abs(label_counts[name][label]-target_labels[name][label]) for label,count in counts.items()) / max(1, ratios[names.index(name)]*sum(global_labels.values()))
            group_target = ratios[names.index(name)] * len(groups)
            group_delta = (abs(group_counts[name]+1-group_target)-abs(group_counts[name]-group_target)) / max(1,group_target)
            return (after-before) + 0.25*label_delta + 0.5*group_delta
        choice = min(names, key=lambda n:(score(n), image_counts[n]/target_images[n], names.index(n)))
        assignments[group] = choice
        image_counts[choice] += n_images
        group_counts[choice] += 1
        label_counts[choice].update(counts)
    # Repair image-ratio drift after the label-aware greedy pass. Groups remain atomic.
    group_sizes = {g: len(items) for g, items in groups.items()}
    for _ in range(len(groups)):
        deficit = max(names, key=lambda n: target_images[n] - image_counts[n])
        surplus = max(names, key=lambda n: image_counts[n] - target_images[n])
        if deficit == surplus or image_counts[deficit] >= target_images[deficit] or image_counts[surplus] <= target_images[surplus]:
            break
        before = abs(image_counts[deficit]-target_images[deficit]) + abs(image_counts[surplus]-target_images[surplus])
        choices = [(abs(image_counts[deficit]+size-target_images[deficit]) + abs(image_counts[surplus]-size-target_images[surplus]), g, size) for g,size in group_sizes.items() if assignments[g] == surplus]
        if not choices: break
        after, group, size = min(choices)
        if after >= before: break
        assignments[group] = deficit
        image_counts[deficit] += size
        image_counts[surplus] -= size
    return SplitResult(assignments, dict(image_counts))
