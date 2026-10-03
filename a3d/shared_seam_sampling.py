"""Finite propagation of subdivision parameters across shared source arcs.

Only source vertex identities establish an overlap. Coordinates, placed meshes
and proximity never establish a new attachment. Rational affine maps retain the
same parameter on both sides of every seam, including reversed and partial arcs.
"""
from collections import defaultdict, deque
from fractions import Fraction
import math

from .core import StudioError


def shared_parameters(pieces, chains, parameters):
    """Return all samples required by paired seams sharing source segments.

    ``chains`` maps seam IDs to two (piece ID, oriented vertex chain) pairs. The
    chains already include the source seam orientation. In a consistent overlap
    graph, each seed can reach each seam at most once. Nonidentity affine cycles
    are rejected: iterating such a cycle could demand infinitely many samples.
    """
    owners = defaultdict(list)
    for sid in sorted(chains):
        for pid, chain in chains[sid]:
            vertices = pieces[pid]['vertices']
            lengths = [Fraction(math.dist(vertices[a], vertices[b]))
                       for a, b in zip(chain, chain[1:])]
            total = sum(lengths)
            if not total or any(length <= 0 for length in lengths):
                raise StudioError('Collapsed source boundary segment')
            cumulative = Fraction(0)
            for (a, b), length in zip(zip(chain, chain[1:]), lengths):
                first, last = cumulative/total, (cumulative+length)/total
                # Coordinate direction is the lower source vertex ID to the
                # higher one, independently of polygon winding and seam side.
                lo, hi = (first, last) if a < b else (last, first)
                owners[(pid, min(a, b), max(a, b))].append((sid, lo, hi))
                cumulative += length

    graph = defaultdict(list)
    for key in sorted(owners):
        uses = owners[key]
        if len(uses) < 2:
            continue
        if len(uses) != 2 or uses[0][0] == uses[1][0]:
            raise StudioError('Unsupported repeated source boundary sampling')
        (a, a0, a1), (b, b0, b1) = uses
        scale = (b1-b0)/(a1-a0)
        offset = b0-scale*a0
        graph[a].append((b, scale, offset, min(a0, a1), max(a0, a1)))
        graph[b].append((a, 1/scale, -offset/scale, min(b0, b1), max(b0, b1)))

    result = {sid: {Fraction(t) for t in values} for sid, values in parameters.items()}
    visited = set()
    for root in sorted(graph):
        if root in visited:
            continue
        # t_seam = scale * t_root + offset. Exact map consistency is checked
        # before propagating samples, even where shared segments are partial.
        transforms = {root: (Fraction(1), Fraction(0))}
        queue = deque([root])
        while queue:
            sid = queue.popleft()
            scale, offset = transforms[sid]
            for other, multiplier, translation, _, _ in graph[sid]:
                candidate = (multiplier*scale, multiplier*offset+translation)
                if other in transforms:
                    if transforms[other] != candidate:
                        raise StudioError('Shared source arcs have inconsistent cyclic sampling maps')
                else:
                    transforms[other] = candidate
                    queue.append(other)
        visited.update(transforms)
        seeds = defaultdict(set)
        for sid, (scale, offset) in transforms.items():
            for t in result[sid]:
                seeds[(t-offset)/scale].add(sid)
        for global_t, starting in sorted(seeds.items()):
            reached = set(starting)
            queue = deque(sorted(starting))
            while queue:
                sid = queue.popleft()
                scale, offset = transforms[sid]
                t = scale*global_t+offset
                result[sid].add(t)
                for other, _, _, lo, hi in graph[sid]:
                    if lo <= t <= hi and other not in reached:
                        reached.add(other)
                        queue.append(other)
    return {sid: sorted({float(t) for t in values}) for sid, values in result.items()}
